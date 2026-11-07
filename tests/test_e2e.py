"""E2E-тест протокола Омеги (без GUI).

Запуск:  python tests/test_e2e.py
Тест поднимает свой сервер на свободном порту и временный keyring.json,
поэтому не трогает рабочие данные рядом с приложением.
"""
import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

import websockets  # noqa: E402
from crypto import (KeyPair, decrypt_message, encrypt_message,  # noqa: E402
                    fingerprint)

try:                       # консоль Windows иначе не печатает кириллицу и ✓
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


async def recv_until(ws, types, timeout=5):
    end = time.time() + timeout
    while True:
        left = end - time.time()
        if left <= 0:
            raise asyncio.TimeoutError(f"нет {types} за {timeout} с")
        data = json.loads(await asyncio.wait_for(ws.recv(), left))
        if data.get("type") in types:
            return data


async def recv_all(ws, timeout=1.5):
    out = []
    try:
        while True:
            out.append(json.loads(await asyncio.wait_for(ws.recv(), timeout)))
    except asyncio.TimeoutError:
        return out


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def main(port: int) -> int:
    url = f"ws://127.0.0.1:{port}/ws"
    alice, bob, mallory = KeyPair(), KeyPair(), KeyPair()

    w1 = await websockets.connect(url)
    await w1.send(json.dumps({"action": "register", "username": "alice",
                              "pubkey": alice.export_public()}))
    d = await recv_until(w1, {"registered", "error"})
    check("регистрация alice", d.get("type") == "registered", str(d)[:60])

    w2 = await websockets.connect(url)
    await w2.send(json.dumps({"action": "register", "username": "боб",
                              "pubkey": bob.export_public()}))
    d = await recv_until(w2, {"registered", "error"})
    check("регистрация с кириллицей", d.get("type") == "registered", str(d)[:60])

    # --- закрепление ключа: тот же ник с ДРУГИМ ключом не пускают ---
    w3 = await websockets.connect(url)
    await w3.send(json.dumps({"action": "register", "username": "alice",
                              "pubkey": mallory.export_public()}))
    d = await recv_until(w3, {"registered", "error"})
    check("чужой ключ для ника отклонён", d.get("type") == "error"
          and "закреплён" in d.get("text", ""), str(d)[:60])
    await w3.close()

    # --- повторный вход тем же ключом вытесняет старую сессию ---
    w4 = await websockets.connect(url)
    await w4.send(json.dumps({"action": "register", "username": "alice",
                              "pubkey": alice.export_public()}))
    d = await recv_until(w4, {"registered", "error"})
    check("переподключение тем же ключом", d.get("type") == "registered", str(d)[:60])
    kicked = False
    try:
        for _ in range(5):
            raw = await asyncio.wait_for(w1.recv(), 2)
            if json.loads(raw).get("type") == "error":
                kicked = True
                break
    except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
        kicked = w1.close_code == 4001
    check("старая сессия закрыта", kicked or w1.close_code == 4001,
          f"code={w1.close_code}")
    try:
        await asyncio.wait_for(w1.wait_closed(), 3)
    except Exception:
        pass
    check("код закрытия 4001", w1.close_code == 4001, str(w1.close_code))

    # --- ключ онлайн ---
    await w4.send(json.dumps({"action": "get_pubkey", "target": "боб"}))
    d = await recv_until(w4, {"pubkey", "error"})
    ok = d.get("type") == "pubkey" and d.get("online") is True
    check("get_pubkey онлайн", ok, str(d)[:60])
    bob_pub = KeyPair.import_public(d["pubkey"]) if ok else bob.public_key
    check("отпечаток стабилен", fingerprint(bob_pub) == fingerprint(bob.public_key))

    # --- доставка онлайн + подтверждение отправителю ---
    await w4.send(json.dumps({"action": "send", "to": "боб", "id": "L1",
                              "payload": encrypt_message(alice, bob_pub, "привет, боб!"),
                              "ts": time.time()}))
    d = await recv_until(w2, {"message"})
    check("доставка онлайн", decrypt_message(bob.private_key, d["payload"]) == "привет, боб!")
    d = await recv_until(w4, {"sent"})
    check("подтверждение ✓", d.get("id") == "L1" and d.get("delivered") is True, str(d)[:80])

    # --- ключ офлайн-пользователя ---
    await w2.close()
    await asyncio.sleep(0.4)
    await w4.send(json.dumps({"action": "get_pubkey", "target": "боб"}))
    d = await recv_until(w4, {"pubkey", "error"})
    check("get_pubkey для офлайн", d.get("type") == "pubkey" and d.get("online") is False,
          str(d)[:60])

    # --- сообщение в офлайн уходит в очередь и доставляется при входе ---
    await w4.send(json.dumps({"action": "send", "to": "боб", "id": "L2",
                              "payload": encrypt_message(alice, bob_pub, "оффлайн привет"),
                              "ts": time.time()}))
    d = await recv_until(w4, {"sent"})
    check("офлайн-сообщение в очереди", d.get("delivered") is False, str(d)[:80])

    w5 = await websockets.connect(url)
    await w5.send(json.dumps({"action": "register", "username": "боб",
                              "pubkey": bob.export_public()}))
    msgs = await recv_all(w5)
    queued = [m for m in msgs if m.get("type") == "message"]
    check("очередь отдана при входе", len(queued) == 1
          and decrypt_message(bob.private_key, queued[0]["payload"]) == "оффлайн привет",
          f"{len(queued)} сообщ.")

    # --- список контактов: знаем и офлайн, и онлайн ---
    d = await recv_all(w5, 0.4)
    users = [m for m in d + msgs if m.get("type") == "users"]
    if users:
        last = users[-1]
        check("в списке есть известные ники",
              "alice" in last.get("list", []) and "боб" in last.get("list", []),
              str(last)[:80])
        check("online-флаг", "боб" in last.get("online", []), str(last)[:80])
    else:
        check("список контактов", False, "нет сообщения users")

    # --- валидация ---
    await w4.send(json.dumps({"action": "register", "username": "a b",
                              "pubkey": alice.export_public()}))
    d = await recv_until(w4, {"registered", "error"})
    check("ник с пробелом отклонён", d.get("type") == "error", str(d)[:60])

    await w4.send("не json")
    await w4.send(json.dumps({"action": "send", "to": "боб", "payload": 123}))
    await w4.send(json.dumps({"action": "send", "to": "нет-такого", "payload": "x"}))
    await w4.send(json.dumps({"action": "get_pubkey", "target": "нет-такого"}))
    d = await recv_until(w4, {"error"})
    check("неизвестный ник — ошибка", "нет" in d.get("text", ""), str(d)[:60])
    check("мусор не рвёт соединение", w4.close_code is None, str(w4.close_code))

    for w in (w4, w5):
        try:
            await w.close()
        except Exception:
            pass

    bad = [r[0] for r in results if not r[1]]
    print("\nИТОГ:", "ВСЁ ПРОШЛО" if not bad else "ПРОВАЛЫ: " + ", ".join(bad))
    return 0 if not bad else 1


if __name__ == "__main__":
    port = free_port()
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "OMEGA_KEYRING": os.path.join(tmp, "keyring.json")}
        proc = subprocess.Popen([sys.executable, os.path.join(APP, "server.py"),
                                 "--port", str(port), "--host", "127.0.0.1"],
                                cwd=APP, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.5)
        try:
            rc = asyncio.run(main(port))
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
    sys.exit(rc)
