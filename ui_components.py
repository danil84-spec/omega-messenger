"""Визуальные компоненты OMEGA в стиле Telegram Desktop.

Только оформление: здесь нет ни сети, ни шифрования.
"""
from __future__ import annotations

import hashlib
import os
import tkinter as tk

import customtkinter as ctk

from theme import Theme, avatar_path

try:                       # Pillow нужен для аватарок-картинок и обоев
    from PIL import Image, ImageEnhance, ImageTk
    PIL_OK = True
except Exception:          # pragma: no cover - без Pillow интерфейс работает
    PIL_OK = False

AVATAR_PALETTE = [
    "#e17076", "#7bc862", "#e5ca77", "#65aadd", "#a695e7",
    "#ee7aae", "#6ec9cb", "#faa774", "#5e9fd8", "#c48ad6",
]


def avatar_color(name: str) -> str:
    h = int(hashlib.md5((name or "?").encode("utf-8")).hexdigest(), 16)
    return AVATAR_PALETTE[h % len(AVATAR_PALETTE)]


def initials(name: str) -> str:
    name = (name or "?").strip()
    return name[0].upper() if name else "?"


def _circular_image(path: str, size: int):
    """Круглая картинка нужного размера (или None, если не вышло)."""
    if not PIL_OK or not path or not os.path.exists(path):
        return None
    try:
        img = Image.open(path).convert("RGB")
        img = img.resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size * 4, size * 4), 0)
        from PIL import ImageDraw
        ImageDraw.Draw(mask).ellipse((0, 0, size * 4, size * 4), fill=255)
        mask = mask.resize((size, size), Image.LANCZOS)
        out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        out.paste(img, (0, 0), mask)
        return out
    except Exception as e:
        print(f"[avatar] не удалось открыть {path}: {e}")
        return None


class Avatar(ctk.CTkFrame):
    """Круглый аватар: картинка или цветной круг с инициалом."""

    def __init__(self, master, name: str, size: int = 40, font=None,
                 image_path: str | None = None):
        super().__init__(master, width=size, height=size,
                         corner_radius=size // 2, fg_color=avatar_color(name))
        self.grid_propagate(False)
        self.pack_propagate(False)
        self._size = size
        self._name = name
        self._photo = None
        self._label = ctk.CTkLabel(
            self, text=initials(name), text_color="#ffffff",
            font=font or ("Segoe UI", max(10, int(size * 0.42)), "bold"))
        self._label.place(relx=0.5, rely=0.5, anchor="center")
        if image_path is None:
            image_path = avatar_path(name)
        self.set_image(image_path)

    def set_name(self, name: str) -> None:
        self._name = name
        self._label.configure(text=initials(name))
        self.configure(fg_color=avatar_color(name))

    def set_image(self, path: str | None) -> None:
        img = _circular_image(path, self._size) if path else None
        if img is None:
            self._photo = None
            self._label.configure(image=None, text=initials(self._name))
            return
        try:
            self._photo = ctk.CTkImage(light_image=img, dark_image=img,
                                       size=(self._size, self._size))
            self._label.configure(image=self._photo, text="")
        except Exception as e:
            print(f"[avatar] {e}")


class Logo(ctk.CTkFrame):
    """Крупная надпись OMEGA с градиентом по буквам."""

    def __init__(self, master, settings, size: int = 30):
        super().__init__(master, fg_color="transparent")
        start, end = settings.logo_colors()
        letters = "OMEGA"
        colors = self._gradient(start, end, len(letters))
        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack()
        self._labels = []
        for ch, color in zip(letters, colors):
            lbl = ctk.CTkLabel(
                inner, text=ch, text_color=color,
                font=(settings.font_family, size, "bold"))
            lbl.pack(side="left", padx=(0, 1))
            self._labels.append(lbl)

    @staticmethod
    def _gradient(start: str, end: str, steps: int) -> list[str]:
        def rgb(h):
            h = h.lstrip("#")
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        a, b = rgb(start), rgb(end)
        out = []
        for i in range(steps):
            t = i / max(1, steps - 1)
            out.append("#%02x%02x%02x" % tuple(
                int(a[j] + (b[j] - a[j]) * t) for j in range(3)))
        return out


class SearchBox(ctk.CTkFrame):
    """Поле поиска с лупой и кнопкой очистки."""

    def __init__(self, master, settings, theme: Theme, on_change):
        super().__init__(master, fg_color=theme.bg_input, corner_radius=12,
                         height=38)
        self.grid_propagate(False)
        self._on_change = on_change
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="\U0001F50D", width=20,
                     text_color=theme.text_dim,
                     font=settings.font(12)).grid(row=0, column=0, padx=(10, 4))
        self.entry = ctk.CTkEntry(
            self, border_width=0, fg_color="transparent",
            text_color=theme.text, placeholder_text="Поиск",
            placeholder_text_color=theme.text_dim,
            font=settings.font(13))
        self.entry.grid(row=0, column=1, sticky="ew", pady=6)
        self.entry.bind("<KeyRelease>", lambda e: self._changed())
        self.clear_btn = ctk.CTkButton(
            self, text="\u2715", width=22, height=22, corner_radius=11,
            fg_color="transparent", hover_color=theme.hover,
            text_color=theme.text_dim, font=settings.font(11),
            command=self.clear)
        self.clear_btn.grid(row=0, column=2, padx=(2, 8))

    def _changed(self) -> None:
        self._show_clear(bool(self.entry.get()))
        self._on_change(self.entry.get().strip().lower())

    def _show_clear(self, show: bool) -> None:
        if show:
            self.clear_btn.grid()
        else:
            self.clear_btn.grid_remove()

    def clear(self) -> None:
        self.entry.delete(0, "end")
        self._changed()

    def get(self) -> str:
        return self.entry.get().strip().lower()


