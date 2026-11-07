"""Модуль шифрования для Омега-мессенджера.

Гибридная схема RSA-OAEP(SHA-256) + AES-256-GCM:
  * RSA шифрует одноразовый AES-ключ (32 байта);
  * AES-GCM шифрует тело сообщения любого размера.
"""
import os
import base64
import json
import hashlib

from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

RSA_KEY_SIZE = 2048
AES_KEY_SIZE = 32
AES_NONCE_SIZE = 12
MAX_TEXT_BYTES = 512 * 1024  # 512 КБ — мягкий лимит на текст


class KeyPair:
    """Пара RSA-ключей пользователя."""

    def __init__(self):
        self.private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=RSA_KEY_SIZE
        )
        self.public_key = self.private_key.public_key()

    # --- Сохранение/загрузка ---
    def export_dict(self) -> dict:
        pem = self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return {"private_key_pem": base64.b64encode(pem).decode()}

    @classmethod
    def import_from_dict(cls, data: dict) -> "KeyPair":
        obj = cls.__new__(cls)
        pem = base64.b64decode(data["private_key_pem"])
        obj.private_key = serialization.load_pem_private_key(pem, password=None)
        obj.public_key = obj.private_key.public_key()
        return obj

    # --- Публичный ключ (PEM-строка) ---
    def export_public(self) -> str:
        pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return pem.decode()

    @staticmethod
    def import_public(pem_str: str):
        return serialization.load_pem_public_key(pem_str.encode())


# --- Примитивы ---
def rsa_encrypt(public_key, data: bytes) -> bytes:
    return public_key.encrypt(
        data,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )


def rsa_decrypt(private_key, data: bytes) -> bytes:
    return private_key.decrypt(
        data,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )


def aes_encrypt(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    """AES-256-GCM. Возвращает nonce || ciphertext(+tag)."""
    nonce = os.urandom(AES_NONCE_SIZE)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def aes_decrypt(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    nonce, ct = blob[:AES_NONCE_SIZE], blob[AES_NONCE_SIZE:]
    return AESGCM(key).decrypt(nonce, ct, aad)


# --- API сообщений ---
def encrypt_message(keys: KeyPair, recipient_pub, text: str) -> str:
    """Гибридное шифрование. Возвращает JSON-строку payload."""
    raw = text.encode("utf-8")
    if len(raw) > MAX_TEXT_BYTES:
        raise ValueError(f"Сообщение слишком длинное (>{MAX_TEXT_BYTES} байт)")

    aes_key = os.urandom(AES_KEY_SIZE)
    ciphertext = aes_encrypt(aes_key, raw)
    enc_key = rsa_encrypt(recipient_pub, aes_key)
    return json.dumps({
        "k": base64.b64encode(enc_key).decode(),
        "d": base64.b64encode(ciphertext).decode(),
    })


def decrypt_message(private_key, payload_json: str) -> str:
    payload = json.loads(payload_json)
    enc_key = base64.b64decode(payload["k"])
    ciphertext = base64.b64decode(payload["d"])
    aes_key = rsa_decrypt(private_key, enc_key)
    return aes_decrypt(aes_key, ciphertext).decode("utf-8")


def fingerprint(public_key) -> str:
    """
    Отпечаток публичного ключа: SHA-256 от DER (каноническое представление),
    разбитый на группы по 4 hex-символа.
    Пример: 'A3F2 9B1C 7E4D 0A8F 2C6B 5D9E 1F3A 7C8B'
    """
    der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    digest = hashlib.sha256(der).hexdigest().upper()
    return " ".join(digest[i:i + 4] for i in range(0, len(digest), 4))

