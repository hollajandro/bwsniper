"""
backend/app/utils/jwt_utils.py — JWT token creation and validation.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from ..config import (
    SECRET_KEY,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE,
    REFRESH_TOKEN_EXPIRE,
)


def create_access_token(user_id: str, email: str, is_admin: bool = False) -> str:
    """Create a short-lived access token."""
    exp = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE)
    payload = {
        "sub": user_id,
        "email": email,
        "is_admin": is_admin,
        "type": "access",
        "exp": exp,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create a long-lived refresh token."""
    exp = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": exp,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT.  Returns payload dict or None on failure."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
