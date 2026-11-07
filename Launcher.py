"""Омега — умный запуск мессенджера одним кликом.

Использование:
    python launcher.py             — показать меню запуска
    python launcher.py --autostart — сразу запустить сохранённый режим
"""
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
import urllib.parse

from config import DEFAULT_SERVER_URL, load_config, save_config

def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


SCRIPT_DIR = _base_dir()
REQUIRED = ["customtkinter", "websockets", "aiohttp", "cryptography"]


# ---------- Зависимости ----------
def _tk_error(title: str, message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk(); root.withdraw()
        messagebox.showerror(title, message, parent=root)
        root.destroy()
    except Exception:
        print(f"{title}: {message}", file=sys.stderr)


def ensure_deps() -> None:
    if _frozen():
        return
    missing = [p for p in REQUIRED if importlib.util.find_spec(p) is None]
    if not missing:
        return

    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk(); r.withdraw()
        messagebox.showinfo(
            "Омега — первый запуск",
            "Устанавливаю зависимости. Это займёт минуту.\n\n"
            + "\n".join(" • " + p for p in missing),
            parent=r,
        )
        r.destroy()
    except Exception:
        pass

    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", *missing]
        )
    except subprocess.CalledProcessError as e:
        _tk_error("Ошибка установки", f"pip завершился с ошибкой:\n{e}")
        sys.exit(1)


# ---------- Сеть ----------
def server_reachable(url: str) -> bool:
    try:
        u = urllib.parse.urlparse(url)
        host = u.hostname or "127.0.0.1"
        port = u.port or (443 if u.scheme == "wss" else 80)
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except Exception:
        return False


