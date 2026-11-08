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
from urllib.parse import urlparse

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
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    use_dir = "--dir" in sys.argv
    if not args:
        print(__doc__)
        return 2
    url = args[0].strip()
    if not (url.startswith("ws://") or url.startswith("wss://")):
        print("Адрес должен начинаться с ws:// или wss://")
        return 2
    if not url.rstrip("/").endswith("/ws"):
        url = url.rstrip("/") + "/ws"

    dir_build = os.path.join(ROOT, "dist", "OmegaClient")
    if use_dir:
        if not os.path.exists(os.path.join(dir_build, "OmegaClient.exe")):
            print("Нет папочной сборки. Соберите: PyInstaller OmegaClientDir.spec")
            return 1
    elif not os.path.exists(EXE):
        print(f"Нет {EXE}\nСначала соберите клиент: build_exe.bat")
        return 1

    safe = urlparse(url).hostname or "local"
    safe = re.sub(r"[^A-Za-z0-9.-]+", "_", safe)
    suffix = "-portable" if use_dir else ""
    out = args[1] if len(args) > 1 else os.path.join(
        ROOT, "release", f"OMEGA-Messenger-{safe}{suffix}.zip")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

    tmp = tempfile.mkdtemp(prefix="omega_pack_")
    folder = os.path.join(tmp, "OMEGA-Messenger")
    os.makedirs(folder)

    if use_dir:
        shutil.copytree(dir_build, folder, dirs_exist_ok=True)
    else:
        shutil.copy2(EXE, os.path.join(folder, "OmegaClient.exe"))
    with open(os.path.join(folder, "omega_config.json"), "w", encoding="utf-8") as f:
        json.dump({"server_url": url, "username": "", "pin_keys": True},
                  f, ensure_ascii=False, indent=2)
    with open(os.path.join(folder, "ЧИТАТЬ-ПЕРВЫМ.txt"), "w", encoding="utf-8") as f:
        f.write(README.format(url=url))

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(folder):
            for name in files:
                full = os.path.join(root, name)
                rel = os.path.relpath(full, tmp).replace("\\", "/")
                z.write(full, rel)

    shutil.rmtree(tmp, ignore_errors=True)
    size = os.path.getsize(out) / (1024 * 1024)
    print(f"Готово: {out}  ({size:.1f} МБ)")
    print(f"Адрес внутри: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
