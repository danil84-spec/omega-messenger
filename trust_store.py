"""Хранилище доверенных ключей (TOFU)."""
import json
import os
import time

from crypto import KeyPair


class TrustStore:
    """
    Формат файла:
    {
      "alice": {
         "fingerprint": "A3F2 9B1C ...",
         "pubkey_pem": "<PEM-строка>",
         "trusted": true,
         "first_seen": 1730000000
      }
    }
    """

    def __init__(self, path: str):
        self.path = path
        self.data: dict[str, dict] = {}
        self._load()

    # --- IO ---
    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception as e:
                print(f"[TrustStore] load error: {e}")
                self.data = {}

    def _save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[TrustStore] save error: {e}")

    # --- API ---
    def get(self, user: str) -> dict | None:
        return self.data.get(user)

    def check(self, user: str, fingerprint: str) -> str:
        """
        'new'     — ключа ещё не было (TOFU);
        'same'    — отпечаток совпадает;
        'changed' — ОПАСНО, ключ изменился.
        """
        entry = self.data.get(user)
        if not entry:
            return "new"
        if entry.get("fingerprint") == fingerprint:
            return "same"
        return "changed"

    def trust(self, user: str, fingerprint: str, pubkey_pem: str) -> None:
        """Помечает ключ как доверенный (создаёт запись, если её не было)."""
        self.data[user] = {
            "fingerprint": fingerprint,
            "pubkey_pem": pubkey_pem,
            "trusted": True,
            "first_seen": self.data.get(user, {}).get("first_seen", time.time()),
        }
        self._save()

    def untrust(self, user: str) -> None:
        """Снимает доверие (при подозрении на MITM)."""
        entry = self.data.get(user)
        if entry:
            entry["trusted"] = False
            self._save()

    def is_trusted(self, user: str) -> bool:
        entry = self.data.get(user)
        return bool(entry and entry.get("trusted"))

    def load_pubkey(self, user: str):
        """Возвращает объект публичного ключа из доверенного хранилища или None."""
        entry = self.data.get(user)
        if not entry or not entry.get("trusted"):
            return None
        pem = entry.get("pubkey_pem")
        if not pem:
            return None
        try:
            return KeyPair.import_public(pem)
        except Exception:
            return None
        
    