"""
backend/app/api/watchlist.py — Watchlist (watch without sniping) endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import BuyWanderLogin, User, WatchlistItem
from ..db.schemas import WatchlistCreate, WatchlistResponse
from ..dependencies import get_current_user
from ..services.buywander_api import extract_handle

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchlistResponse])
def list_watchlist(user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    return db.query(WatchlistItem).filter(WatchlistItem.user_id == user.id)\
             .order_by(WatchlistItem.created_at.desc()).all()


@router.post("", response_model=WatchlistResponse)
def add_to_watchlist(req: WatchlistCreate,
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    # Validate login_id belongs to this user (if provided)
    if req.login_id:
        login = db.query(BuyWanderLogin).filter(
            BuyWanderLogin.id == req.login_id,
            BuyWanderLogin.user_id == user.id,
        ).first()
        if not login:
            raise HTTPException(status_code=404, detail="Login not found.")

    handle = extract_handle(req.url)
    existing = db.query(WatchlistItem).filter(
        WatchlistItem.user_id == user.id,
        WatchlistItem.handle == handle,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Already in watchlist.")
    item = WatchlistItem(
        user_id=user.id,
        login_id=req.login_id,
        handle=handle,
        url=req.url,
        title=req.title,
        notes=req.notes,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}")
def remove_from_watchlist(item_id: str,
                           user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    item = db.query(WatchlistItem).filter(
        WatchlistItem.id == item_id,
        WatchlistItem.user_id == user.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found.")
    db.delete(item)
    db.commit()
    return {"success": True}
