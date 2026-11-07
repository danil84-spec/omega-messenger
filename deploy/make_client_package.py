"""Собирает архив с клиентом OMEGA под конкретный адрес сервера.

    python deploy/make_client_package.py wss://203.0.113.10.sslip.io/ws
    python deploy/make_client_package.py ws://192.168.0.153:8080/ws .\\test.zip

В архиве: OmegaClient.exe, omega_config.json с уже вписанным адресом
и короткая инструкция для получателя.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "dist", "OmegaClient.exe")

README = """OMEGA Messenger — тестовая сборка
=================================

1. Распакуйте архив в любую папку (не в Program Files).
2. Запустите OmegaClient.exe.
   Windows покажет «Система Windows защитила ваш компьютер» — программа без
   цифровой подписи. Нажмите «Подробнее» → «Выполнить всё равно».
3. Введите ник (1–32 символа, без пробелов) и нажмите «Войти».
   Адрес сервера уже вписан: {url}
4. Слева появятся контакты. Выберите человека и напишите сообщение.
   Enter — отправить. ✓✓ серые — доставлено, ✓✓ синие — прочитано,
   🕓 — получатель не в сети (сообщение уйдёт, когда он войдёт).
5. При первом сообщении от нового человека появится отпечаток его ключа.
   Если вы сверили его лично — «Да», иначе «Нет».

Настройки — шестерёнка внизу слева: темы, шрифт, обои, аватар, статус.

Данные (ключ, история, настройки) лежат рядом с OmegaClient.exe.
Папку не удаляйте: в файле <ник>_keys.json лежит ваш ключ.

Если пишет «Нет связи» — проверьте, что адрес сервера ровно такой:
{url}
"""


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    url = sys.argv[1].strip()
    if not (url.startswith("ws://") or url.startswith("wss://")):
        print("Адрес должен начинаться с ws:// или wss://")
        return 2
    if not url.rstrip("/").endswith("/ws"):
        url = url.rstrip("/") + "/ws"

    if not os.path.exists(EXE):
        print(f"Нет {EXE}\nСначала соберите клиент: build_exe.bat")
        return 1

    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", url.split("//", 1)[-1])
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        ROOT, "release", f"OMEGA-Messenger-{safe}.zip")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

    tmp = tempfile.mkdtemp(prefix="omega_pack_")
    folder = os.path.join(tmp, "OMEGA-Messenger")
    os.makedirs(folder)

    shutil.copy2(EXE, os.path.join(folder, "OmegaClient.exe"))
    with open(os.path.join(folder, "omega_config.json"), "w", encoding="utf-8") as f:
        json.dump({"server_url": url, "username": "", "pin_keys": True},
                  f, ensure_ascii=False, indent=2)
    with open(os.path.join(folder, "ЧИТАТЬ-ПЕРВЫМ.txt"), "w", encoding="utf-8") as f:
        f.write(README.format(url=url))

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name in os.listdir(folder):
            z.write(os.path.join(folder, name), f"OMEGA-Messenger/{name}")

    shutil.rmtree(tmp, ignore_errors=True)
    size = os.path.getsize(out) / (1024 * 1024)
    print(f"Готово: {out}  ({size:.1f} МБ)")
    print(f"Адрес внутри: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
