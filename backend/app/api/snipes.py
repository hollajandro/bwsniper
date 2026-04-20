"""
backend/app/api/snipes.py — Snipe CRUD endpoints.
"""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import User, UserConfig
from ..db.schemas import SnipeCreate, SnipeUpdate, SnipeResponse
from ..dependencies import get_current_user
from ..db.models import BuyWanderLogin, Snipe
from ..services.snipe_service import (
    create_snipe,
    update_snipe,
    delete_snipe,
    get_user_snipes,
)
from ..services import notification_service
from ..websocket.manager import ws_manager
from ..api.auth import limiter

router = APIRouter(prefix="/snipes", tags=["snipes"])


def _make_notification_fn(user_id: str, snipe_id_ref: list):
    """Build a notification callback that re-reads user prefs at send time.

    snipe_id_ref is a one-element list [snipe_id] so that the caller can
    populate the ID after create_snipe returns (late-binding).  The worker
    only invokes this function when the auction ends, so the ID is always set.
    """
    from ..db.database import SessionLocal

    def _fn(title, status, bid_amount, final_price):
        # Read config fresh so preference changes after snipe creation are honoured
        db = SessionLocal()
        try:
            cfg_rec = db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
            cfg = json.loads(cfg_rec.config_json) if cfg_rec else {}
            # Also read the snipe's per-snipe notify override
            snipe_rec = db.query(Snipe).filter(Snipe.id == snipe_id_ref[0]).first()
            snipe_notify = snipe_rec.notify if snipe_rec else None
        except Exception:
            cfg = {}
            snipe_notify = None
        finally:
            db.close()

        # Per-snipe override takes priority
        if snipe_notify is False:
            return
        notif = cfg.get("notifications", {})
        if snipe_notify is None:  # use global setting
            if status == "Won" and not notif.get("notify_on_won", True):
                return
            if status == "Lost" and not notif.get("notify_on_lost", True):
                return
        notification_service.notify_outcome(cfg, title, status, bid_amount, final_price)

    return _fn


@router.post("", response_model=SnipeResponse)
@limiter.limit("30/minute")
def add_snipe(
    request: Request,
    req: SnipeCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Use a mutable container so the notification closure can reference the snipe
    # ID after create_snipe assigns it (the worker only calls the fn after the
    # auction ends, so the ID will always be populated by then).
    snipe_id_ref = [None]
    notification_fn = _make_notification_fn(user.id, snipe_id_ref)
    try:
        snipe = create_snipe(
            db,
            user.id,
            req.login_id,
            req.url,
            req.bid_amount,
            req.snipe_seconds,
            ws_manager=ws_manager,
            notification_fn=notification_fn,
            notify=req.notify,
        )
        snipe_id_ref[0] = snipe.id
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex))
    return snipe


@router.get("", response_model=list[SnipeResponse])
def list_snipes(
    login_id: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_user_snipes(db, user.id, login_id=login_id)


@router.get("/{snipe_id}", response_model=SnipeResponse)
def get_snipe(
    snipe_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    # Join through the login so we guarantee the snipe belongs to this user
    snipe = (
        db.query(Snipe)
        .join(BuyWanderLogin)
        .filter(Snipe.id == snipe_id, BuyWanderLogin.user_id == user.id)
        .first()
    )
    if not snipe:
        raise HTTPException(status_code=404, detail="Snipe not found.")
    return snipe


@router.put("/{snipe_id}", response_model=SnipeResponse)
def modify_snipe(
    snipe_id: str,
    req: SnipeUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Build update_data from only the fields explicitly set in the request.
    # Pydantic's default=None makes it impossible to distinguish "not sent"
    # from "explicitly sent as null" — we sidestep that by using the
    # request.__fields_set__ or checking the raw dict.
    update_data = req.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update.")
    try:
        return update_snipe(
            db,
            user.id,
            snipe_id,
            update_data=update_data,
        )
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex))


@router.delete("/{snipe_id}")
def remove_snipe(
    snipe_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not delete_snipe(db, user.id, snipe_id):
        raise HTTPException(status_code=404, detail="Snipe not found.")
    return {"success": True}
