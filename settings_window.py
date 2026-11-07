"""Модальное окно настроек OMEGA: профиль, оформление, о программе."""
from __future__ import annotations

import os
import shutil
import time
import urllib.request
from tkinter import colorchooser, filedialog, messagebox

import customtkinter as ctk

from theme import (FONT_FAMILIES, LOGO_STYLES, PRESETS, WALLPAPER_DIR,
                   avatar_path, ensure_dirs)

try:
    from PIL import Image
    PIL_OK = True
except Exception:
    PIL_OK = False


class SettingsWindow(ctk.CTkToplevel):
    """Настройки в отдельном окне. Изменения применяются сразу."""

    def __init__(self, app, page: str = "profile"):
        super().__init__(app)
        self.app = app
        self.settings = app.settings
        self.theme = self.settings.resolved_theme()

        self.title("OMEGA — настройки")
        self.geometry("720x560")
        self.minsize(640, 500)
        self.transient(app)
        self.configure(fg_color=self.theme.bg_sidebar)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.nav = ctk.CTkFrame(self, width=180, corner_radius=0,
                                fg_color=self.theme.bg_sidebar)
        self.nav.grid(row=0, column=0, sticky="nsw")
        self.nav.grid_propagate(False)
        self.content = ctk.CTkFrame(self, fg_color=self.theme.bg_chat,
                                    corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        for key, title in (("profile", "Профиль"),
                           ("appearance", "Оформление"),
                           ("about", "О программе")):
            btn = ctk.CTkButton(
                self.nav, text=title, anchor="w", height=38, corner_radius=8,
                fg_color="transparent", hover_color=self.theme.hover,
                text_color=self.theme.text, font=self.settings.font(13),
                command=lambda k=key: self.show_page(k))
            btn.pack(fill="x", padx=10, pady=4)
            self._nav_buttons[key] = btn

        self.show_page(page)

    # ------------------------------------------------------------------
    def _clear(self) -> None:
        for w in self.content.winfo_children():
            w.destroy()

    def _title(self, text: str) -> None:
        ctk.CTkLabel(self.content, text=text, text_color=self.theme.text,
                     font=self.settings.font(20, bold=True),
                     anchor="w").pack(fill="x", padx=24, pady=(20, 12))

    def _hint(self, text: str) -> None:
        ctk.CTkLabel(self.content, text=text, text_color=self.theme.text_dim,
                     font=self.settings.font(11), anchor="w",
                     wraplength=440, justify="left").pack(fill="x", padx=24,
                                                          pady=(0, 6))

    def show_page(self, key: str) -> None:
        for k, btn in self._nav_buttons.items():
            btn.configure(fg_color=self.theme.active if k == key else "transparent")
        self._clear()
        if key == "profile":
            self._page_profile()
        elif key == "appearance":
            self._page_appearance()
        else:
            self._page_about()

    # ------------------------------ профиль ---------------------------
    def _page_profile(self) -> None:
        self._title("Профиль")

        row = ctk.CTkFrame(self.content, fg_color="transparent")
        row.pack(fill="x", padx=24)
        self._avatar = ctk.CTkLabel(row, text="", fg_color=self.theme.bg_input,
                                    corner_radius=40, width=80, height=80,
                                    text_color=self.theme.text_dim,
                                    font=self.settings.font(28, True))
        self._avatar.pack(side="left", padx=(0, 16))
        self._refresh_avatar_preview()

        col = ctk.CTkFrame(row, fg_color="transparent")
        col.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(col, text="Загрузить фото", height=34, corner_radius=8,
                      fg_color=self.theme.accent,
                      command=self._pick_avatar).pack(fill="x", pady=(6, 4))
        ctk.CTkButton(col, text="Убрать фото", height=34, corner_radius=8,
                      fg_color="transparent", border_width=1,
                      text_color=self.theme.text,
                      command=self._remove_avatar).pack(fill="x")

        ctk.CTkLabel(self.content, text="Ник", text_color=self.theme.text_dim,
                     anchor="w", font=self.settings.font(12)).pack(
            fill="x", padx=24, pady=(20, 4))
        self.nick_entry = ctk.CTkEntry(
            self.content, height=38, corner_radius=10,
            fg_color=self.theme.bg_input, border_width=0,
            text_color=self.theme.text, font=self.settings.font(13))
        self.nick_entry.pack(fill="x", padx=24)
        self.nick_entry.insert(0, self.app.username)

        ctk.CTkLabel(self.content, text="Статус (виден только вам)",
                     text_color=self.theme.text_dim, anchor="w",
                     font=self.settings.font(12)).pack(fill="x", padx=24,
                                                       pady=(14, 4))
        self.status_entry = ctk.CTkEntry(
            self.content, height=38, corner_radius=10,
            fg_color=self.theme.bg_input, border_width=0,
            text_color=self.theme.text, placeholder_text="например, на связи",
            font=self.settings.font(13))
        self.status_entry.pack(fill="x", padx=24)
        self.status_entry.insert(0, self.settings.status)

        self._hint("Смена ника применится после перезапуска приложения: "
                   "сервер закрепляет ключ за ником.")

        btns = ctk.CTkFrame(self.content, fg_color="transparent")
        btns.pack(fill="x", padx=24, pady=16)
        ctk.CTkButton(btns, text="Сохранить", height=40, corner_radius=10,
                      fg_color=self.theme.accent,
                      command=self._save_profile).pack(side="right")
        ctk.CTkButton(btns, text="Перезапустить", height=40, corner_radius=10,
                      fg_color="transparent", border_width=1,
                      text_color=self.theme.text,
                      command=self._restart).pack(side="right", padx=(0, 8))

    def _refresh_avatar_preview(self) -> None:
        path = avatar_path(self.app.username)
        img = None
        if PIL_OK and os.path.exists(path):
            try:
                from PIL import ImageDraw
                im = Image.open(path).convert("RGB").resize((80, 80))
                mask = Image.new("L", (320, 320), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, 320, 320), fill=255)
                mask = mask.resize((80, 80))
                out = Image.new("RGBA", (80, 80), (0, 0, 0, 0))
                out.paste(im, (0, 0), mask)
                img = ctk.CTkImage(light_image=out, dark_image=out, size=(80, 80))
            except Exception:
                img = None
        if img is not None:
            self._avatar.configure(image=img, text="")
        else:
            self._avatar.configure(
                image=None, text=(self.app.username or "?")[:1].upper())

    def _pick_avatar(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите изображение",
            filetypes=[("Картинки", "*.png *.jpg *.jpeg *.bmp *.gif"),
                       ("Все файлы", "*.*")], parent=self)
        if not path:
            return
        if not self.app.set_avatar(path):
            messagebox.showerror("Аватар", "Не удалось открыть изображение.\n"
                                          "Нужен Pillow и файл-картинка.", parent=self)
            return
        self._refresh_avatar_preview()

    def _remove_avatar(self) -> None:
        self.app.remove_avatar()
        self._refresh_avatar_preview()

    def _save_profile(self) -> None:
        nick = self.nick_entry.get().strip()
        status = self.status_entry.get().strip()
        if nick and (len(nick) > 32 or any(c.isspace() for c in nick)):
            messagebox.showerror("Ник", "1–32 символа, без пробелов.", parent=self)
            return
        self.app.set_status(status)
        if nick and nick != self.app.username:
            self.app.request_nick_change(nick)
        self.destroy()

    def _restart(self) -> None:
        self.app.restart_app()

    # ---------------------------- оформление --------------------------
    def _page_appearance(self) -> None:
        self._title("Оформление")

        ctk.CTkLabel(self.content, text="Тема", anchor="w",
                     text_color=self.theme.text_dim,
                     font=self.settings.font(12)).pack(fill="x", padx=24)
        titles = {v.title: k for k, v in PRESETS.items()}
        current = PRESETS.get(self.settings.theme, PRESETS["telegram_dark"]).title
        self.theme_box = ctk.CTkOptionMenu(
            self.content, values=list(titles), width=240, height=34,
            fg_color=self.theme.bg_input, button_color=self.theme.accent,
            text_color=self.theme.text, font=self.settings.font(12),
            command=lambda t: self._set_theme(titles[t]))
        self.theme_box.pack(anchor="w", padx=24, pady=(4, 12))
        self.theme_box.set(current)

        colors = ctk.CTkFrame(self.content, fg_color="transparent")
        colors.pack(fill="x", padx=24)
        ctk.CTkButton(colors, text="Цвет фона чата", height=34, corner_radius=8,
                      fg_color=self.theme.accent,
                      command=lambda: self._pick_color("custom_bg")).pack(
            side="left", padx=(0, 8))
        ctk.CTkButton(colors, text="Цвет панелей", height=34, corner_radius=8,
                      fg_color="transparent", border_width=1,
                      text_color=self.theme.text,
                      command=lambda: self._pick_color("custom_sidebar")).pack(
            side="left", padx=(0, 8))
        ctk.CTkButton(colors, text="Сбросить", height=34, corner_radius=8,
                      fg_color="transparent", border_width=1,
                      text_color=self.theme.text_dim,
                      command=self._reset_colors).pack(side="left")

        ctk.CTkLabel(self.content, text="Обои чата", anchor="w",
                     text_color=self.theme.text_dim,
                     font=self.settings.font(12)).pack(fill="x", padx=24,
                                                       pady=(16, 4))
        walls = ctk.CTkFrame(self.content, fg_color="transparent")
        walls.pack(fill="x", padx=24)
        ctk.CTkButton(walls, text="Выбрать файл", height=34, corner_radius=8,
                      fg_color=self.theme.accent,
                      command=self._pick_wallpaper).pack(side="left", padx=(0, 8))
        ctk.CTkButton(walls, text="Из интернета", height=34, corner_radius=8,
                      fg_color="transparent", border_width=1,
                      text_color=self.theme.text,
                      command=self._wallpaper_from_url).pack(side="left",
                                                             padx=(0, 8))
        ctk.CTkButton(walls, text="Убрать", height=34, corner_radius=8,
                      fg_color="transparent", border_width=1,
                      text_color=self.theme.text_dim,
                      command=self._clear_wallpaper).pack(side="left")

        self.dim_slider = ctk.CTkSlider(
            self.content, from_=0, to=80, number_of_steps=16,
            command=self._set_dim)
        self.dim_slider.pack(fill="x", padx=24, pady=(12, 2))
        self.dim_slider.set(self.settings.wallpaper_dim)
        ctk.CTkLabel(self.content, text="Затемнение обоев", anchor="w",
                     text_color=self.theme.text_dim,
                     font=self.settings.font(10)).pack(fill="x", padx=24)

        ctk.CTkLabel(self.content, text="Шрифт", anchor="w",
                     text_color=self.theme.text_dim,
                     font=self.settings.font(12)).pack(fill="x", padx=24,
                                                       pady=(16, 4))
        fonts = ctk.CTkFrame(self.content, fg_color="transparent")
        fonts.pack(fill="x", padx=24)
        self.font_box = ctk.CTkOptionMenu(
            fonts, values=FONT_FAMILIES, width=200, height=34,
            fg_color=self.theme.bg_input, button_color=self.theme.accent,
            text_color=self.theme.text, font=self.settings.font(12),
            command=self._set_font)
        self.font_box.pack(side="left", padx=(0, 10))
        self.font_box.set(self.settings.font_family)
        self.size_slider = ctk.CTkSlider(
            fonts, from_=80, to=140, number_of_steps=12,
            command=self._set_font_scale, width=140)
        self.size_slider.pack(side="left")
        self.size_slider.set(self.settings.font_scale)

        ctk.CTkLabel(self.content, text="Логотип", anchor="w",
                     text_color=self.theme.text_dim,
                     font=self.settings.font(12)).pack(fill="x", padx=24,
                                                       pady=(16, 4))
        self.logo_box = ctk.CTkOptionMenu(
            self.content, values=[v[0] for v in LOGO_STYLES.values()],
            width=280, height=34, fg_color=self.theme.bg_input,
            button_color=self.theme.accent, text_color=self.theme.text,
            font=self.settings.font(12), command=self._set_logo)
        self.logo_box.pack(anchor="w", padx=24)
        self.logo_box.set(LOGO_STYLES[self.settings.logo_style][0])

        self.ticks_var = ctk.BooleanVar(value=self.settings.show_ticks)
        ctk.CTkCheckBox(
            self.content, text="Показывать галочки доставки",
            variable=self.ticks_var, font=self.settings.font(12),
            text_color=self.theme.text, fg_color=self.theme.accent,
            command=self._toggle_ticks).pack(anchor="w", padx=24, pady=(16, 0))

        ctk.CTkButton(self.content, text="Готово", height=40, corner_radius=10,
                      fg_color=self.theme.accent,
                      command=self.destroy).pack(anchor="e", padx=24, pady=16)

    def _set_theme(self, key: str) -> None:
        self.settings.theme = key
        self.settings.custom_bg = ""
        self.settings.custom_sidebar = ""
        self._apply()

    def _pick_color(self, field: str) -> None:
        color = colorchooser.askcolor(
            color=getattr(self.settings, field) or
            getattr(self.theme, "bg_chat" if field == "custom_bg" else "bg_sidebar"),
            title="Выберите цвет", parent=self)
        if color and color[1]:
            setattr(self.settings, field, color[1])
            self._apply()

    def _reset_colors(self) -> None:
        self.settings.custom_bg = ""
        self.settings.custom_sidebar = ""
        self._apply()

    def _pick_wallpaper(self) -> None:
        path = filedialog.askopenfilename(
            title="Обои для чата",
            filetypes=[("Картинки", "*.png *.jpg *.jpeg *.bmp"),
                       ("Все файлы", "*.*")], parent=self)
        if not path:
            return
        if self._store_wallpaper(path):
            self._apply()

    def _wallpaper_from_url(self) -> None:
        url = ctk.CTkInputDialog(text="Ссылка на картинку (https://…):",
                                 title="Обои из интернета").get_input()
        if not url:
            return
        try:
            ensure_dirs()
            name = f"wall_{int(time.time())}.img"
            target = os.path.join(WALLPAPER_DIR, name)
            req = urllib.request.Request(url, headers={"User-Agent": "Omega/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp, \
                    open(target, "wb") as f:
                data = resp.read(8 * 1024 * 1024)
                f.write(data)
            if not self._store_wallpaper(target):
                raise RuntimeError("файл не похож на картинку")
            self._apply()
        except Exception as e:
            messagebox.showerror("Обои", f"Не удалось скачать картинку:\n{e}",
                                 parent=self)

    def _store_wallpaper(self, path: str) -> bool:
        if not PIL_OK:
            messagebox.showerror("Обои", "Для обоев нужен Pillow "
                                          "(pip install pillow).", parent=self)
            return False
        try:
            ensure_dirs()
            target = os.path.join(WALLPAPER_DIR, f"wall_{int(time.time())}.png")
            Image.open(path).convert("RGB").save(target, "PNG")
            self.settings.wallpaper = target
            return True
        except Exception as e:
            messagebox.showerror("Обои", f"Не удалось открыть файл:\n{e}",
                                 parent=self)
            return False

    def _clear_wallpaper(self) -> None:
        self.settings.wallpaper = ""
        self._apply()

    def _set_dim(self, value) -> None:
        self.settings.wallpaper_dim = int(value)
        self.settings.save()
        self.app.refresh_chat_style()

    def _set_font(self, family: str) -> None:
        self.settings.font_family = family
        self._apply()

    def _set_font_scale(self, value) -> None:
        self.settings.font_scale = int(value)
        self._apply()

    def _set_logo(self, title: str) -> None:
        for key, (t, _) in LOGO_STYLES.items():
            if t == title:
                self.settings.logo_style = key
        self._apply()

    def _toggle_ticks(self) -> None:
        self.settings.show_ticks = bool(self.ticks_var.get())
        self._apply()

    def _apply(self) -> None:
        self.settings.save()
        self.app.apply_ui_settings()

    # ---------------------------- о программе -------------------------
    def _page_about(self) -> None:
        self._title("О программе")
        fp = self.app.my_fingerprint()
        info = [
            ("Версия", "OMEGA 1.2"),
            ("Ник", self.app.username),
            ("Сервер", self.app.server_uri),
            ("Ваш отпечаток ключа", fp),
            ("Данные", self.app.data_dir),
            ("Шифрование", "RSA-OAEP (SHA-256) + AES-256-GCM"),
        ]
        for name, value in info:
            block = ctk.CTkFrame(self.content, fg_color=self.theme.bg_input,
                                 corner_radius=10)
            block.pack(fill="x", padx=24, pady=4)
            ctk.CTkLabel(block, text=name, text_color=self.theme.text_dim,
                         anchor="w", font=self.settings.font(10)).pack(
                fill="x", padx=12, pady=(8, 0))
            ctk.CTkLabel(block, text=str(value), text_color=self.theme.text,
                         anchor="w", font=self.settings.font(12),
                         wraplength=420, justify="left").pack(
                fill="x", padx=12, pady=(0, 8))
        ctk.CTkButton(self.content, text="Открыть папку данных", height=36,
                      corner_radius=8, fg_color="transparent", border_width=1,
                      text_color=self.theme.text,
                      command=self._open_data_dir).pack(anchor="w", padx=24,
                                                        pady=12)

    def _open_data_dir(self) -> None:
        try:
            os.startfile(self.app.data_dir)      # noqa: S606 - Windows
        except Exception:
            pass
