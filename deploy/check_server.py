"""Проверка доступности сервера OMEGA: подключиться по WebSocket и отключиться.

    python deploy/check_server.py wss://ваш-адрес/ws
    python deploy/check_server.py ws://127.0.0.1:8080/ws
"""
import asyncio
import sys
import time

import websockets


async def main(url: str) -> int:
    started = time.time()
    try:
        async with websockets.connect(url, open_timeout=20) as ws:
            await ws.send('{"action": "get_pubkey", "target": "__ping__"}')
            reply = await asyncio.wait_for(ws.recv(), 10)
            print(f"OK: {url} отвечает за {time.time() - started:.2f} с")
            print(f"ответ сервера: {reply[:120]}")
            return 0
    except Exception as e:                              # noqa: BLE001
        print(f"НЕ УДАЛОСЬ: {url}\n  {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8080/ws"
    sys.exit(asyncio.run(main(target)))
