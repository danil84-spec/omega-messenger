"""Конфигурация Омега-мессенджера."""
import json
import os
import sys

DEFAULT_SERVER_URL = "ws://127.0.0.1:8080/ws"

# Значения по умолчанию: файл конфигурации лишь перекрывает их.
DEFAULTS = {
    "server_url": DEFAULT_SERVER_URL,
    "action": None,
    "pin_keys": True,   # сервер закрепляет первый ключ за ником (защита от подмены)
    "username": "",
}


def app_dir() -> str:
    """Папка программы: для .py — папка скрипта, для exe — папка exe.

    Внутри PyInstaller-сборки __file__ указывает во временную папку, которая
    удаляется при выходе, поэтому ключи и историю там хранить нельзя.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


_data_dir: str | None = None


def data_dir() -> str:
    """Папка для ключей, истории и настроек.

    Обычно рядом с программой (portable). Если туда нельзя писать
    (например, exe лежит в Program Files) — %APPDATA%\\OmegaMessenger.
    """
    global _data_dir
    if _data_dir:
        return _data_dir

    base = app_dir()
    try:
        probe = os.path.join(base, ".write-test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("")
        os.remove(probe)
        _data_dir = base
    except Exception:
        fallback = os.path.join(
            os.environ.get("APPDATA") or os.path.expanduser("~"),
            "OmegaMessenger")
        os.makedirs(fallback, exist_ok=True)
        _data_dir = fallback
    return _data_dir


def config_path() -> str:
    return os.path.join(data_dir(), "omega_config.json")


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    path = config_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    cfg.update(data)
        except Exception:
            pass
    return cfg


def save_config(cfg: dict) -> None:
    try:
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[config] не удалось сохранить: {e}")
