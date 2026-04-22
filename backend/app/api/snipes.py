"""
backend/app/api/snipes.py — Snipe CRUD endpoints.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import User
from ..db.schemas import SnipeCreate, SnipeUpdate, SnipeResponse
from ..dependencies import get_current_user
from ..db.models import BuyWanderLogin, Snipe
from ..services.snipe_service import (
    create_snipe,
    update_snipe,
    delete_snipe,
    get_user_snipes,
)
from ..websocket.manager import ws_manager
from ..api.auth import limiter

router = APIRouter(prefix="/snipes", tags=["snipes"])


@router.post("", response_model=SnipeResponse)
@limiter.limit("30/minute")
def add_snipe(
    request: Request,
    req: SnipeCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        snipe = create_snipe(
            db,
            user.id,
            req.login_id,
            req.url,
            req.bid_amount,
            req.snipe_seconds,
            ws_manager=ws_manager,
            notification_fn=None,
            notify=req.notify,
        )
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
