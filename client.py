"""Омега-клиент: интерфейс в стиле Telegram + E2E + TOFU Trust Store.

Сетевой протокол и шифрование остались прежними (см. _connect/_handle ниже):
изменилась только визуальная часть и структура виджетов.
"""
import argparse
import asyncio
import json
import os
import shutil
import socket
import sys
import threading
import time
import traceback
import uuid
from datetime import date, datetime, timedelta
from tkinter import filedialog, messagebox
from urllib.parse import urlparse

import customtkinter as ctk
import websockets

from config import app_dir, data_dir, load_config, save_config
from crypto import KeyPair, encrypt_message, decrypt_message, fingerprint
from theme import (PRESETS, Settings, avatar_path, ensure_dirs)
from trust_store import TrustStore
from ui_components import (Avatar, ChatRow, ChatView, ContactRow, EmptyState,
                           Logo, SearchBox, TabBar)
from settings_window import SettingsWindow

try:                       # Pillow — для аватарок и обоев
    from PIL import Image
    PIL_OK = True
except Exception:
    PIL_OK = False

SERVER_URI = load_config().get("server_url", "ws://127.0.0.1:8080/ws")
KEY_DIR = data_dir()

RECONNECT_MAX_DELAY = 30
WS_PING_INTERVAL = 20
WS_PING_TIMEOUT = 10

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class OmegaClient(ctk.CTk):
    def __init__(self, username: str, server_uri: str | None = None):
        super().__init__()
        self.username = username
        self.server_uri = server_uri or SERVER_URI
        self.data_dir = data_dir()

        # --- Состояние ---
        self.pubkeys: dict[str, object] = {}
        self.history: dict[str, list[dict]] = {}
        self.unread: dict[str, int] = {}
        self.online_users: set[str] = set()
        self.last_seen: dict[str, float] = {}
        self.current_chat: str | None = None
        self.tab = "chats"
        self._seen_ids: set[str] = set()
        self._last_date = None
        self._settings_window = None
        self.ws = None
        self.loop = asyncio.new_event_loop()
        self._abort = False
        self._closing = False

        # --- Оформление ---
        ensure_dirs()
        self.settings = Settings.load()
        self.theme = self.settings.resolved_theme()

        # --- Ключи / доверие / история ---
        self.keys = self._load_or_create_keys()
        self.trust = TrustStore(os.path.join(KEY_DIR, f"{self.username}_trust.json"))
        self.history = self._load_history()

        self.title(f"OMEGA — {self.username}")
        self.geometry("1120x720")
        self.minsize(900, 560)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.report_callback_exception = self._on_tk_error

        self._build_ui()
        self._start_network()

    def _on_tk_error(self, exc, val, tb) -> None:
        """Не засорять консоль безвредным шумом Tk при пересборке виджетов."""
        text = str(val)
        if "invalid command name" in text or "bad window path" in text:
            return
        print("".join(traceback.format_exception(exc, val, tb)), file=sys.stderr)

    # ================= Persistence =================
    def _load_or_create_keys(self) -> KeyPair:
        path = os.path.join(KEY_DIR, f"{self.username}_keys.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return KeyPair.import_from_dict(json.load(f))
            except Exception as e:
                print("Не удалось загрузить ключи:", e)
        keys = KeyPair()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(keys.export_dict(), f)
        return keys

    def _load_history(self) -> dict[str, list[dict]]:
        path = os.path.join(KEY_DIR, f"{self.username}_history.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_history(self) -> None:
        path = os.path.join(KEY_DIR, f"{self.username}_history.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False)
        except Exception as e:
            print(f"history save error: {e}")

    # ================= UI: каркас =================
    def _build_ui(self) -> None:
        t = self.theme = self.settings.resolved_theme()
        self.configure(fg_color=t.bg_chat)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_chat_panel()
        self._refresh_list()
        self._refresh_header()
        self._update_title()

    def _build_sidebar(self) -> None:
        t = self.theme
        s = self.settings

        sidebar = ctk.CTkFrame(self, width=330, corner_radius=0,
                               fg_color=t.bg_sidebar)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(3, weight=1)

        # 1. Логотип
        logo_holder = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo_holder.grid(row=0, column=0, pady=(14, 6))
        Logo(logo_holder, s, size=28).pack()

        # 2. Поиск
        self.search = SearchBox(sidebar, s, t, self._on_search)
        self.search.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))

        # 3. Вкладки
        self.tabs = TabBar(
            sidebar,
            [("chats", "Чаты"), ("contacts", "Контакты"),
             ("calls", "Звонки"), ("settings", "Настройки")],
            self._on_tab, s, t)
        self.tabs.grid(row=2, column=0, sticky="ew", padx=10)
        self.tabs.set_active(self.tab, t)

        # 4. Список
        self.list_frame = ctk.CTkScrollableFrame(
            sidebar, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=t.bg_sidebar,
            scrollbar_button_hover_color=t.hover)
        self.list_frame.grid(row=3, column=0, sticky="nsew", padx=6, pady=(6, 0))

        # 5. Профиль (внизу)
        profile = ctk.CTkFrame(sidebar, fg_color=t.bg_header, corner_radius=0,
                               height=64)
        profile.grid(row=4, column=0, sticky="ew")
        profile.grid_propagate(False)
        profile.grid_columnconfigure(1, weight=1)

        self.profile_avatar = Avatar(profile, self.username, size=36,
                                     font=self.settings.font(13, True))
        self.profile_avatar.grid(row=0, column=0, rowspan=2,
                                 padx=(12, 10), pady=14)
        self.profile_name = ctk.CTkLabel(
            profile, text=self.username, anchor="w", text_color=t.text,
            font=self.settings.font(12, bold=True))
        self.profile_name.grid(row=0, column=1, sticky="w", pady=(12, 0))
        self.profile_status = ctk.CTkLabel(
            profile, text=self.settings.status or "в сети",
            anchor="w", text_color=t.text_dim,
            font=self.settings.font(10))
        self.profile_status.grid(row=1, column=1, sticky="w", pady=(0, 12))

        ctk.CTkButton(profile, text="\u2699", width=34, height=34,
                      corner_radius=17, fg_color="transparent",
                      hover_color=t.hover, text_color=t.text_dim,
                      font=(self.settings.font_family, 16),
                      command=lambda: self.open_settings("profile")
                      ).grid(row=0, column=2, rowspan=2, padx=(0, 12))

    def _build_chat_panel(self) -> None:
        t = self.theme
        s = self.settings

        chat = ctk.CTkFrame(self, fg_color=t.bg_chat, corner_radius=0)
        chat.grid(row=0, column=1, sticky="nsew")
        chat.grid_columnconfigure(0, weight=1)
        chat.grid_rowconfigure(1, weight=1)

        # Шапка чата
        header = ctk.CTkFrame(chat, height=64, corner_radius=0,
                              fg_color=t.bg_header)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)

        self.header_avatar = Avatar(header, "?", size=38,
                                    font=s.font(14, True))
        self.header_avatar.grid(row=0, column=0, padx=(14, 10), pady=13)

        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.grid(row=0, column=1, sticky="w")
        self.chat_title = ctk.CTkLabel(
            titles, text="Выберите чат", anchor="w", text_color=t.text,
            font=s.font(15, bold=True))
        self.chat_title.pack(anchor="w")
        self.chat_status = ctk.CTkLabel(
            titles, text="", anchor="w", text_color=t.text_dim,
            font=s.font(11))
        self.chat_status.pack(anchor="w")

        self.fp_button = ctk.CTkButton(
            header, text="\U0001F511", width=36, height=32, corner_radius=8,
            fg_color="transparent", hover_color=t.hover,
            text_color=t.text_dim, font=(s.font_family, 15),
            command=self._show_fingerprint, state="disabled")
        self.fp_button.grid(row=0, column=2, padx=(0, 12))

        # Лента
        self.chat_view = ChatView(chat, self.settings, t)
        self.chat_view.grid(row=1, column=0, sticky="nsew")
        self.chat_view.show_empty("Выберите чат слева, чтобы начать переписку")

        # Ввод
        bottom = ctk.CTkFrame(chat, fg_color=t.bg_header, corner_radius=0,
                              height=64)
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.grid_propagate(False)
        bottom.grid_columnconfigure(0, weight=1)

        self.msg_entry = ctk.CTkEntry(
            bottom, height=40, corner_radius=18, fg_color=t.bg_input,
            border_width=0, placeholder_text="Написать сообщение...",
            placeholder_text_color=t.text_dim, text_color=t.text,
            font=s.font(13))
        self.msg_entry.grid(row=0, column=0, sticky="ew", padx=(14, 8), pady=12)
        self.msg_entry.bind("<Return>", lambda e: self.send_message())

        ctk.CTkButton(bottom, text="\u27A4", width=40, height=40,
                      corner_radius=20, fg_color=t.accent,
                      hover_color=t.active, text_color="#ffffff",
                      font=(s.font_family, 16),
                      command=self.send_message).grid(row=0, column=1,
                                                      padx=(0, 14), pady=12)

    def _rebuild_ui(self) -> None:
        """Пересобрать интерфейс после смены темы/шрифта."""
        import tkinter as tk
        for w in list(self.winfo_children()):
            if isinstance(w, (tk.Toplevel, ctk.CTkToplevel)):
                continue            # окно настроек не трогаем
            try:
                w.destroy()
            except Exception:
                pass
        self._build_ui()
        if self.current_chat:
            self._render_history(self.current_chat)

    def apply_ui_settings(self) -> None:
        self.settings.save()
        self._rebuild_ui()

    def refresh_chat_style(self) -> None:
        """Обновить только ленту (например, при ползунке затемнения)."""
        try:
            self.chat_view.apply_theme(self.settings.resolved_theme(), self.settings)
            if self.current_chat:
                self._render_history(self.current_chat)
        except Exception:
            pass

    # ================= UI: левый список =================
    def _on_tab(self, key: str) -> None:
        self.tab = key
        self.tabs.set_active(key, self.theme)
        if key == "settings":
            self._fill_settings_tab()
            return
        self._refresh_list()

    def _on_search(self, _query: str) -> None:
        if self.tab in ("chats", "contacts"):
            self._refresh_list()

    def _schedule_list_refresh(self) -> None:
        """Пересобрать список один раз, даже если пришла пачка сообщений."""
        if getattr(self, "_refresh_job", None):
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
        self._refresh_job = self.after(60, self._run_scheduled_refresh)

    def _run_scheduled_refresh(self) -> None:
        self._refresh_job = None
        self._refresh_list()

    def _refresh_list(self) -> None:
        if not hasattr(self, "list_frame"):
            return
        for w in self.list_frame.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass
        query = self.search.get() if hasattr(self, "search") else ""
        if self.tab == "chats":
            self._fill_chats(query)
        elif self.tab == "contacts":
            self._fill_contacts(query)
        elif self.tab == "calls":
            EmptyState(self.list_frame, "Звонков пока нет",
                       "Голосовые и видеозвонки появятся в следующей версии.",
                       self.settings, self.theme, icon="\U0001F4DE").pack(
                fill="x", pady=40)
        elif self.tab == "settings":
            self._fill_settings_tab()

    def _last_message(self, peer: str):
        msgs = [r for r in self.history.get(peer, [])
                if r.get("sender") != "__system__"]
        return msgs[-1] if msgs else None

    def _fill_chats(self, query: str) -> None:
        entries = []
        for peer in self.history:
            last = self._last_message(peer)
            if last is None:
                continue
            entries.append((peer, last))
        entries.sort(key=lambda x: x[1].get("ts") or 0, reverse=True)

        shown = 0
        for peer, last in entries:
            text = last.get("text", "")
            if query and query not in peer.lower() and query not in text.lower():
                continue
            preview = ("Вы: " if last.get("sender") == self.username else "") + text
            tick = ""
            if last.get("sender") == self.username:
                tick = {"sent": "\u2713\u2713", "queued": "\U0001F552"}.get(
                    last.get("status", ""), "")
            ChatRow(
                self.list_frame, peer, preview,
                time_text=self._short_time(last.get("ts")),
                settings=self.settings, theme=self.theme,
                on_click=self.open_chat,
                unread=self.unread.get(peer, 0),
                online=peer in self.online_users,
                active=peer == self.current_chat,
                tick=tick,
            ).pack(fill="x", pady=2, padx=2)
            shown += 1

        if not shown:
            EmptyState(
                self.list_frame,
                "Пока нет чатов" if not query else "Ничего не найдено",
                "Откройте вкладку «Контакты» и напишите кому-нибудь.",
                self.settings, self.theme, icon="\U0001F4AC").pack(
                fill="x", pady=40)

    def _fill_contacts(self, query: str) -> None:
        known = set(self.online_users) | set(self.pubkeys) | set(self.history)
        try:
            known |= set(self.trust.data)
        except Exception:
            pass
        known.discard(self.username)

        shown = 0
        for peer in sorted(known, key=lambda u: (u not in self.online_users,
                                                 u.lower())):
            if query and query not in peer.lower():
                continue
            text, _color = self._peer_status(peer)
            ContactRow(self.list_frame, peer, text, self.settings, self.theme,
                       on_click=self.open_chat,
                       online=peer in self.online_users).pack(
                fill="x", pady=1, padx=2)
            shown += 1

        if not shown:
            EmptyState(
                self.list_frame,
                "Пока никого нет" if not query else "Не найдено",
                "Как только кто-то войдёт в сеть, он появится в списке.",
                self.settings, self.theme, icon="\U0001F465").pack(
                fill="x", pady=40)

    def _fill_settings_tab(self) -> None:
        for w in self.list_frame.winfo_children():
            w.destroy()
        t, s = self.theme, self.settings
        block = ctk.CTkFrame(self.list_frame, fg_color="transparent")
        block.pack(fill="x", pady=10, padx=4)
        for title, subtitle, page in (
            ("Профиль", "Ник, статус и аватар", "profile"),
            ("Оформление", "Тема, шрифт, обои, галочки", "appearance"),
            ("О программе", "Версия, отпечаток ключа, папка данных", "about"),
        ):
            card = ctk.CTkFrame(block, fg_color=t.bg_input, corner_radius=12)
            card.pack(fill="x", pady=4)
            ctk.CTkLabel(card, text=title, anchor="w", text_color=t.text,
                         font=s.font(13, bold=True)).pack(
                fill="x", padx=14, pady=(10, 0))
            ctk.CTkLabel(card, text=subtitle, anchor="w", text_color=t.text_dim,
                         font=s.font(10)).pack(fill="x", padx=14, pady=(0, 10))
            for w in card.winfo_children():
                w.bind("<Button-1>", lambda e, p=page: self.open_settings(p))
            card.bind("<Button-1>", lambda e, p=page: self.open_settings(p))

    # ================= UI: шапка и статусы =================
    def _peer_status(self, peer: str) -> tuple[str, str]:
        t = self.theme
        if peer in self.online_users:
            return "в сети", t.online
        ts = self.last_seen.get(peer)
        if ts:
            mins = int((time.time() - ts) / 60)
            if mins < 1:
                return "был(а) только что", t.text_dim
            if mins < 60:
                return f"был(а) {mins} мин назад", t.text_dim
            return "был(а) " + time.strftime("%H:%M", time.localtime(ts)), t.text_dim
        return "не в сети", t.text_dim

    def _refresh_header(self) -> None:
        if not hasattr(self, "chat_title"):
            return
        peer = self.current_chat
        if not peer:
            self.chat_title.configure(text="Выберите чат")
            self.chat_status.configure(text="")
            self.header_avatar.grid_remove()
            self.fp_button.configure(state="disabled")
            return
        self.header_avatar.grid()
        self.header_avatar.set_name(peer)
        self.header_avatar.set_image(avatar_path(peer))
        self.chat_title.configure(text=peer)
        text, color = self._peer_status(peer)
        self.chat_status.configure(text=text, text_color=color)
        self.fp_button.configure(state="normal")

    def _update_title(self) -> None:
        total = sum(self.unread.values())
        suffix = f"  ({total})" if total else ""
        self.title(f"OMEGA — {self.username}{suffix}")

    def _short_time(self, ts) -> str:
        if not ts:
            return ""
        d = datetime.fromtimestamp(ts)
        today = date.today()
        if d.date() == today:
            return d.strftime("%H:%M")
        if d.date() == today - timedelta(days=1):
            return "вчера"
        return d.strftime("%d.%m")

    def _date_label(self, d: date) -> str:
        today = date.today()
        if d == today:
            return "Сегодня"
        if d == today - timedelta(days=1):
            return "Вчера"
        if d.year == today.year:
            return f"{d.day} {MONTHS[d.month - 1]}"
        return d.strftime("%d.%m.%Y")

    # ================= Чат =================
    def open_chat(self, peer: str) -> None:
        self.current_chat = peer
        self.unread.pop(peer, None)
        self._refresh_header()
        self._render_history(peer)
        self._refresh_list()
        self._update_title()
        if hasattr(self, "msg_entry"):
            self.msg_entry.focus_set()
        if peer not in self.pubkeys and self.ws:
            asyncio.run_coroutine_threadsafe(self._request_pubkey(peer), self.loop)

    def _is_read(self, peer: str, rec: dict) -> bool:
        """Эмуляция «прочитано»: собеседник был активен после нашего сообщения."""
        if rec.get("sender") != self.username or not self.settings.read_ticks:
            return False
        ts = rec.get("ts") or 0
        return any(r.get("sender") == peer and (r.get("ts") or 0) > ts
                   for r in self.history.get(peer, []))

    def _render_history(self, peer: str) -> None:
        if not hasattr(self, "chat_view"):
            return
        self.chat_view.clear()
        self._last_date = None
        records = self.history.get(peer, [])
        if not records:
            self.chat_view.show_empty("Сообщений пока нет — напишите первым")
            return
        for rec in records:
            self._add_record_widget(peer, rec)
        self.chat_view.scroll_bottom()

    def _add_record_widget(self, peer: str, rec: dict) -> None:
        ts = rec.get("ts") or 0
        if ts:
            d = date.fromtimestamp(ts)
            if d != self._last_date:
                self.chat_view.add_date(self._date_label(d))
                self._last_date = d
        self.chat_view.add_message(rec, self.username,
                                   read=self._is_read(peer, rec))

    def _append_record(self, peer: str, rec: dict) -> None:
        if self.current_chat != peer or not hasattr(self, "chat_view"):
            return
        self._add_record_widget(peer, rec)
        self.chat_view.scroll_bottom()

    # ================= Отправка =================
    def send_message(self) -> None:
        if not self.current_chat:
            messagebox.showwarning("Внимание", "Выберите чат слева!", parent=self)
            return
        target = self.current_chat
        text = self.msg_entry.get().strip()
        if not text:
            return

        pk = self._get_peer_pubkey(target)
        if pk is None:
            if self.ws:
                asyncio.run_coroutine_threadsafe(
                    self._request_pubkey(target), self.loop)
            messagebox.showinfo(
                "Подождите",
                f"Ключ для «{target}» не подтверждён.\n"
                f"Запрашиваю ключ, подтвердите отпечаток.", parent=self)
            return

        if not self.ws:
            messagebox.showerror("Ошибка", "Нет соединения с сервером", parent=self)
            return

        rec = {"sender": self.username, "text": text, "ts": time.time(),
               "trusted": True, "status": "pending",
               "local_id": uuid.uuid4().hex[:12]}
        self.history.setdefault(target, []).append(rec)
        self._save_history()
        self._append_record(target, rec)
        self.msg_entry.delete(0, "end")
        self._refresh_list()

        asyncio.run_coroutine_threadsafe(
            self._async_send(target, text, pk, rec["local_id"]), self.loop)

    def _get_peer_pubkey(self, user: str):
        if user in self.pubkeys:
            return self.pubkeys[user]
        pk = self.trust.load_pubkey(user)
        if pk is not None:
            self.pubkeys[user] = pk
        return pk

    # ================= Сеть (логика без изменений) =================
    def _start_network(self) -> None:
        threading.Thread(target=self._run_loop, daemon=True).start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._connect())
        except Exception as e:
            self._ui(lambda e=e: self._set_status(f"Сеть: {e}", "red"))

    async def _connect(self) -> None:
        attempt = 0
        while not self._abort and not self._closing:
            try:
                async with websockets.connect(
                    self.server_uri,
                    ping_interval=WS_PING_INTERVAL,
                    ping_timeout=WS_PING_TIMEOUT,
                    max_size=2 * 1024 * 1024,
                ) as ws:
                    self.ws = ws
                    await ws.send(json.dumps({
                        "action": "register",
                        "username": self.username,
                        "pubkey": self.keys.export_public(),
                    }))
                    attempt = 0
                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        await self._handle(data)

                    if ws.close_code == 4001:
                        self._abort = True
                        self._ui(lambda: (
                            self._set_status("Сеанс открыт в другом окне", "orange"),
                            messagebox.showwarning(
                                "Вход",
                                "Выполнен вход с другого устройства.\n"
                                "Это окно отключено от сервера.",
                                parent=self)))
                        return
            except websockets.exceptions.ConnectionClosed:
                self._ui(lambda: self._set_status("Соединение закрыто", "orange"))
            except Exception as e:
                if self._abort:
                    return
                self._ui(lambda e=e: self._set_status(f"Нет связи: {e}", "red"))

            if self._abort or self._closing:
                return
            delay = min(RECONNECT_MAX_DELAY, 2 ** attempt)
            self._ui(lambda d=delay: self._set_status(
                f"Переподключение через {d} с...", "orange"))
            await asyncio.sleep(delay)
            attempt += 1

    async def _handle(self, data: dict) -> None:
        t = data.get("type")

        if t == "registered":
            self._ui(lambda: self._set_status(
                f"В сети как {self.username}", "green"))

        elif t == "users":
            users = [u for u in data.get("list", []) if u != self.username]
            online = {u for u in data.get("online", users) if u != self.username}

            def _apply(u=users, o=online):
                for peer in self.online_users - o:
                    self.last_seen[peer] = time.time()
                self.online_users = o
                self._refresh_list()
                self._refresh_header()
            self._ui(_apply)

        elif t == "sent":
            self._on_sent(data)

        elif t == "pubkey":
            await self._on_pubkey(data)

        elif t == "message":
            await self._on_message(data)

        elif t == "error":
            text = data.get("text", "")
            if "закреплён" in text or "занято" in text.lower():
                self._abort = True
                self._ui(lambda t=text: messagebox.showerror(
                    "Не удалось войти", t, parent=self))
                self._ui(self.destroy)
            else:
                self._ui(lambda t=text: self._set_status(f"Сервер: {t}", "orange"))

    async def _on_pubkey(self, data: dict) -> None:
        user = data.get("username")
        pem = data.get("pubkey")
        if not user or not pem:
            return
        try:
            pk = KeyPair.import_public(pem)
            fp = fingerprint(pk)
        except Exception as e:
            print(f"Плохой pubkey от {user}: {e}")
            return

        status = self.trust.check(user, fp)
        if status == "same":
            self.pubkeys[user] = pk
            self._ui(self._schedule_list_refresh)
        elif status == "new":
            self._ui(lambda u=user, f=fp, p=pem: self._prompt_new_key(u, f, p))
        else:
            old_fp = (self.trust.get(user) or {}).get("fingerprint", "?")
            self._ui(lambda u=user, o=old_fp, f=fp, p=pem:
                     self._prompt_changed_key(u, o, f, p))

    def _prompt_new_key(self, user: str, fp: str, pem: str) -> None:
        ok = messagebox.askyesno(
            "Новый контакт",
            f"Первый ключ для «{user}»:\n\n{fp}\n\n"
            f"Сверьте отпечаток с собеседником лично или по другому каналу.\n\n"
            f"Доверять этому ключу?", parent=self)
        if ok:
            self.trust.trust(user, fp, pem)
            self.pubkeys[user] = KeyPair.import_public(pem)
            self._append_system(user, f"Ключ подтверждён: {user}")
            self._refresh_header()
            self._refresh_list()
        else:
            self.pubkeys.pop(user, None)
            self._set_status(f"Ключ {user} отклонён", "red")
            self._refresh_header()

    def _prompt_changed_key(self, user: str, old_fp: str, new_fp: str,
                            pem: str) -> None:
        ok = messagebox.askyesno(
            "КЛЮЧ БЕЗОПАСНОСТИ ИЗМЕНИЛСЯ",
            f"Ключ пользователя «{user}» изменился!\n\n"
            f"Было:\n{old_fp}\n\nСтало:\n{new_fp}\n\n"
            f"Это может быть атака MITM. Принимайте новый ключ только если "
            f"лично убедились, что отпечаток верный.\n\nПринять новый ключ?",
            parent=self, icon="warning")
        if ok:
            self.trust.trust(user, new_fp, pem)
            self.pubkeys[user] = KeyPair.import_public(pem)
            self._append_system(user, f"Ключ для {user} обновлён пользователем")
            self._refresh_header()
            self._refresh_list()
        else:
            self.pubkeys.pop(user, None)
            self.trust.untrust(user)
            self._set_status(f"Новый ключ {user} отклонён", "red")
            self._refresh_header()
            self._refresh_list()

    async def _on_message(self, data: dict) -> None:
        sender = data.get("from")
        payload = data.get("payload")
        if not sender or not payload:
            return
        mid = data.get("id")
        if mid:
            if mid in self._seen_ids:
                return
            self._seen_ids.add(mid)
            if len(self._seen_ids) > 5000:
                self._seen_ids.clear()
        ts = data.get("ts") or time.time()
        try:
            text = decrypt_message(self.keys.private_key, payload)
        except Exception as e:
            text = f"[не удалось расшифровать: {e}]"

        trusted = self.trust.is_trusted(sender)
        rec = {"sender": sender, "text": text, "ts": ts, "trusted": trusted}

        self.history.setdefault(sender, []).append(rec)
        self._save_history()

        if self.current_chat == sender:
            self._ui(lambda r=rec, s=sender: self._append_record(s, r))
            self._ui(self._refresh_header)
        else:
            self.unread[sender] = self.unread.get(sender, 0) + 1
        self._ui(self._schedule_list_refresh)
        self._ui(self._update_title)

        if sender not in self.pubkeys:
            await self._request_pubkey(sender)

    async def _request_pubkey(self, user: str) -> None:
        if self.ws:
            try:
                await self.ws.send(json.dumps(
                    {"action": "get_pubkey", "target": user}))
            except Exception:
                pass

    async def _async_send(self, target: str, text: str, pk,
                          local_id: str = "") -> None:
        try:
            payload = encrypt_message(self.keys, pk, text)
            await self.ws.send(json.dumps({
                "action": "send",
                "to": target,
                "payload": payload,
                "ts": time.time(),
                "id": local_id,
            }))
        except Exception as e:
            self._ui(lambda e=e: messagebox.showerror(
                "Ошибка", f"Не отправлено: {e}", parent=self))

    def _on_sent(self, data: dict) -> None:
        local_id = data.get("id")
        peer = data.get("to")
        if not local_id or not peer:
            return
        new_status = "sent" if data.get("delivered") else "queued"
        for rec in self.history.get(peer, []):
            if rec.get("local_id") != local_id:
                continue
            if rec.get("status") != new_status:
                rec["status"] = new_status
                self._save_history()
                if self.current_chat == peer:
                    self._render_history(peer)
                self._refresh_list()
            break

    # ================= Профиль и настройки =================
    def open_settings(self, page: str = "profile") -> None:
        try:
            if self._settings_window is not None and \
                    self._settings_window.winfo_exists():
                self._settings_window.show_page(page)
                self._settings_window.lift()
                self._settings_window.focus()
                return
        except Exception:
            pass
        self._settings_window = SettingsWindow(self, page)

    def set_status(self, text: str) -> None:
        self.settings.status = text
        self.settings.save()
        if hasattr(self, "profile_status"):
            self.profile_status.configure(text=text or "в сети")

    def set_avatar(self, source_path: str) -> bool:
        if not PIL_OK:
            return False
        try:
            ensure_dirs()
            target = avatar_path(self.username)
            img = Image.open(source_path).convert("RGB")
            img.thumbnail((256, 256))
            img.save(target, "PNG")
        except Exception as e:
            print(f"[avatar] {e}")
            return False
        self._refresh_list()
        self._refresh_header()
        if hasattr(self, "profile_avatar"):
            self.profile_avatar.set_image(target)
        return True

    def remove_avatar(self) -> None:
        path = avatar_path(self.username)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
        self._refresh_list()
        self._refresh_header()
        if hasattr(self, "profile_avatar"):
            self.profile_avatar.set_image(None)

    def request_nick_change(self, nick: str) -> None:
        cfg = load_config()
        cfg["username"] = nick
        save_config(cfg)
        self.settings.save()
        messagebox.showinfo(
            "Смена ника",
            f"Новый ник «{nick}» применится после перезапуска.\n\n"
            f"Сервер закрепляет ключ за ником, поэтому нужно войти заново.",
            parent=self)

    def restart_app(self) -> None:
        try:
            import subprocess
            subprocess.Popen([sys.executable, *sys.argv[1:]])
        except Exception as e:
            print(f"[restart] {e}")
        self._on_close()

    def my_fingerprint(self) -> str:
        try:
            return fingerprint(self.keys.public_key)
        except Exception:
            return "—"

    # ================= Служебное =================
    def _show_fingerprint(self) -> None:
        user = self.current_chat
        if not user:
            return
        entry = self.trust.get(user)
        if not entry:
            messagebox.showinfo("Отпечаток", "Ключ ещё не получен.", parent=self)
            return
        state = "доверенный" if entry.get("trusted") else "НЕ подтверждён"
        messagebox.showinfo(
            f"Ключ «{user}»",
            f"Статус: {state}\n\n{entry.get('fingerprint', '?')}\n\n"
            f"Сверьте этот отпечаток с собеседником лично "
            f"или по другому каналу связи.", parent=self)

    def _append_system(self, peer: str, text: str) -> None:
        rec = {"sender": "__system__", "text": text,
               "ts": time.time(), "trusted": True}
        self.history.setdefault(peer, []).append(rec)
        self._save_history()
        if self.current_chat == peer:
            self._append_record(peer, rec)

    def _set_status(self, text: str, color: str = "gray") -> None:
        """Короткий статус в шапке чата (сеть, ошибки)."""
        if not hasattr(self, "chat_status"):
            return
        if not self.current_chat:
            self.chat_status.configure(text=text, text_color=color)
        else:
            self.chat_status.configure(text=text, text_color=color)
            self.after(3000, self._refresh_header)

    def _ui(self, fn) -> None:
        try:
            self.after(0, fn)
        except Exception:
            pass

    def _on_close(self) -> None:
        self._closing = True
        self._save_history()
        try:
            if self.loop and self.ws:
                asyncio.run_coroutine_threadsafe(self.ws.close(), self.loop)
        except Exception:
            pass
        self.destroy()