class TabBar(ctk.CTkFrame):
    """Горизонтальные вкладки: Чаты | Контакты | Звонки | Настройки."""

    def __init__(self, master, tabs: list[tuple[str, str]], on_select,
                 settings, theme: Theme):
        super().__init__(master, fg_color="transparent")
        self._on_select = on_select
        self._buttons: dict[str, ctk.CTkButton] = {}
        for i, (key, title) in enumerate(tabs):
            btn = ctk.CTkButton(
                self, text=title, height=30, corner_radius=8,
                fg_color="transparent", hover_color=theme.hover,
                text_color=theme.text_dim, font=settings.font(12, bold=True),
                command=lambda k=key: self._on_select(k))
            btn.grid(row=0, column=i, sticky="ew", padx=2, pady=2)
            self.grid_columnconfigure(i, weight=1)
            self._buttons[key] = btn

    def set_active(self, key: str, theme: Theme) -> None:
        for k, btn in self._buttons.items():
            if k == key:
                btn.configure(text_color=theme.text, fg_color=theme.active)
            else:
                btn.configure(text_color=theme.text_dim, fg_color="transparent")


class ChatRow(ctk.CTkFrame):
    """Строка списка чатов: аватар, имя, последнее сообщение, время, бейдж."""

    def __init__(self, master, name: str, preview: str, time_text: str,
                 settings, theme: Theme, on_click, unread: int = 0,
                 online: bool = False, active: bool = False, tick: str = ""):
        super().__init__(master, fg_color=theme.active if active else "transparent",
                         corner_radius=10, height=64)
        self.name = name
        self._on_click = on_click
        self._active = active
        self._theme = theme
        self.grid_propagate(False)
        self.grid_columnconfigure(1, weight=1)

        self.avatar = Avatar(self, name, size=44, font=settings.font(15, True))
        self.avatar.grid(row=0, column=0, rowspan=2, padx=(8, 10), pady=10)

        title = ctk.CTkLabel(self, text=name, anchor="w",
                             text_color=theme.text,
                             font=settings.font(13, bold=True))
        title.grid(row=0, column=1, sticky="ew", pady=(10, 0))

        preview_text = preview or "Нет сообщений"
        if len(preview_text) > 38:
            preview_text = preview_text[:37] + "…"
        self.preview = ctk.CTkLabel(
            self, text=preview_text, anchor="w",
            text_color=theme.text_dim, font=settings.font(11))
        self.preview.grid(row=1, column=1, sticky="ew", pady=(0, 10))

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=0, column=2, rowspan=2, sticky="e", padx=(4, 10))
        self.time_label = ctk.CTkLabel(
            right, text=time_text, text_color=theme.text_dim,
            font=settings.font(10))
        self.time_label.pack(anchor="e")
        self.badge = ctk.CTkLabel(
            right, text="", width=20, height=20, corner_radius=10,
            fg_color=theme.accent, text_color="#ffffff",
            font=settings.font(10, bold=True))
        self.badge.pack(anchor="e", pady=(4, 0))
        if unread > 0:
            self.badge.configure(text=str(unread) if unread < 100 else "99+")
        else:
            self.badge.pack_forget()

        if tick:
            self.tick_label = ctk.CTkLabel(
                right, text=tick, text_color=theme.text_dim,
                font=settings.font(10))
            self.tick_label.pack(anchor="e", pady=(2, 0))

        for w in (self, self.avatar, title, self.preview):
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)

    def _click(self, _e=None):
        self._on_click(self.name)

    def _enter(self, _e=None):
        if not self._active:
            self.configure(fg_color=self._theme.hover)

    def _leave(self, _e=None):
        if not self._active:
            self.configure(fg_color="transparent")

    def set_active(self, active: bool) -> None:
        self._active = active
        self.configure(fg_color=self._theme.active if active else "transparent")


