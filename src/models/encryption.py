"""
KwachaKeeper - Data Encryption
AES-256 encryption using pycryptodome
"""

import hashlib
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

SECRET_KEY = "kwacha-keeper-secret-key-change-in-production"


def _get_key() -> bytes:
    """Derive 32-byte AES key"""
    return hashlib.sha256(SECRET_KEY.encode()).digest()


def encrypt(text: str) -> str:
    """Encrypt with AES-256-CBC"""
    if not text:
        return text
    key = _get_key()
    iv = b'\x00' * 16  # In production, use random IV per record
    cipher = AES.new(key, AES.MODE_CBC, iv)
    encrypted = cipher.encrypt(pad(text.encode(), AES.block_size))
    return base64.urlsafe_b64encode(iv + encrypted).decode()


def decrypt(encrypted_text: str) -> str:
    """Decrypt AES-256-CBC"""
    if not encrypted_text:
        return encrypted_text
    try:
        key = _get_key()
        data = base64.urlsafe_b64decode(encrypted_text.encode())
        iv = data[:16]
        ciphertext = data[16:]
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)
        return decrypted.decode()
    except Exception:
        return encrypted_text
