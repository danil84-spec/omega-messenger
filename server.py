"""Омега-сервер: маршрутизация зашифрованных сообщений и каталог публичных ключей.

Сервер НЕ имеет доступа к содержимому переписки: он видит только конверт
(кому, когда, сколько байт). Ключи из keyring.json — публичные.

Запуск:
    python server.py                  # слушать 0.0.0.0:8080
    python server.py --port 9000      # другой порт
    python server.py --host 127.0.0.1 # только локальные подключения
    python server.py --list-keys      # показать закреплённые ключи
    python server.py --reset-key Ник  # сбросить закреплённый ключ ника
"""
import argparse
import asyncio
import json
import logging
import os
import re
import socket
import tempfile
import threading
import time
import uuid

from aiohttp import web, WSMsgType

from config import data_dir, load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("omega")

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
KEYRING_PATH = os.environ.get("OMEGA_KEYRING") or os.path.join(data_dir(), "keyring.json")

clients: dict[str, dict] = {}        # ник -> {"ws", "pub"}  (только онлайн)
inbox:   dict[str, list] = {}        # ник -> [отложенные сообщения]
keyring: dict[str, dict] = {}        # ник -> {"pubkey", "first_seen", "last_seen"}

MAX_MSG_SIZE   = 1 * 1024 * 1024    # 1 МБ
MAX_INBOX      = 200                # макс. offline-сообщений на пользователя
INBOX_TTL      = 24 * 60 * 60       # 24 часа
MAX_PUBKEY_LEN = 8 * 1024           # PEM RSA-4096 с запасом

# Разрешена кириллица (А-Я, а-я, Ё, ё) в никнеймах
USERNAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9_.\-]{1,32}$")