# ======================= Окно входа =======================
class LoginDialog(ctk.CTk):
    """Окно входа: ник, адрес сервера, локальный сервер."""

    def __init__(self, cfg: dict):
        super().__init__()
        self.settings = Settings.load()
        self.theme = self.settings.resolved_theme()
        self.result: tuple[str, str, bool] | None = None
        self._server_url = cfg.get("server_url") or SERVER_URI
        self.has_local_server = _local_server_available()
        t, s = self.theme, self.settings

        self.title("OMEGA — вход")
        self.geometry("480x470" if self.has_local_server else "480x410")
        self.resizable(False, False)
        self.configure(fg_color=t.bg_sidebar)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        ctk.CTkLabel(self, text="OMEGA", text_color=t.text,
                     font=(s.font_family, 34, "bold")).pack(pady=(28, 0))
        ctk.CTkLabel(self, text="Защищённый E2E-мессенджер",
                     text_color=t.text_dim, font=s.font(12)).pack(pady=(0, 20))

        ctk.CTkLabel(self, text="Ваш ник", anchor="w", text_color=t.text_dim,
                     font=s.font(11)).pack(fill="x", padx=32)
        self.nick_entry = ctk.CTkEntry(
            self, height=38, corner_radius=10, fg_color=t.bg_input,
            border_width=0, text_color=t.text, font=s.font(13),
            placeholder_text="например, Егор")
        self.nick_entry.pack(fill="x", padx=32, pady=(4, 14))
        self.nick_entry.insert(0, cfg.get("username") or "")

        ctk.CTkLabel(self, text="Адрес сервера (WebSocket)", anchor="w",
                     text_color=t.text_dim, font=s.font(11)).pack(
            fill="x", padx=32)
        self.server_entry = ctk.CTkEntry(
            self, height=38, corner_radius=10, fg_color=t.bg_input,
            border_width=0, text_color=t.text, font=s.font(13),
            placeholder_text="ws://192.168.1.50:8080/ws")
        self.server_entry.pack(fill="x", padx=32, pady=(4, 14))
        if cfg.get("server_url"):
            self.server_entry.insert(0, cfg["server_url"])

        self.local_var = ctk.BooleanVar(value=False)
        if self.has_local_server:
            ctk.CTkCheckBox(
                self, text="Поднять сервер на этом компьютере",
                variable=self.local_var, font=s.font(11),
                text_color=t.text, fg_color=t.accent,
            ).pack(anchor="w", padx=32)

        self.error_label = ctk.CTkLabel(self, text="", text_color="#e06c6c",
                                        font=s.font(11))
        self.error_label.pack(pady=(8, 0))

        ctk.CTkButton(self, text="Войти", height=44, corner_radius=12,
                      fg_color=t.accent, hover_color=t.active,
                      text_color="#ffffff", font=s.font(14, True),
                      command=self._submit).pack(fill="x", padx=32, pady=(6, 8))

        self.bind("<Return>", lambda e: self._submit())
        self.nick_entry.focus_set()

    def _submit(self) -> None:
        nick = self.nick_entry.get().strip()
        server = self.server_entry.get().strip()

        if not nick:
            self.error_label.configure(text="Введите ник")
            return
        if len(nick) > 32 or any(c.isspace() for c in nick):
            self.error_label.configure(text="Ник: 1–32 символа, без пробелов")
            return
        if not server:
            self.error_label.configure(
                text="Введите адрес сервера (его пришлёт владелец)")
            return
        if not (server.startswith("ws://") or server.startswith("wss://")):
            self.error_label.configure(
                text="Адрес должен начинаться с ws:// или wss://")
            return
        if not server.rstrip("/").endswith("/ws"):
            server = server.rstrip("/") + "/ws"

        self.result = (nick, server,
                       bool(self.has_local_server and self.local_var.get()))
        self.destroy()


