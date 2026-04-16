"""
backend/app/api/auth.py — Registration, login, token refresh.

Improvements over original:
- Refresh token rotation: each /refresh call issues a new refresh token and
  revokes the old one (single-use tokens tracked in the refresh_tokens table).
- Rate limiting via slowapi on all auth endpoints.
- Tokens stored as SHA-256 hashes in the DB (raw token never persisted).
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from ..config import REFRESH_TOKEN_EXPIRE
from ..db.database import get_db
from ..db.models import RefreshToken, User
from ..db.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from ..services.auth_service import authenticate_user, get_user_by_id, register_user
from ..utils.jwt_utils import create_access_token, create_refresh_token, decode_token

logger = logging.getLogger(__name__)

# ── Rate limiter ─────────────────────────────────────────────────────────────
# Limiter instance is shared with main.py (imported there for app-level setup).
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _store_refresh_token(db: Session, user_id: str, token: str) -> None:
    """Persist a hashed refresh token with its expiry."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE)
    db.add(RefreshToken(
        user_id=user_id,
        token_hash=_hash_token(token),
        expires_at=expires_at,
    ))
    db.commit()


def _revoke_refresh_token(db: Session, token: str) -> bool:
    """Mark the given token as revoked.  Returns True if it existed."""
    rec = db.query(RefreshToken).filter(
        RefreshToken.token_hash == _hash_token(token),
        RefreshToken.revoked == False,  # noqa: E712
    ).first()
    if not rec:
        return False
    rec.revoked = True
    db.commit()
    return True


def _issue_token_pair(db: Session, user: User) -> TokenResponse:
    """Create a fresh access + refresh token pair and persist the refresh token."""
    access  = create_access_token(user.id, user.email, is_admin=user.is_admin)
    refresh = create_refresh_token(user.id)
    _store_refresh_token(db, user.id, refresh)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse)
@limiter.limit("10/minute")
def register(request: Request, req: RegisterRequest,
             db: Session = Depends(get_db)):
    try:
        user = register_user(db, req.email, req.password, req.display_name)
    except ValueError as ex:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(ex))
    return _issue_token_pair(db, user)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("20/minute")
def login(request: Request, req: LoginRequest,
          db: Session = Depends(get_db)):
    user = authenticate_user(db, req.email, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return _issue_token_pair(db, user)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
def refresh(request: Request, req: RefreshRequest,
            db: Session = Depends(get_db)):
    payload = decode_token(req.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Verify the token exists in the DB and has not been revoked
    rec = db.query(RefreshToken).filter(
        RefreshToken.token_hash == _hash_token(req.refresh_token),
        RefreshToken.revoked == False,  # noqa: E712
    ).first()
    if not rec:
        # Token already used or never issued — possible token theft; log it
        logger.warning("Refresh token not found or already revoked for sub=%s",
                       payload.get("sub"))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token already used or revoked",
        )

    # Single-use: revoke immediately before issuing the replacement
    rec.revoked = True
    db.commit()

    user = get_user_by_id(db, payload["sub"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return _issue_token_pair(db, user)


@router.post("/logout")
@limiter.limit("30/minute")
def logout(request: Request, req: RefreshRequest,
           db: Session = Depends(get_db)):
    """Revoke a refresh token on explicit logout."""
    if req.refresh_token:
        _revoke_refresh_token(db, req.refresh_token)
    return {"success": True}


@router.get("/me")
def get_me(user: User = Depends(get_current_user)):
    """Return the current user's identity (authoritative source for frontend)."""
    return {
        "user_id":      user.id,
        "email":        user.email,
        "display_name": user.display_name,
        "is_admin":     user.is_admin,
    }
