import customtkinter as ctk
import tkinter as tk
from tkinter import simpledialog, messagebox
import asyncio
import threading
import base64
import json
import websockets
import crypto

# Настройка внешнего вида (как в Telegram Dark Mode)
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class OmegaApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("OMEGA Messenger")
        self.geometry("800x600")
        
        # Запрашиваем ник
        self.user_id = simpledialog.askstring("Вход", "Введите ваш ник:")
        if not self.user_id:
            self.destroy()
            return
            
        self.priv, self.pub = crypto.generate_keypair()
        self.sessions = {}
        self._pending_keys = {}
        self.loop = asyncio.new_event_loop()
        self.ws = None
        self.current_chat = None

        # --- Создание интерфейса (как в ВК/Telegram) ---
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ЛЕВАЯ ПАНЕЛЬ: Список контактов
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        
        self.contacts_label = ctk.CTkLabel(self.sidebar, text="Чаты", font=("Arial", 18, "bold"))
        self.contacts_label.pack(pady=20, padx=10)
        
        self.btn_alice = ctk.CTkButton(self.sidebar, text="alice", command=lambda: self.open_chat("alice"))
        self.btn_alice.pack(pady=5, padx=10, fill="x")
        
        self.btn_bob = ctk.CTkButton(self.sidebar, text="bob", command=lambda: self.open_chat("bob"))
        self.btn_bob.pack(pady=5, padx=10, fill="x")

        # ПРАВАЯ ПАНЕЛЬ: Чат
        self.chat_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.chat_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.chat_frame.grid_rowconfigure(0, weight=1)
        self.chat_frame.grid_columnconfigure(0, weight=1)

        self.chat_header = ctk.CTkLabel(self.chat_frame, text="Выберите чат слева", font=("Arial", 20, "bold"))
        self.chat_header.grid(row=0, column=0, sticky="nw", pady=(0, 10))

        # История сообщений
        self.chat_area = ctk.CTkTextbox(self.chat_frame, state='disabled', wrap='word', font=("Arial", 14))
        self.chat_area.grid(row=1, column=0, sticky="nsew")

        # Поле ввода
        self.input_frame = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        self.input_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.msg_entry = ctk.CTkEntry(self.input_frame, placeholder_text="Написать сообщение...", height=40)
        self.msg_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.msg_entry.bind("<Return>", self.send_message)
        
        self.send_btn = ctk.CTkButton(self.input_frame, text="➤", width=50, height=40, command=self.send_message)
        self.send_btn.grid(row=0, column=1)

        # Запускаем асинхронный сервер в отдельном потоке
        threading.Thread(target=self.run_async_loop, daemon=True).start()

    def open_chat(self, peer):
        self.current_chat = peer
        self.chat_header.configure(text=f"Чат с {peer}")
        # Очищаем историю при переключении (для простоты)
        self.chat_area.configure(state='normal')
        self.chat_area.delete("1.0", tk.END)
        self.chat_area.configure(state='disabled')

    def log(self, text):
        self.chat_area.configure(state='normal')
        self.chat_area.insert(tk.END, text + "\n\n")
        self.chat_area.configure(state='disabled')
        self.chat_area.see(tk.END)

    def send_message(self, event=None):
        if not self.current_chat:
            messagebox.showwarning("Внимание", "Выберите чат слева!")
            return
            
        text = self.msg_entry.get().strip()
        if not text:
            return
            
        self.msg_entry.delete(0, tk.END)
        self.log(f"Вы:\n{text}")
        # Отправляем в асинхронный поток
        asyncio.run_coroutine_threadsafe(self.async_send(self.current_chat, text), self.loop)

    # --- Асинхронная логика (БЕЗ ИЗМЕНЕНИЙ, работает с вашим server.py) ---
    def run_async_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.connect())

    async def connect(self):
        try:
            # ИСПОЛЬЗУЕМ 127.0.0.1 ЧТОБЫ ИЗБЕЖАТЬ ОШИБКИ 1225
            self.ws = await websockets.connect(f"ws://127.0.0.1:8000/ws/{self.user_id}")
            await self.ws.send(json.dumps({
                "action": "register_key",
                "public_key": base64.b64encode(self.pub).decode(),
            }))
            await self.ws.recv()
            self.after(0, self.log, "✅ Подключено к серверу!")
            
            async for raw in self.ws:
                data = json.loads(raw)
                if data["action"] == "key_response":
                    fut = self._pending_keys.pop(data["target"], None)
                    if fut and not fut.done():
                        self.loop.call_soon_threadsafe(fut.set_result, data["public_key"])
                elif data["action"] == "message":
                    key = await self._get_session(data["from"])
                    text = crypto.decrypt(key, data["nonce"], data["ciphertext"])
                    # Если сообщение от того, с кем открыт чат, показываем его
                    if self.current_chat == data["from"]:
                        self.after(0, self.log, f"[{data['from']}]:\n{text}")
                    else:
                        # Если от другого - мигаем в консоли (в будущем можно добавить уведомление)
                        print(f"Новое сообщение от {data['from']}!")
        except Exception as e:
            self.after(0, self.log, f"❌ Ошибка сети: {e}")

    async def _get_session(self, peer: str) -> bytes:
        if peer in self.sessions:
            return self.sessions[peer]
        fut = self.loop.create_future()
        self._pending_keys[peer] = fut
        await self.ws.send(json.dumps({"action": "get_key", "target": peer}))
        pub_b64 = await asyncio.wait_for(fut, timeout=10)
        if not pub_b64:
            raise RuntimeError(f"Пользователь {peer} не найден")
        peer_pub = base64.b64decode(pub_b64)
        shared = crypto.derive_shared_key(self.priv, peer_pub)
        self.sessions[peer] = shared
        return shared

    async def async_send(self, peer, text):
        try:
            key = await self._get_session(peer)
            nonce_b64, ct_b64 = crypto.encrypt(key, text)
            await self.ws.send(json.dumps({
                "action": "send", "to": peer,
                "nonce": nonce_b64, "ciphertext": ct_b64,
            }))
        except Exception as e:
            self.after(0, self.log, f"❌ Не отправлено: {e}")

if __name__ == "__main__":
    app = OmegaApp()
    app.mainloop()
    