def _local_server_available() -> bool:
    base = app_dir()
    if os.path.exists(os.path.join(base, "server.py")):
        return True
    if os.path.exists(os.path.join(base, "OmegaServer.exe")):
        return True
    try:
        import importlib.util
        return importlib.util.find_spec("server") is not None
    except Exception:
        return False


def _start_local_server(server_url: str) -> None:
    try:
        import server as omega_server
    except Exception as e:                       # noqa: BLE001
        messagebox.showerror(
            "Локальный сервер недоступен",
            f"В этой сборке нет серверной части.\n\n{e}")
        return
    port = urlparse(server_url).port or 8080
    omega_server.run_in_thread(host="0.0.0.0", port=port)
    end = time.time() + 5
    while time.time() < end:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.15)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--user", help="ник, без окна входа")
    parser.add_argument("--server", help="адрес сервера, без окна входа")
    parser.add_argument("--local-server", action="store_true",
                        help="поднять сервер в этом же процессе")
    args, _ = parser.parse_known_args()
    return args


def main() -> None:
    args = _parse_args()
    cfg = load_config()

    username = (args.user or "").strip()
    server = (args.server or "").strip()
    start_local = args.local_server

    if not username:
        dialog = LoginDialog(cfg)
        dialog.mainloop()
        if not dialog.result:
            return
        username, server, start_local = dialog.result

    if start_local:
        _start_local_server(server)

    if not server:
        server = cfg.get("server_url") or SERVER_URI

    cfg["username"] = username
    cfg["server_url"] = server
    save_config(cfg)

    app = OmegaClient(username, server)
    app.mainloop()


if __name__ == "__main__":
    main()
