"""
backend/app/api/auctions.py — Browse and detail auction endpoints.

These proxy through to the BuyWander API using a specific login's session.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import User, BuyWanderLogin
from ..db.schemas import AuctionSearchParams
from ..dependencies import get_current_user
from ..services.buywander_api import (
    create_bw_session, fetch_active_auctions, get_auction,
    fetch_store_locations,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auctions", tags=["auctions"])


def _get_bw_session(db: Session, user: User, login_id: str):
    """Resolve a BW login and build a session, or 404."""
    login = db.query(BuyWanderLogin).filter(
        BuyWanderLogin.id == login_id,
        BuyWanderLogin.user_id == user.id,
        BuyWanderLogin.is_active,
    ).first()
    if not login:
        raise HTTPException(status_code=404, detail="BuyWander login not found.")
    return create_bw_session(login.encrypted_cookies), login


@router.post("/search")
def search_auctions(params: AuctionSearchParams,
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    bw_session, _ = _get_bw_session(db, user, params.login_id)
    try:
        return fetch_active_auctions(
            bw_session,
            page=params.page,
            page_size=params.page_size,
            sort_by=params.sort_by,
            search=params.search,
            conditions=params.conditions or None,
            auction_filters=params.auction_filters or None,
            store_location_ids=params.store_location_ids or None,
            min_retail_price=params.min_retail_price,
            max_retail_price=params.max_retail_price,
        )
    except Exception as ex:
        log.warning("BuyWander search error: %s", ex)
        raise HTTPException(status_code=502, detail="Failed to fetch auctions from BuyWander.")


@router.get("/{auction_id}")
def auction_detail(auction_id: str,
                   login_id: str = Query(...),
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    bw_session, _ = _get_bw_session(db, user, login_id)
    try:
        return get_auction(bw_session, auction_id)
    except ValueError as ex:
        raise HTTPException(status_code=404, detail=str(ex))
    except Exception as ex:
        log.warning("BuyWander auction detail error (id=%s): %s", auction_id, ex)
        raise HTTPException(status_code=502, detail="Failed to fetch auction detail from BuyWander.")


@router.get("/locations/list")
def list_locations(login_id: str = Query(...),
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    bw_session, _ = _get_bw_session(db, user, login_id)
    try:
        return fetch_store_locations(bw_session)
    except Exception as ex:
        log.warning("BuyWander locations error: %s", ex)
        raise HTTPException(status_code=502, detail="Failed to fetch store locations from BuyWander.")