class ContactRow(ctk.CTkFrame):
    """Строка списка контактов: аватар, имя, статус."""

    def __init__(self, master, name: str, status_text: str, settings,
                 theme: Theme, on_click, online: bool = False):
        super().__init__(master, fg_color="transparent", corner_radius=10,
                         height=58)
        self.name = name
        self._on_click = on_click
        self._theme = theme
        self.grid_propagate(False)
        self.grid_columnconfigure(1, weight=1)

        Avatar(self, name, size=42, font=settings.font(14, True)).grid(
            row=0, column=0, rowspan=2, padx=(8, 10), pady=8)
        title = ctk.CTkLabel(self, text=name, anchor="w", text_color=theme.text,
                             font=settings.font(13, bold=True))
        title.grid(row=0, column=1, sticky="ew", pady=(8, 0))
        sub = ctk.CTkLabel(self, text=status_text, anchor="w",
                           text_color=theme.online if online else theme.text_dim,
                           font=settings.font(11))
        sub.grid(row=1, column=1, sticky="ew", pady=(0, 8))

        for w in (self, title, sub):
            w.bind("<Button-1>", lambda e: self._on_click(self.name))
            w.bind("<Enter>", lambda e: self.configure(fg_color=theme.hover))
            w.bind("<Leave>", lambda e: self.configure(fg_color="transparent"))


class DateChip(ctk.CTkFrame):
    """Разделитель даты («Сегодня», «Вчера», «7 ноября»)."""

    def __init__(self, master, text: str, settings, theme: Theme):
        super().__init__(master, fg_color=theme.separator, corner_radius=10)
        ctk.CTkLabel(self, text=text, text_color=theme.text_dim,
                     font=settings.font(11, bold=True)).pack(
            padx=10, pady=3)
        self.update_idletasks()


