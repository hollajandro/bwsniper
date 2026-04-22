"""
backend/app/api/cart.py — Cart, payment, and appointment management.
"""

from concurrent.futures import ThreadPoolExecutor

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import User, BuyWanderLogin
from ..db.schemas import (
    PayRequest,
    AppointmentCreate,
    AppointmentReschedule,
    CartRemoveItem,
)
from ..dependencies import get_current_user
from ..services.auth_service import (
    BuyWanderCredentialDecryptError,
    reauth_bw_login,
)
from ..services.buywander_api import (
    create_bw_session,
    validate_session,
    fetch_cart_and_visits,
    fetch_reserved_auctions,
    fetch_payment_methods,
    fetch_open_slots,
    fetch_removal_status,
    do_pay_checkout,
    do_create_appointment,
    do_reschedule_appointment,
    do_cancel_appointment,
    do_remove_from_cart,
    _redact_stripe_keys,  # re-export for local use
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/cart", tags=["cart"])


def _resolve(db: Session, user: User, login_id: str):
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
    bw = create_bw_session(login.encrypted_cookies)
    if not validate_session(bw):
        log.warning(
            "BW session invalid for login %s — re-authenticating", login.bw_email
        )
        try:
            bw = reauth_bw_login(login, db)
            log.warning("Re-authentication succeeded for %s", login.bw_email)
        except BuyWanderCredentialDecryptError as ex:
            log.warning(
                "Stored BuyWander credentials invalid for %s: %s",
                login.bw_email,
                ex,
            )
            raise HTTPException(status_code=409, detail=str(ex))
        except Exception as ex:
            log.error(
                "Re-authentication failed for %s: %s", login.bw_email, ex, exc_info=True
            )
            raise HTTPException(
                status_code=502,
                detail=f"BuyWander session expired and re-authentication failed: {ex}",
            )
    return bw, login


@router.get("/{login_id}")
def get_cart(
    login_id: str,
    store_location_id: str = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bw, login = _resolve(db, user, login_id)
    cid = login.customer_id
    enc_cookies = login.encrypted_cookies
    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            cart_future = executor.submit(
                fetch_cart_and_visits, bw, cid, store_location_id
            )
            # Create separate sessions for parallel calls since requests.Session isn't thread-safe
            reserved_future = executor.submit(
                lambda: fetch_reserved_auctions(create_bw_session(enc_cookies), cid)
            )
            methods_future = executor.submit(
                lambda: fetch_payment_methods(create_bw_session(enc_cookies))
            )
            return {
                "cart_data": cart_future.result(),
                "reserved": reserved_future.result(),
                "methods": methods_future.result(),
            }
    except Exception as ex:
        log.error("get_cart failed: %s", ex, exc_info=True)
        raise HTTPException(status_code=502, detail=str(ex))


@router.get("/{login_id}/open-slots")
def get_open_slots(
    login_id: str,
    location_id: str = Query(...),
    day: str = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bw, login = _resolve(db, user, login_id)
    try:
        return fetch_open_slots(bw, location_id, day, login.customer_id or "")
    except Exception as ex:
        raise HTTPException(status_code=502, detail=str(ex))


@router.get("/{login_id}/removal-status")
def get_removal_status(
    login_id: str,
    store_location_id: str = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bw, _ = _resolve(db, user, login_id)
    try:
        return fetch_removal_status(bw, store_location_id)
    except Exception as ex:
        log.error("get_removal_status failed: %s", ex, exc_info=True)
        raise HTTPException(status_code=502, detail=str(ex))


@router.post("/{login_id}/pay")
def pay_cart(
    login_id: str,
    req: PayRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bw, login = _resolve(db, user, login_id)
    try:
        # Fetch saved payment methods so do_pay_checkout can pass them to the
        # Stripe confirmation step (needed when skipPayment is False).
        enc_cookies = login.encrypted_cookies
        try:
            methods = fetch_payment_methods(create_bw_session(enc_cookies))
        except Exception:
            methods = []

        result = do_pay_checkout(bw, req.store_location_id, payment_methods=methods)
        # Redact any Stripe keys from the logged response
        log.warning("BW pay response: %s", _redact_stripe_keys(str(result)))
        return result
    except HTTPException:
        raise
    except RuntimeError as ex:
        # Stripe confirmation error — message already user-readable
        log.warning("pay_cart Stripe error: %s", ex)
        raise HTTPException(status_code=502, detail=str(ex))
    except Exception as ex:
        log.warning("pay_cart exception: %s", ex, exc_info=True)
        raise HTTPException(status_code=502, detail=str(ex))


@router.post("/{login_id}/appointments")
def create_appointment(
    login_id: str,
    req: AppointmentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bw, _ = _resolve(db, user, login_id)
    try:
        return do_create_appointment(bw, req.location_id, req.visit_date_iso)
    except Exception as ex:
        raise HTTPException(status_code=502, detail=str(ex))


@router.put("/{login_id}/appointments/{visit_id}")
def reschedule_appointment(
    login_id: str,
    visit_id: str,
    req: AppointmentReschedule,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bw, _ = _resolve(db, user, login_id)
    try:
        return do_reschedule_appointment(bw, visit_id, req.new_date_iso)
    except Exception as ex:
        raise HTTPException(status_code=502, detail=str(ex))


@router.delete("/{login_id}/appointments/{visit_id}")
def cancel_appointment(
    login_id: str,
    visit_id: str,
    visit_date: str = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bw, _ = _resolve(db, user, login_id)
    try:
        return do_cancel_appointment(bw, visit_id, visit_date)
    except Exception as ex:
        raise HTTPException(status_code=502, detail=str(ex))


@router.delete("/{login_id}/items")
def remove_cart_item(
    login_id: str,
    req: CartRemoveItem,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bw, _ = _resolve(db, user, login_id)
    try:
        do_remove_from_cart(bw, req.auction_id, req.reason, req.notes)
        return {"success": True}
    except RuntimeError as ex:
        raise HTTPException(status_code=502, detail=str(ex))
