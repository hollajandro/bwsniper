"""
backend/app/api/watchlist.py — Watchlist (watch without sniping) endpoints.
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import BuyWanderLogin, User, WatchlistItem
from ..db.schemas import WatchlistCreate, WatchlistResponse
from ..dependencies import get_current_user
from ..services.buywander_api import extract_handle

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def _decode_snapshot(item: WatchlistItem) -> dict | None:
    if not item.snapshot_json:
        return None
    try:
        value = json.loads(item.snapshot_json)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _watchlist_response(item: WatchlistItem) -> dict:
    return {
        "id": item.id,
        "user_id": item.user_id,
        "login_id": item.login_id,
        "handle": item.handle,
        "auction_id": item.auction_id,
        "url": item.url,
        "title": item.title,
        "notes": item.notes,
        "snapshot": _decode_snapshot(item),
        "created_at": item.created_at,
    }


@router.get("", response_model=list[WatchlistResponse])
def list_watchlist(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    items = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.user_id == user.id)
        .order_by(WatchlistItem.created_at.desc())
        .all()
    )
    return [_watchlist_response(item) for item in items]


@router.post("", response_model=WatchlistResponse)
def add_to_watchlist(
    req: WatchlistCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Validate login_id belongs to this user (if provided)
    if req.login_id:
        login = (
            db.query(BuyWanderLogin)
            .filter(
                BuyWanderLogin.id == req.login_id,
                BuyWanderLogin.user_id == user.id,
            )
            .first()
        )
        if not login:
            raise HTTPException(status_code=404, detail="Login not found.")

    handle = extract_handle(req.url)
    snapshot_json = json.dumps(req.snapshot) if req.snapshot else None
    query = db.query(WatchlistItem).filter(WatchlistItem.user_id == user.id)
    existing = query.filter(WatchlistItem.handle == handle).first()
    if not existing and req.auction_id:
        existing = query.filter(WatchlistItem.auction_id == req.auction_id).first()
    if existing:
        existing.login_id = req.login_id or existing.login_id
        existing.auction_id = req.auction_id or existing.auction_id
        existing.url = req.url or existing.url
        existing.title = req.title or existing.title
        existing.notes = req.notes if req.notes is not None else existing.notes
        existing.snapshot_json = snapshot_json or existing.snapshot_json
        db.commit()
        db.refresh(existing)
        return _watchlist_response(existing)
    item = WatchlistItem(
        user_id=user.id,
        login_id=req.login_id,
        handle=handle,
        auction_id=req.auction_id,
        url=req.url,
        title=req.title,
        notes=req.notes,
        snapshot_json=snapshot_json,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _watchlist_response(item)


@router.delete("/{item_id}")
def remove_from_watchlist(
    item_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    item = (
        db.query(WatchlistItem)
        .filter(
            WatchlistItem.id == item_id,
            WatchlistItem.user_id == user.id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Not found.")
    db.delete(item)
    db.commit()
    return {"success": True}
