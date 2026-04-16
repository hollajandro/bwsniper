"""
backend/app/services/auth_service.py — User registration, login, password hashing.
"""

from typing import Optional

import bcrypt
from sqlalchemy.orm import Session

from ..db.models import User, UserConfig

_DEFAULT_CONFIG = {
    "defaults": {"snipe_seconds": 5},
    "notifications": {
        "remind_before_seconds": 300,
        "telegram":  {"enabled": False, "bot_token": "", "chat_id": ""},
        "smtp":      {"enabled": False, "host": "smtp.gmail.com", "port": 587,
                      "username": "", "password": "", "from_addr": "", "to_addr": ""},
        "pushover":  {"enabled": False, "user_key": "", "app_token": ""},
        "gotify":    {"enabled": False, "url": "", "token": "", "priority": 5},
    },
}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def register_user(db: Session, email: str, password: str,
                  display_name: str = None) -> User:
    """Create a new app user.  Raises ValueError if email already taken.
    The very first user registered is automatically granted admin privileges.
    """
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise ValueError("Email already registered.")
    is_first = db.query(User).count() == 0
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name or email.split("@")[0],
        is_admin=is_first,
    )
    db.add(user)
    db.flush()

    # Create default config
    import json
    cfg = UserConfig(user_id=user.id, config_json=json.dumps(_DEFAULT_CONFIG))
    db.add(cfg)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """Return the User if credentials are correct, else None.

    Always runs bcrypt.checkpw regardless of whether the email exists so that
    response time is identical in both cases, preventing email enumeration via
    timing attacks.
    """
    # Constant-time dummy hash used when the user doesn't exist so we still pay
    # the full bcrypt cost and don't leak whether the email is registered.
    _DUMMY_HASH = "$2b$12$aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    user = db.query(User).filter(User.email == email).first()
    candidate_hash = user.password_hash if user else _DUMMY_HASH
    if not verify_password(password, candidate_hash):
        return None
    return user  # None if user not found (dummy hash always fails)


def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def reauth_bw_login(login, db: Session):
    """Re-authenticate a BuyWander login and persist fresh cookies.

    Works for any BuyWanderLogin record that has encrypted_password set.
    Callers should already hold a DB session; this function commits the
    cookie update before returning.

    Returns the fresh requests.Session, or raises on failure.
    """
    from ..utils.crypto import decrypt, encrypt
    from .buywander_api import create_bw_session, bw_login, serialise_cookies

    password = decrypt(login.encrypted_password)
    session = create_bw_session()
    bw_login(session, login.bw_email, password)   # raises ValueError/HTTPError on failure
    login.encrypted_cookies = encrypt(serialise_cookies(session))
    db.commit()
    return session
