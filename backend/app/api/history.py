"""
backend/app/api/history.py — Won-auction history endpoints.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import User, BuyWanderLogin, HistoryRecord
from ..db.schemas import HistoryResponse
from ..dependencies import get_current_user
from ..services.buywander_api import (
    create_bw_session,
    fetch_won_auctions,
    parse_dt,
)

router = APIRouter(prefix="/history", tags=["history"])


@router.get("", response_model=list[HistoryResponse])
def list_history(
    login_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return cached history records.  Use /history/refresh to pull from BW."""
    q = (
        db.query(HistoryRecord)
        .join(BuyWanderLogin)
        .filter(BuyWanderLogin.user_id == user.id)
    )
    if login_id:
        q = q.filter(HistoryRecord.login_id == login_id)
    if search:
        sq = f"%{search}%"
        q = q.filter((HistoryRecord.title.ilike(sq)) | (HistoryRecord.url.ilike(sq)))
    return q.order_by(HistoryRecord.won_at.desc()).all()


@router.post("/refresh")
def refresh_history(
    login_id: str = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetch won auctions from BuyWander and upsert into the cache."""
    login = (
        db.query(BuyWanderLogin)
        .filter(
            BuyWanderLogin.id == login_id,
            BuyWanderLogin.user_id == user.id,
        )
        .first()
    )
    if not login:
        raise HTTPException(status_code=404, detail="Login not found.")

    bw_session = create_bw_session(login.encrypted_cookies)
    try:
        records = fetch_won_auctions(bw_session, login.customer_id or "")
    except Exception as ex:
        raise HTTPException(status_code=502, detail=f"BuyWander error: {ex}")

    # Upsert: skip records already in the DB (by auction_id)
    existing_ids = set(
        r.auction_id
        for r in db.query(HistoryRecord.auction_id)
        .filter(HistoryRecord.login_id == login_id)
        .all()
    )

    added = 0
    for rec in records:
        aid = rec.get("auction_id", "")
        if aid and aid in existing_ids:
            continue
        won_at_str = rec.get("won_at", "")
        won_at = None
        if won_at_str:
            try:
                won_at = parse_dt(won_at_str)
            except Exception:
                pass
        history_kwargs = {
            "login_id": login_id,
            "auction_id": aid,
            "title": rec.get("title", ""),
            "url": rec.get("url", ""),
            "condition": rec.get("condition", ""),
            "final_price": rec.get("final_price", 0.0),
            "my_bid": rec.get("my_bid", 0.0),
            "store_location_id": rec.get("store_location_id", ""),
        }
        if won_at is not None:
            history_kwargs["won_at"] = won_at
        hr = HistoryRecord(**history_kwargs)
        db.add(hr)
        added += 1

    db.commit()
    return {"added": added, "total_fetched": len(records)}
