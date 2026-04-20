"""
backend/app/api/logins.py — CRUD for BuyWander login credentials.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import User, BuyWanderLogin
from ..db.schemas import BWLoginCreate, BWLoginResponse, BWLoginUpdate
from ..dependencies import get_current_user
from ..utils.crypto import encrypt
from ..services.buywander_api import (
    create_bw_session,
    bw_login,
    validate_session,
    serialise_cookies,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/logins", tags=["buywander-logins"])


@router.post("", response_model=BWLoginResponse)
def add_login(
    req: BWLoginCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a BuyWander login — authenticates with BW and stores encrypted creds."""
    # Authenticate with BuyWander — no DB writes have happened yet, so no
    # rollback is needed here, but we still clean up carefully.
    bw_session = create_bw_session()
    try:
        bw_login(bw_session, req.bw_email, req.bw_password)
    except ValueError as ex:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ex))
    except Exception as ex:
        logger.error("Unexpected BW login error: %s", ex)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach BuyWander. Please try again.",
        )

    # Validate and get customer info
    customer = validate_session(bw_session)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Login succeeded but could not fetch BuyWander profile.",
        )

    # Check for duplicate
    existing = (
        db.query(BuyWanderLogin)
        .filter(
            BuyWanderLogin.user_id == user.id,
            BuyWanderLogin.bw_email == req.bw_email,
        )
        .first()
    )
    if existing:
        # Update existing login with fresh creds
        existing.encrypted_password = encrypt(req.bw_password)
        existing.encrypted_cookies = encrypt(serialise_cookies(bw_session))
        existing.customer_id = customer["id"]
        existing.display_name = (
            customer.get("displayName") or customer.get("firstName") or req.bw_email
        )
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return existing

    login = BuyWanderLogin(
        user_id=user.id,
        bw_email=req.bw_email,
        encrypted_password=encrypt(req.bw_password),
        encrypted_cookies=encrypt(serialise_cookies(bw_session)),
        customer_id=customer["id"],
        display_name=(
            customer.get("displayName") or customer.get("firstName") or req.bw_email
        ),
    )
    db.add(login)
    db.commit()
    db.refresh(login)
    return login


@router.get("", response_model=list[BWLoginResponse])
def list_logins(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(BuyWanderLogin)
        .filter(BuyWanderLogin.user_id == user.id)
        .order_by(BuyWanderLogin.created_at)
        .all()
    )


@router.put("/{login_id}", response_model=BWLoginResponse)
def update_login(
    login_id: str,
    req: BWLoginUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
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

    if req.is_active is not None:
        login.is_active = req.is_active

    if req.bw_email and req.bw_password:
        # Re-authenticate with new creds — if this fails, roll back is_active
        # change we may have made above.
        bw_session = create_bw_session()
        try:
            bw_login(bw_session, req.bw_email, req.bw_password)
        except ValueError as ex:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(ex))
        except Exception as ex:
            db.rollback()
            logger.error("Unexpected BW re-auth error: %s", ex)
            raise HTTPException(status_code=502, detail="Could not reach BuyWander.")
        customer = validate_session(bw_session)
        if customer:
            login.bw_email = req.bw_email
            login.encrypted_password = encrypt(req.bw_password)
            login.encrypted_cookies = encrypt(serialise_cookies(bw_session))
            login.customer_id = customer["id"]
            login.display_name = (
                customer.get("displayName") or customer.get("firstName") or req.bw_email
            )

    db.commit()
    db.refresh(login)
    return login


@router.delete("/{login_id}")
def delete_login(
    login_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
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
    db.delete(login)
    db.commit()
    return {"success": True}
