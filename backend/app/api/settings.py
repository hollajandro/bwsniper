"""
backend/app/api/settings.py — User settings CRUD.
"""

from datetime import datetime, timezone
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import User, UserConfig
from ..db.schemas import SettingsResponse, SettingsUpdate
from ..dependencies import get_current_user
from ..services import notification_service
from ..services.notification_encryption import (
    encrypt_notifications,
    decrypt_notifications,
)

router = APIRouter(prefix="/settings", tags=["settings"])

_DEFAULT_CONFIG = {
    "defaults": {"snipe_seconds": 5, "default_location_id": None},
    "serper_api_key": "",
    "notifications": {
        "remind_before_seconds": 300,
        "notify_on_won": True,
        "notify_on_lost": True,
        "keyword_watches": [],
        "keyword_watch_locations": {},
        "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
        "smtp": {
            "enabled": False,
            "host": "smtp.gmail.com",
            "port": 587,
            "username": "",
            "password": "",
            "from_addr": "",
            "to_addr": "",
            "use_tls": True,
        },
        "pushover": {"enabled": False, "user_key": "", "app_token": ""},
        "gotify": {"enabled": False, "url": "", "token": "", "priority": 5},
    },
}


def _deep_merge(base: dict, overlay: dict) -> dict:
    result = dict(base)
    for k, v in overlay.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _truncate_to_seconds_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _parse_settings_version(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return _truncate_to_seconds_utc(parsed)


def _get_or_create_config(db: Session, user: User) -> UserConfig:
    cfg = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
    if not cfg:
        cfg = UserConfig(
            user_id=user.id,
            config_json=json.dumps(_DEFAULT_CONFIG),
        )
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


@router.get("", response_model=SettingsResponse)
def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cfg = _get_or_create_config(db, user)
    try:
        raw = json.loads(cfg.config_json)
        # Decrypt any encrypted credential fields before returning to client
        data = _deep_merge(_DEFAULT_CONFIG, decrypt_notifications(raw))
    except Exception:
        data = dict(_DEFAULT_CONFIG)
    return SettingsResponse(
        defaults=data.get("defaults", {}),
        notifications=data.get("notifications", {}),
        serper_api_key=data.get("serper_api_key", ""),
        updated_at=cfg.updated_at,
    )


@router.put("", response_model=SettingsResponse)
def update_settings(
    req: SettingsUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cfg = _get_or_create_config(db, user)

    if req.version is not None:
        try:
            req_ts = _parse_settings_version(req.version)
        except ValueError as ex:
            raise HTTPException(
                status_code=400,
                detail="Invalid settings version.",
            ) from ex

        db_ts = _truncate_to_seconds_utc(cfg.updated_at) if cfg.updated_at else None
        if db_ts and db_ts != req_ts:
            raise HTTPException(
                status_code=409,
                detail="Settings were modified in another tab. Please reload.",
            )

    try:
        current = json.loads(cfg.config_json)
    except Exception:
        current = dict(_DEFAULT_CONFIG)

    if req.defaults is not None:
        current["defaults"] = _deep_merge(
            current.get("defaults", {}), req.defaults.model_dump()
        )
    if req.notifications is not None:
        current["notifications"] = _deep_merge(
            current.get("notifications", {}), req.notifications.model_dump()
        )
    if req.serper_api_key is not None:
        current["serper_api_key"] = req.serper_api_key

    # Encrypt credential fields before persisting to config_json
    current = encrypt_notifications(current)

    cfg.config_json = json.dumps(current)
    db.commit()
    db.refresh(cfg)

    # Decrypt for the response so the client receives plain-text values
    merged = _deep_merge(_DEFAULT_CONFIG, decrypt_notifications(current))
    return SettingsResponse(
        defaults=merged.get("defaults", {}),
        notifications=merged.get("notifications", {}),
        serper_api_key=merged.get("serper_api_key", ""),
        updated_at=cfg.updated_at,
    )


_VALID_CHANNELS = {"telegram", "smtp", "pushover", "gotify"}


@router.post("/test-notification/{channel}")
def test_notification(
    channel: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if channel not in _VALID_CHANNELS:
        raise HTTPException(status_code=400, detail=f"Unknown channel: {channel}")

    cfg = _get_or_create_config(db, user)
    try:
        data = _deep_merge(_DEFAULT_CONFIG, json.loads(cfg.config_json))
    except Exception:
        data = dict(_DEFAULT_CONFIG)

    ch_cfg = data.get("notifications", {}).get(channel, {})
    if not ch_cfg.get("enabled"):
        raise HTTPException(status_code=400, detail=f"{channel} is not enabled")

    try:
        notification_service.send_test(
            channel,
            ch_cfg,
            "BW Sniper — test notification",
            "This is a test message from BW Sniper.",
        )
    except Exception as ex:
        logging.getLogger(__name__).warning(
            "Test notification failed (%s): %s", channel, ex
        )
        # Sanitize: don't leak internal details to the client
        safe_msg = str(ex)
        if len(safe_msg) > 200:
            safe_msg = safe_msg[:200] + "…"
        raise HTTPException(status_code=502, detail=safe_msg)

    return {"ok": True, "channel": channel}