def wait_for_server(url: str, timeout: float = 4.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if server_reachable(url):
            return True
        time.sleep(0.2)
    return False


# ---------- Запуск ----------
def run_client() -> None:
    import client as omega_client
    omega_client.main()


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def server_launch_cmd() -> list[str]:
    if _frozen():
        return [os.path.join(SCRIPT_DIR, "OmegaServer.exe")]
    return [sys.executable, os.path.join(SCRIPT_DIR, "server.py")]


def start_server_proc() -> subprocess.Popen:
    return subprocess.Popen(server_launch_cmd(), cwd=SCRIPT_DIR)


def execute(action: str, url: str) -> bool:
    """Выполнить выбранный режим. True если успешно."""
    if action == "both":
        proc = start_server_proc()
        try:
            if not wait_for_server(url):
                _tk_error("Сервер не поднялся",
                          f"Не удалось стартовать сервер на {url}")
                return False
            run_client()
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
        return True

    if action == "client":
        if not server_reachable(url):
            return False
        run_client()
        return True

    if action == "server":
        subprocess.call(server_launch_cmd(), cwd=SCRIPT_DIR)
        return True

    return False


# ---------- Меню ----------
def show_menu(cfg: dict) -> dict:
    import customtkinter as ctk

    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    app = ctk.CTk()
    app.title("OMEGA Messenger — запуск")
    app.geometry("500x430")
    app.resizable(False, False)

    result = {
        "action": None,
        "url": cfg.get("server_url", DEFAULT_SERVER_URL),
        "save": True,
    }

    ctk.CTkLabel(app, text="OMEGA Messenger",
                 font=("Arial", 24, "bold")).pack(pady=(28, 2))
    ctk.CTkLabel(app, text="Защищённый E2E-мессенджер",
                 text_color="gray").pack(pady=(0, 20))

    action_var = ctk.StringVar(value=cfg.get("action", "both"))

    f = ctk.CTkFrame(app, fg_color="transparent")
    f.pack(fill="x", padx=28)

    ctk.CTkRadioButton(
        f, text="Сервер + клиент  (этот компьютер, для теста)",
        variable=action_var, value="both",
    ).pack(anchor="w", pady=6)
    ctk.CTkRadioButton(
        f, text="Только клиент  (подключиться к серверу)",
        variable=action_var, value="client",
    ).pack(anchor="w", pady=6)
    ctk.CTkRadioButton(
        f, text="Только сервер  (оставить работать у себя)",
        variable=action_var, value="server",
    ).pack(anchor="w", pady=6)

    ctk.CTkLabel(app, text="Адрес сервера (WebSocket):",
                 anchor="w").pack(fill="x", padx=28, pady=(16, 4))
    url_entry = ctk.CTkEntry(app, height=38)
    url_entry.insert(0, result["url"])
    url_entry.pack(fill="x", padx=28)

    save_var = ctk.BooleanVar(value=True)
    ctk.CTkCheckBox(
        app, text="Запомнить — следующий клик сразу открывает мессенджер",
        variable=save_var,
    ).pack(anchor="w", padx=28, pady=(16, 4))

    btn_row = ctk.CTkFrame(app, fg_color="transparent")
    btn_row.pack(fill="x", padx=28, pady=20)

    def launch() -> None:
        result["action"] = action_var.get()
        result["url"] = url_entry.get().strip() or DEFAULT_SERVER_URL
        result["save"] = save_var.get()
        app.destroy()

    def make_shortcut() -> None:
        try:
            install_shortcut()
            import tkinter as tk
            from tkinter import messagebox
            messagebox.showinfo(
                "Готово",
                "Ярлык «Omega Messenger» создан на рабочем столе.\n\n"
                "Двойной клик по нему — и мессенджер запускается.",
                parent=app,
            )
        except Exception as e:
            import tkinter as tk
            from tkinter import messagebox
            messagebox.showerror("Ошибка", str(e), parent=app)

    ctk.CTkButton(btn_row, text="Запустить", height=44,
                  font=("Arial", 15, "bold"),
                  command=launch).pack(side="left", fill="x",
                                       expand=True, padx=(0, 8))
    ctk.CTkButton(btn_row, text="Ярлык на рабочий стол", height=44,
                  fg_color="transparent", border_width=1,
                  command=make_shortcut).pack(side="left", fill="x",
                                              expand=True)

    app.mainloop()
    return result


# ---------- Ярлык ----------
def install_shortcut() -> None:
    script_name = os.path.basename(os.path.abspath(__file__))
    script_path = os.path.join(SCRIPT_DIR, script_name)
    python_exe = sys.executable

    if sys.platform.startswith("win"):
        pythonw = python_exe.replace("python.exe", "pythonw.exe")
        if not os.path.exists(pythonw):
            pythonw = python_exe

        desktop = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "[Environment]::GetFolderPath('Desktop')"],
            text=True,
        ).strip()
        lnk = os.path.join(desktop, "Omega Messenger.lnk")

        ps = (
            "$s = New-Object -ComObject WScript.Shell\n"
            f"$c = $s.CreateShortcut({json.dumps(lnk)})\n"
            f"$c.TargetPath = {json.dumps(pythonw)}\n"
            "$c.Arguments = '" + script_name + " --autostart'\n"
            f"$c.WorkingDirectory = {json.dumps(SCRIPT_DIR)}\n"
            "$c.IconLocation = 'shell32.dll,14'\n"
            "$c.Description = 'Omega Messenger'\n"
            "$c.Save()\n"
        )
        subprocess.check_call(
            ["powershell", "-NoProfile", "-Command", ps]
        )

    elif sys.platform == "darwin":
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        path = os.path.join(desktop, "Omega Messenger.command")
        with open(path, "w") as f:
            f.write(
                "#!/bin/bash\n"
                f'cd "{SCRIPT_DIR}"\n'
                f'"{python_exe}" "{script_name}" --autostart\n'
            )
        os.chmod(path, 0o755)

    else:  # Linux
        desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        os.makedirs(desktop_dir, exist_ok=True)
        content = (
            "[Desktop Entry]\n"
            "Version=1.0\n"
            "Type=Application\n"
            "Name=Omega Messenger\n"
            "Comment=Secure E2E messenger\n"
            f'Exec="{python_exe}" "{script_path}" --autostart\n'
            f"Path={SCRIPT_DIR}\n"
            "Icon=utilities-terminal\n"
            "Terminal=false\n"
            "Categories=Network;Chat;\n"
        )
        for target_dir in (
            desktop_dir,
            os.path.join(os.path.expanduser("~"), ".local", "share", "applications"),
        ):
            os.makedirs(target_dir, exist_ok=True)
            p = os.path.join(target_dir, "omega-messenger.desktop")
            with open(p, "w") as f:
                f.write(content)
            os.chmod(p, 0o755)


# ---------- main ----------
def _check_files() -> None:
    if _frozen():
        return
    for name in ("client.py", "server.py", "crypto.py", "config.py", "trust_store.py"):
        if not os.path.exists(os.path.join(SCRIPT_DIR, name)):
            raise FileNotFoundError(
                f"Рядом с {os.path.basename(__file__)} должен лежать файл «{name}»"
            )


def main() -> None:
    autostart = "--autostart" in sys.argv
    ensure_deps()
    _check_files()

    cfg = load_config()

    # Быстрый путь: уже настроено — запускаем без меню
    if autostart and cfg.get("action"):
        url = cfg.get("server_url", DEFAULT_SERVER_URL)
        if execute(cfg["action"], url):
            return
        # если не удалось — падаем в меню, чтобы дать шанс исправить

    # Меню
    result = show_menu(cfg)
    if not result["action"]:
        return

    cfg["action"] = result["action"]
    cfg["server_url"] = result["url"]
    save_config(cfg)

    if not execute(result["action"], result["url"]):
        _tk_error(
            "Не удалось запустить",
            f"Сервер {result['url']} недоступен.\n\n"
            "Запустите сервер отдельно или выберите\n"
            "«Сервер + клиент» в меню.",
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        _tk_error("Омега — критическая ошибка",
                  f"{e}\n\n{traceback.format_exc()}")
        sys.exit(1)
        