class MessageBubble(ctk.CTkFrame):
    """Пузырь сообщения с временем и галочками."""

    def __init__(self, master, text: str, outgoing: bool, time_text: str,
                 settings, theme: Theme, max_px: int = 460,
                 status: str = "", system: bool = False, read: bool = False):
        if system:
            super().__init__(master, fg_color="transparent")
            ctk.CTkLabel(self, text=text, text_color=theme.text_dim,
                         font=settings.font(11), wraplength=max_px,
                         justify="center").pack(padx=6, pady=4)
            return

        bg = theme.bubble_out if outgoing else theme.bubble_in
        fg = theme.bubble_out_text if outgoing else theme.bubble_in_text
        super().__init__(master, fg_color=bg, corner_radius=14)

        self.body = ctk.CTkLabel(
            self, text=text, text_color=fg, justify="left", anchor="w",
            wraplength=max(120, max_px - 28), font=settings.font(12))
        self.body.grid(row=0, column=0, sticky="w", padx=(12, 12), pady=(7, 0))

        meta = ctk.CTkFrame(self, fg_color="transparent")
        meta.grid(row=1, column=0, sticky="e", padx=(0, 8), pady=(0, 5))
        ctk.CTkLabel(meta, text=time_text, text_color=theme.text_dim,
                     font=settings.font(10)).pack(side="left")

        self.tick_label = None
        if outgoing and settings.show_ticks and status:
            glyph, color = self._tick_view(status, read, settings, theme)
            self.tick_label = ctk.CTkLabel(
                meta, text=glyph, text_color=color,
                font=settings.font(10, bold=True))
            self.tick_label.pack(side="left", padx=(4, 0))

        self.update_idletasks()
        try:
            width = self.body.winfo_reqwidth() + 26
            self.configure(width=max(90, min(width, max_px)))
        except Exception:
            pass

    @staticmethod
    def _tick_view(status: str, read: bool, settings, theme: Theme):
        if status == "read" or (read and status == "sent" and settings.read_ticks):
            return "\u2713\u2713", theme.accent
        if status == "sent":
            return "\u2713\u2713", theme.text_dim
        if status == "queued":
            return "\U0001F552", theme.text_dim
        return "\u2026", theme.text_dim


class EmptyState(ctk.CTkFrame):
    """Заглушка для пустых вкладок (звонки и т.п.)."""

    def __init__(self, master, title: str, subtitle: str, settings,
                 theme: Theme, icon: str = "\U0001F4AC"):
        super().__init__(master, fg_color="transparent")
        ctk.CTkLabel(self, text=icon, font=(settings.font_family, 46),
                     text_color=theme.text_dim).pack(pady=(30, 6))
        ctk.CTkLabel(self, text=title, text_color=theme.text,
                     font=settings.font(14, bold=True)).pack()
        ctk.CTkLabel(self, text=subtitle, text_color=theme.text_dim,
                     font=settings.font(11), wraplength=220,
                     justify="center").pack(pady=(4, 0))


