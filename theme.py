"""Темы, шрифты и настройки оформления OMEGA.

Здесь только визуальная часть: цвета, шрифты, обои, аватарки, профиль.
Сетевой протокол и шифрование не затрагиваются.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

from config import data_dir

SETTINGS_PATH = os.path.join(data_dir(), "ui_settings.json")
AVATAR_DIR = os.path.join(data_dir(), "avatars")
WALLPAPER_DIR = os.path.join(data_dir(), "wallpapers")

FONT_FAMILIES = [
    "Segoe UI", "Bahnschrift", "Calibri", "Tahoma",
    "Verdana", "Trebuchet MS", "Georgia", "Consolas",
]

# Варианты логотипа: заказчик выбирает в настройках.
LOGO_STYLES = {
    "gradient": ("Градиент (красный → оранжевый)", ("#ff4d4d", "#ff9f43")),
    "brand_red": ("Фирменный красный", ("#e63946", "#e63946")),
    "blue": ("Синий", ("#4c6ef5", "#4c6ef5")),
    "mint": ("Мятный", ("#2fbf8f", "#63e6be")),
    "mono": ("Белый", ("#ffffff", "#ffffff")),
}


@dataclass
class Theme:
    key: str
    title: str
    bg_chat: str
    bg_sidebar: str
    bg_header: str
    bg_input: str
    bubble_in: str
    bubble_out: str
    bubble_in_text: str
    bubble_out_text: str
    accent: str
    text: str
    text_dim: str
    online: str
    hover: str
    active: str
    separator: str


PRESETS: dict[str, Theme] = {
    "telegram_dark": Theme(
        key="telegram_dark", title="Telegram Dark",
        bg_chat="#0e1621", bg_sidebar="#212121", bg_header="#212121",
        bg_input="#17212b", bubble_in="#182533", bubble_out="#2b5278",
        bubble_in_text="#ffffff", bubble_out_text="#ffffff",
        accent="#2b5278", text="#ffffff", text_dim="#7d7d7d",
        online="#4fae4e", hover="#2a2a2a", active="#2b5278", separator="#182533",
    ),
    "midnight": Theme(
        key="midnight", title="Полночь",
        bg_chat="#0b1020", bg_sidebar="#111827", bg_header="#111827",
        bg_input="#1a2234", bubble_in="#1b2436", bubble_out="#3b5bdb",
        bubble_in_text="#e8eaf6", bubble_out_text="#ffffff",
        accent="#4c6ef5", text="#e8eaf6", text_dim="#8b93a7",
        online="#37b24d", hover="#1b2334", active="#3b5bdb", separator="#1b2436",
    ),
    "graphite": Theme(
        key="graphite", title="Графит",
        bg_chat="#121212", bg_sidebar="#1c1c1c", bg_header="#1c1c1c",
        bg_input="#232323", bubble_in="#242424", bubble_out="#3a3a3a",
        bubble_in_text="#f1f1f1", bubble_out_text="#ffffff",
        accent="#d4a017", text="#f1f1f1", text_dim="#8a8a8a",
        online="#57c96a", hover="#262626", active="#3a3a3a", separator="#242424",
    ),
    "light": Theme(
        key="light", title="Светлая",
        bg_chat="#eef1f5", bg_sidebar="#ffffff", bg_header="#ffffff",
        bg_input="#ffffff", bubble_in="#ffffff", bubble_out="#d3ecff",
        bubble_in_text="#111111", bubble_out_text="#111111",
        accent="#2b8cff", text="#111111", text_dim="#707579",
        online="#1fa855", hover="#f2f4f7", active="#e3f0ff", separator="#ffffff",
    ),
    "emerald": Theme(
        key="emerald", title="Изумруд",
        bg_chat="#0b1f1a", bg_sidebar="#102a23", bg_header="#102a23",
        bg_input="#16352c", bubble_in="#143a30", bubble_out="#1f6f54",
        bubble_in_text="#eafff7", bubble_out_text="#ffffff",
        accent="#2fbf8f", text="#eafff7", text_dim="#7fa89a",
        online="#4ade80", hover="#163a31", active="#1f6f54", separator="#143a30",
    ),
}


@dataclass
class Settings:
    """Пользовательские настройки оформления (ui_settings.json)."""

    theme: str = "telegram_dark"
    custom_bg: str = ""          # свой цвет фона чата (перекрывает тему)
    custom_sidebar: str = ""     # свой цвет сайдбара
    wallpaper: str = ""          # путь к картинке-обоям
    wallpaper_dim: int = 45      # затемнение обоев, %
    font_family: str = "Segoe UI"
    font_scale: int = 100        # размер шрифта, %
    show_ticks: bool = True      # показывать галочки доставки
    read_ticks: bool = True      # синие галочки «прочитано»
    status: str = ""             # свой статус в профиле
    logo_style: str = "gradient"

    # ---------- загрузка/сохранение ----------
    @classmethod
    def load(cls) -> "Settings":
        data = {}
        if os.path.exists(SETTINGS_PATH):
            try:
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
            except Exception:
                data = {}
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[settings] не удалось сохранить: {e}")

    # ---------- производные значения ----------
    def base_theme(self) -> Theme:
        return PRESETS.get(self.theme, PRESETS["telegram_dark"])

    def resolved_theme(self) -> Theme:
        """Тема с учётом пользовательских цветов."""
        base = self.base_theme()
        if not (self.custom_bg or self.custom_sidebar):
            return base
        return Theme(
            **{
                **asdict(base),
                "bg_chat": self.custom_bg or base.bg_chat,
                "bg_sidebar": self.custom_sidebar or base.bg_sidebar,
                "bg_header": self.custom_sidebar or base.bg_header,
                "bg_input": self.custom_sidebar or base.bg_input,
            }
        )

    def font(self, size: int, bold: bool = False) -> tuple:
        scale = max(70, min(160, int(self.font_scale))) / 100.0
        return (self.font_family, max(8, int(round(size * scale))),
                "bold" if bold else "normal")

    def logo_colors(self) -> tuple[str, str]:
        return LOGO_STYLES.get(self.logo_style, LOGO_STYLES["gradient"])[1]


def avatar_path(name: str) -> str:
    """Файл кастомной аватарки пользователя (если загружена)."""
    safe = "".join(c for c in (name or "_") if c.isalnum() or c in "-_ .")
    return os.path.join(AVATAR_DIR, f"{safe.strip()}.png")


def ensure_dirs() -> None:
    for d in (AVATAR_DIR, WALLPAPER_DIR):
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
