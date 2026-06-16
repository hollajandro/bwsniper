"""
backend/app/services/auth_service.py — User registration, login, password hashing.
"""

import json
import secrets
from typing import Optional

import bcrypt
from cryptography.fernet import InvalidToken
from sqlalchemy.orm import Session

from ..db.models import User, UserConfig

_DEFAULT_CONFIG = {
    "defaults": {"snipe_seconds": 5},
    "notifications": {
        "remind_before_seconds": 300,
        "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
        "smtp": {
            "enabled": False,
            "host": "smtp.gmail.com",
            "port": 587,
            "username": "",
            "password": "",
            "from_addr": "",
            "to_addr": "",
        },
        "pushover": {"enabled": False, "user_key": "", "app_token": ""},
        "gotify": {"enabled": False, "url": "", "token": "", "priority": 5},
    },
}


class BuyWanderCredentialDecryptError(ValueError):
    """Stored BuyWander credentials can no longer be decrypted."""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def register_user(
    db: Session, email: str, password: str, display_name: str | None = None
) -> User:
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

    cfg = UserConfig(user_id=user.id, config_json=json.dumps(_DEFAULT_CONFIG))
    db.add(cfg)
    db.commit()
    db.refresh(user)
    return user


def get_or_create_external_user(
    db: Session,
    *,
    provider: str,
    subject: str,
    email: str,
    display_name: str | None = None,
    auto_create: bool = True,
    admin_emails: set[str] | None = None,
) -> User:
    """Resolve a user authenticated by an external IdP.

    Existing internal users are linked by email the first time they arrive via
    Cloudflare Access, which gives admins a reversible migration path.
    """
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise ValueError("External identity is missing an email address.")
    if not subject:
        raise ValueError("External identity is missing a subject.")

    user = (
        db.query(User)
        .filter(User.auth_provider == provider, User.external_subject == subject)
        .first()
    )
    if user:
        changed = False
        if user.email != normalized_email:
            user.email = normalized_email
            changed = True
        if display_name and user.display_name != display_name:
            user.display_name = display_name
            changed = True
        if changed:
            db.commit()
            db.refresh(user)
        return user

    existing = db.query(User).filter(User.email == normalized_email).first()
    if existing:
        if existing.external_subject and existing.external_subject != subject:
            raise ValueError(
                "Email is already linked to a different external identity."
            )
        existing.auth_provider = provider
        existing.external_subject = subject
        if display_name and not existing.display_name:
            existing.display_name = display_name
        db.commit()
        db.refresh(existing)
        return existing

    if not auto_create:
        raise ValueError("No BwSniper user exists for this external identity.")

    admin_emails = admin_emails or set()
    is_first = db.query(User).count() == 0
    user = User(
        email=normalized_email,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        display_name=display_name or normalized_email.split("@")[0],
        is_admin=is_first or normalized_email in admin_emails,
        auth_provider=provider,
        external_subject=subject,
    )
    db.add(user)
    db.flush()

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

    try:
        password = decrypt(login.encrypted_password)
    except (InvalidToken, AttributeError, TypeError, ValueError) as ex:
        raise BuyWanderCredentialDecryptError(
            "Stored BuyWander credentials can no longer be decrypted. "
            "Update this login's password to continue."
        ) from ex
    session = create_bw_session()
    bw_login(
        session, login.bw_email, password
    )  # raises ValueError/HTTPError on failure
    login.encrypted_cookies = encrypt(serialise_cookies(session))
    db.commit()
    return session
