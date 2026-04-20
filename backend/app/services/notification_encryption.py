"""
backend/app/services/notification_encryption.py — Fernet encryption helpers for
notification credentials at rest.

All sensitive credentials stored in config_json are encrypted before saving and
decrypted after loading.  Uses the same Fernet key as BuyWander credentials.
"""

from cryptography.fernet import Fernet
from ..config import FERNET_KEY

_fernet = Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)


def encrypt_value(value: str) -> str:
    """Encrypt a single credential string. Returns the base64-encoded ciphertext."""
    if not value:
        return value
    return _fernet.encrypt(value.encode()).decode()


def decrypt_value(value: str) -> str:
    """Decrypt a credential string. Returns plaintext. Falls through if not encrypted."""
    if not value:
        return value
    try:
        return _fernet.decrypt(value.encode()).decode()
    except Exception:
        # Not a valid ciphertext — return as-is (may be empty or plain text on first read)
        return value


# Fields per channel that must be encrypted before storing in config_json
_CREDENTIAL_FIELDS = {
    "smtp": ["password"],
    "telegram": ["bot_token"],
    "pushover": ["user_key", "app_token"],
    "gotify": ["token"],
}


def encrypt_notifications(data: dict) -> dict:
    """Encrypt credential fields in the notifications sub-dict before saving."""
    import copy

    data = copy.deepcopy(data)
    notif = data.get("notifications", {})
    for channel, fields in _CREDENTIAL_FIELDS.items():
        ch = notif.get(channel, {})
        if not isinstance(ch, dict):
            continue
        for field in fields:
            val = ch.get(field, "")
            if val:  # only encrypt non-empty strings
                ch[field] = encrypt_value(str(val))
        notif[channel] = ch
    data["notifications"] = notif
    return data


def decrypt_notifications(data: dict) -> dict:
    """Decrypt credential fields in the notifications sub-dict after loading."""
    import copy

    data = copy.deepcopy(data)
    notif = data.get("notifications", {})
    for channel, fields in _CREDENTIAL_FIELDS.items():
        ch = notif.get(channel, {})
        if not isinstance(ch, dict):
            continue
        for field in fields:
            val = ch.get(field, "")
            if val:  # only attempt decryption for non-empty strings
                ch[field] = decrypt_value(str(val))
        notif[channel] = ch
    data["notifications"] = notif
    return data
