"""
backend/app/utils/crypto.py — Fernet encryption for BuyWander credentials.

Credentials are encrypted at rest in the database and decrypted only when
a BuyWander API call needs to be made.
"""

from cryptography.fernet import Fernet
from ..config import FERNET_KEY

_fernet = Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)


def encrypt(plaintext: str) -> str:
    """Encrypt a string and return the base64-encoded ciphertext."""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext back to plaintext."""
    return _fernet.decrypt(ciphertext.encode()).decode()
