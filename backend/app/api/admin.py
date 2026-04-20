"""
backend/app/api/admin.py — Admin-only user management endpoints.

All routes require the caller to be an administrator (is_admin=True).
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import User
from ..db.schemas import (
    AdminUserView,
    AdminUserCreate,
    AdminUserUpdate,
    AdminPasswordReset,
)
from ..dependencies import require_admin
from ..services.auth_service import hash_password
from ..db.models import UserConfig
import json as _json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


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


@router.post(
    "/users", response_model=AdminUserView, status_code=status.HTTP_201_CREATED
)
def create_user(
    body: AdminUserCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new user with a preset password."""
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name or body.email.split("@")[0],
        is_admin=body.is_admin,
    )
    db.add(user)
    db.flush()
    db.add(UserConfig(user_id=user.id, config_json=_json.dumps(_DEFAULT_CONFIG)))
    db.commit()
    db.refresh(user)
    logger.info(
        "Admin %s created user %s (is_admin=%s)", admin.email, user.email, user.is_admin
    )
    return user


@router.get("/users", response_model=List[AdminUserView])
def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return all registered users."""
    return db.query(User).order_by(User.created_at).all()


@router.patch("/users/{user_id}", response_model=AdminUserView)
def update_user(
    user_id: str,
    body: AdminUserUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update a user's admin status or display name."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Prevent demoting the last admin (applies to self or any other admin)
    if body.is_admin is False and user.is_admin:
        admin_count = db.query(User).filter(User.is_admin == True).count()  # noqa: E712
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last administrator",
            )

    if body.is_admin is not None:
        user.is_admin = body.is_admin
    if body.display_name is not None:
        user.display_name = body.display_name

    db.commit()
    db.refresh(user)
    logger.info(
        "Admin %s updated user %s: %s",
        admin.email,
        user.email,
        body.model_dump(exclude_none=True),
    )
    return user


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: str,
    body: AdminPasswordReset,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Set a new password for any user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    user.password_hash = hash_password(body.new_password)
    db.commit()
    logger.info("Admin %s reset password for user %s", admin.email, user.email)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Permanently delete a user and all their data."""
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    db.delete(user)
    db.commit()
    logger.info("Admin %s deleted user %s", admin.email, user.email)