# ---------------------------------------------------------------- keyring
def _load_keyring() -> None:
    global keyring
    if not os.path.exists(KEYRING_PATH):
        keyring = {}
        return
    try:
        with open(KEYRING_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        keyring = data if isinstance(data, dict) else {}
    except Exception as e:
        log.warning("keyring.json не прочитан (%s), начинаю с пустого", e)
        keyring = {}


def _save_keyring() -> None:
    """Атомарная запись, чтобы падение не оставило битый файл."""
    try:
        fd, tmp = tempfile.mkstemp(dir=DATA_DIR, prefix=".keyring-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(keyring, f, ensure_ascii=False, indent=2)
        os.replace(tmp, KEYRING_PATH)
    except Exception as e:
        log.error("не удалось сохранить keyring.json: %s", e)


def _pin_key(username: str, pubkey: str) -> tuple[bool, str]:
    """Закрепляет ключ за ником при первой регистрации.

    Возвращает (ok, причина отказа). Если за ник уже закреплён другой ключ —
    отказ: иначе любой мог бы войти под чужим ником и подменить собеседника.
    """
    entry = keyring.get(username)
    if entry and entry.get("pubkey") != pubkey:
        if not load_config().get("pin_keys", True):
            entry["pubkey"] = pubkey
            entry["last_seen"] = time.time()
            _save_keyring()
            log.warning("[!] ключ %s заменён (pin_keys=false)", username)
            return True, ""
        return False, ("Ключ для этого ника уже закреплён за другим устройством. "
                       "Выберите другой ник или сбросьте ключ на сервере: "
                       f"server.py --reset-key {username}")
    now = time.time()
    if entry is None:
        keyring[username] = {"pubkey": pubkey, "first_seen": now, "last_seen": now}
        _save_keyring()
        log.info("[+] новый ник %s закреплён", username)
    else:
        entry["last_seen"] = now
    return True, ""


# ---------------------------------------------------------------- helpers
def _prune_inbox() -> None:
    now = time.time()
    for user, q in list(inbox.items()):
        fresh = [m for m in q if now - (m.get("ts") or now) < INBOX_TTL]
        if fresh:
            inbox[user] = fresh[-MAX_INBOX:]
        else:
            inbox.pop(user, None)


def _flush_inbox(username: str) -> list[dict]:
    """Возвращает свежие сообщения и очищает очередь."""
    _prune_inbox()
    fresh = inbox.pop(username, [])
    return fresh


def _users_payload() -> dict:
    return {
        "type": "users",
        "list": sorted(set(keyring) | set(clients)),
        "online": sorted(clients),
    }


async def broadcast_users() -> None:
    msg = _users_payload()
    for info in list(clients.values()):
        try:
            await info["ws"].send_json(msg)
        except Exception:
            pass


# ---------------------------------------------------------------- websocket
async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(max_msg_size=MAX_MSG_SIZE, heartbeat=30)
    await ws.prepare(request)
    username: str | None = None

    try:
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            action = data.get("action")

            # --- Регистрация ---
            if action == "register":
                uname = (data.get("username") or "").strip()
                pubkey = data.get("pubkey")

                if not USERNAME_RE.match(uname):
                    await ws.send_json({"type": "error",
                                        "text": "Некорректный ник (1–32, буквы, цифры, _ . -)"})
                    continue
                if not pubkey or not isinstance(pubkey, str) or len(pubkey) > MAX_PUBKEY_LEN:
                    await ws.send_json({"type": "error", "text": "Нет публичного ключа"})
                    continue

                ok, reason = _pin_key(uname, pubkey)
                if not ok:
                    await ws.send_json({"type": "error", "text": reason})
                    continue

                # Тот же ник на новом соединении вытесняет старое:
                # после падения клиента сокет может висеть ещё несколько секунд.
                old = clients.get(uname)
                if old and old["ws"] is not ws:
                    try:
                        await old["ws"].send_json({
                            "type": "error",
                            "text": "Сеанс закрыт: выполнен вход с другого устройства"})
                    except Exception:
                        pass
                    try:
                        await old["ws"].close(code=4001,
                                              message=b"replaced by new session")
                    except Exception:
                        pass
                    clients.pop(uname, None)
                    log.info("[~] %s переподключился, старая сессия закрыта", uname)

                username = uname
                clients[username] = {"ws": ws, "pub": pubkey}
                await ws.send_json({"type": "registered"})
                await broadcast_users()
                for m in _flush_inbox(username):
                    await ws.send_json(m)
                log.info("[+] %s вошёл", username)

            # --- Запрос ключа (работает и для офлайн-пользователей) ---
            elif action == "get_pubkey":
                target = data.get("target")
                info = clients.get(target)
                if info:
                    pub = info["pub"]
                elif target in keyring:
                    pub = keyring[target]["pubkey"]
                else:
                    await ws.send_json({"type": "error",
                                        "text": f"{target}: такого пользователя нет"})
                    continue
                await ws.send_json({
                    "type": "pubkey",
                    "username": target,
                    "pubkey": pub,
                    "online": target in clients,
                })

            # --- Доставка ---
            elif action == "send":
                if not username:
                    continue
                to = data.get("to")
                payload = data.get("payload")
                if not isinstance(to, str) or not isinstance(payload, str):
                    continue
                msg_obj = {
                    "type": "message",
                    "id": str(uuid.uuid4()),
                    "from": username,
                    "payload": payload,
                    "ts": data.get("ts") or time.time(),
                }
                delivered = False
                target = clients.get(to)
                if target:
                    try:
                        await target["ws"].send_json(msg_obj)
                        delivered = True
                    except Exception:
                        target = None
                if not delivered:
                    q = inbox.setdefault(to, [])
                    q.append(msg_obj)
                    if len(q) > MAX_INBOX:
                        q.pop(0)
                # Подтверждение отправителю (✓ доставлено / ⌛ в очереди).
                await ws.send_json({
                    "type": "sent",
                    "id": data.get("id") or msg_obj["id"],
                    "mid": msg_obj["id"],
                    "to": to,
                    "delivered": delivered,
                    "ts": msg_obj["ts"],
                })

    finally:
        _prune_inbox()
        if username and clients.get(username, {}).get("ws") is ws:
            del clients[username]
            log.info("[-] %s вышел", username)
            await broadcast_users()

    return ws


async def index(request: web.Request) -> web.Response:
    return web.Response(
        text=f"Omega E2E server is running. Online: {len(clients)}, "
             f"known: {len(keyring)}\n",
        content_type="text/plain")


app = web.Application()
app.router.add_get("/", index)
app.router.add_get("/ws", ws_handler)


def run_in_thread(host: str = "127.0.0.1", port: int = 8080) -> threading.Thread:
    """Поднимает сервер в фоновом потоке (режим «клиент + сервер в одном окне»)."""
    _load_keyring()

    def _serve() -> None:
        try:
            web.run_app(app, host=host, port=port, print=None)
        except Exception as e:                       # noqa: BLE001
            log.error("сервер не запустился: %s", e)

    thread = threading.Thread(target=_serve, name="omega-server", daemon=True)
    thread.start()
    return thread


# ---------------------------------------------------------------- CLI
def _local_ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Omega E2E server")
    parser.add_argument("--host", default=os.environ.get("OMEGA_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("OMEGA_PORT")
                                    or os.environ.get("PORT")   # Render/Railway/Koyeb
                                    or "8080"))
    parser.add_argument("--list-keys", action="store_true",
                        help="показать закреплённые ключи и выйти")
    parser.add_argument("--reset-key", metavar="НИК",
                        help="удалить закреплённый ключ ника и выйти")
    args = parser.parse_args()

    _load_keyring()

    if args.list_keys:
        if not keyring:
            print("keyring.json пуст")
        for name, entry in sorted(keyring.items()):
            seen = time.strftime("%Y-%m-%d %H:%M",
                                 time.localtime(entry.get("last_seen") or 0))
            print(f"{name:<24} {seen}  {entry.get('pubkey', '')[:40]}...")
        return

    if args.reset_key:
        if keyring.pop(args.reset_key, None) is None:
            print(f"ника «{args.reset_key}» в keyring нет")
        else:
            _save_keyring()
            print(f"ключ «{args.reset_key}» сброшен — можно войти с новым")
        return

    log.info("Локальный адрес: ws://%s:%s/ws", _local_ip(), args.port)
    log.info("Слушаю на:       ws://%s:%s/ws", args.host, args.port)
    web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