class ChatView(ctk.CTkFrame):
    """Лента сообщений на Canvas: обои на фоне, пузыри поверх.

    Canvas нужен ради обоев: обычный контейнер закрасил бы картинку сплошным
    цветом. Пузыри лежат отдельными окнами и позиционируются вручную.
    """

    MARGIN = 14
    GAP = 6
    DATE_GAP = 14

    def __init__(self, master, settings, theme: Theme):
        super().__init__(master, fg_color=theme.bg_chat, corner_radius=0)
        self.settings = settings
        self.theme = theme
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(self, bg=theme.bg_chat, highlightthickness=0,
                                bd=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ctk.CTkScrollbar(self, width=10,
                                          command=self._yview,
                                          button_color=theme.separator,
                                          button_hover_color=theme.hover)
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self._items: list[dict] = []
        self._y = 10
        self._wallpaper_item = None
        self._wallpaper_photo = None
        self._empty_item = None

        self.canvas.bind("<Configure>", lambda e: (self._relayout(),
                                                   self._draw_wallpaper()))
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.apply_theme(theme, settings)

    # ---------- обои ----------
    def apply_theme(self, theme: Theme, settings) -> None:
        self.theme = theme
        self.settings = settings
        self.canvas.configure(bg=theme.bg_chat)
        self.scrollbar.configure(button_color=theme.separator,
                                 button_hover_color=theme.hover)
        self._draw_wallpaper()

    def _draw_wallpaper(self) -> None:
        if self._wallpaper_item:
            self.canvas.delete(self._wallpaper_item)
            self._wallpaper_item = None

        path = self.settings.wallpaper
        if not (PIL_OK and path and os.path.exists(path)):
            return
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        if width < 50 or height < 50:
            return
        try:
            img = Image.open(path).convert("RGB")
            scale = max(width / img.width, height / img.height)
            img = img.resize((max(1, int(img.width * scale)),
                              max(1, int(img.height * scale))), Image.LANCZOS)
            left = (img.width - width) // 2
            top = (img.height - height) // 2
            img = img.crop((left, top, left + width, top + height))
            dim = 1.0 - max(0, min(80, self.settings.wallpaper_dim)) / 100.0
            img = ImageEnhance.Brightness(img).enhance(dim)
            self._wallpaper_photo = ImageTk.PhotoImage(img)
            self._wallpaper_item = self.canvas.create_image(
                0, 0, anchor="nw", image=self._wallpaper_photo)
            self.canvas.tag_lower(self._wallpaper_item)
        except Exception as e:
            print(f"[wallpaper] {e}")
            self._wallpaper_item = None

    def _pin_wallpaper(self) -> None:
        if self._wallpaper_item:
            self.canvas.coords(self._wallpaper_item,
                               self.canvas.canvasx(0), self.canvas.canvasy(0))

    # ---------- прокрутка ----------
    def _yview(self, *args) -> None:
        self.canvas.yview(*args)
        self._pin_wallpaper()

    def _on_wheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")
        self._pin_wallpaper()

    def _bind_wheel(self, widget) -> None:
        widget.bind("<MouseWheel>", self._on_wheel)
        for child in widget.winfo_children():
            self._bind_wheel(child)

    # ---------- содержимое ----------
    def clear(self) -> None:
        for it in self._items:
            try:
                self.canvas.delete(it["item"])
            except Exception:
                pass
            try:
                it["widget"].destroy()
            except Exception:
                pass
        self._items.clear()
        self._y = 10
        if self._empty_item:
            self.canvas.delete(self._empty_item)
            self._empty_item = None
        self._update_scrollregion()

    def show_empty(self, text: str) -> None:
        self.clear()
        width = max(200, self.canvas.winfo_width())
        self._empty_item = self.canvas.create_text(
            width // 2, 80, text=text, fill=self.theme.text_dim,
            font=(self.settings.font_family, 13), width=width - 40)

    def _add_widget(self, widget, kind: str = "msg", side: str = "in") -> None:
        widget.update_idletasks()
        item = self.canvas.create_window(0, self._y, window=widget, anchor="nw")
        self._items.append({"item": item, "widget": widget, "kind": kind,
                            "side": side})
        height = widget.winfo_reqheight()
        self._y += height + (self.DATE_GAP if kind == "date" else self.GAP)
        if self._empty_item:
            self.canvas.delete(self._empty_item)
            self._empty_item = None
        self._bind_wheel(widget)
        self._relayout()

    def add_date(self, text: str) -> None:
        chip = DateChip(self.canvas, text, self.settings, self.theme)
        self._add_widget(chip, kind="date")

    def add_message(self, rec: dict, my_name: str, read: bool = False) -> None:
        sender = rec.get("sender", "?")
        system = sender == "__system__"
        outgoing = sender == my_name
        ts = rec.get("ts") or 0
        time_text = ""
        if ts:
            import time as _t
            time_text = _t.strftime("%H:%M", _t.localtime(ts))
        text = rec.get("text", "")
        if not system and not rec.get("trusted", True) and not outgoing:
            text += "\n\u26A0 ключ не подтверждён"
        bubble = MessageBubble(
            self.canvas, text=text, outgoing=outgoing, time_text=time_text,
            settings=self.settings, theme=self.theme,
            max_px=max(240, int(self.canvas.winfo_width() * 0.68)),
            status=rec.get("status", ""), system=system, read=read)
        self._add_widget(bubble, side="out" if outgoing else "in")

    def _relayout(self) -> None:
        width = max(320, self.canvas.winfo_width())
        for it in self._items:
            widget = it["widget"]
            try:
                widget.update_idletasks()
                w = widget.winfo_reqwidth()
            except Exception:
                continue
            if it["kind"] == "date":
                x = max(0, (width - w) // 2)
            elif it["side"] == "out":
                x = max(self.MARGIN, width - w - self.MARGIN - 10)
            else:
                x = self.MARGIN
            self.canvas.coords(it["item"], x, self.canvas.coords(it["item"])[1])
        self._update_scrollregion()

    def _update_scrollregion(self) -> None:
        width = max(320, self.canvas.winfo_width())
        self.canvas.configure(scrollregion=(0, 0, width, self._y + 10))

    def scroll_bottom(self) -> None:
        self.canvas.update_idletasks()
        self._update_scrollregion()
        self.canvas.yview_moveto(1.0)
        self._pin_wallpaper()
