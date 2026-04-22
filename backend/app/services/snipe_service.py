"""
backend/app/services/snipe_service.py — High-level snipe orchestration.

Bridges API routes → DB operations → worker pool management.
"""

import logging
import time
from sqlalchemy.orm import Session as DBSession

from ..db.models import Snipe, BuyWanderLogin, SnipeStatus
from .buywander_api import extract_handle, create_bw_session
from .auction_worker import AuctionWorker
from .worker_pool import pool


def _get_bw_session(login: BuyWanderLogin):
    """Recreate a requests.Session from stored encrypted cookies."""
    return create_bw_session(login.encrypted_cookies)


def create_snipe(
    db: DBSession,
    user_id: str,
    login_id: str,
    url: str,
    bid_amount: float,
    snipe_seconds: int,
    ws_manager=None,
    notification_fn=None,
    notify=None,
) -> Snipe:
    """Create a snipe record and start its worker."""
    login = (
        db.query(BuyWanderLogin)
        .filter(
            BuyWanderLogin.id == login_id,
            BuyWanderLogin.user_id == user_id,
        )
        .first()
    )
    if not login:
        raise ValueError("BuyWander login not found or doesn't belong to you.")
    if not login.is_active:
        raise ValueError("This BuyWander login is disabled.")

    handle = extract_handle(url)
    snipe = Snipe(
        login_id=login_id,
        url=url,
        handle=handle,
        bid_amount=bid_amount,
        snipe_seconds=snipe_seconds,
        status=SnipeStatus.LOADING,
        notify=notify,
    )
    db.add(snipe)
    db.commit()
    db.refresh(snipe)

    # Spin up background worker
    bw_session = _get_bw_session(login)
    worker = AuctionWorker(
        snipe_id=snipe.id,
        login_id=login_id,
        user_id=user_id,
        bw_session=bw_session,
        customer_id=login.customer_id or "",
        handle=handle,
        bid_amount=bid_amount,
        snipe_seconds=snipe_seconds,
        ws_manager=ws_manager,
        notification_fn=notification_fn,
        bw_email=login.bw_email,
        encrypted_password=login.encrypted_password,
    )
    pool.spawn(snipe.id, worker)
    return snipe


def update_snipe(
    db: DBSession, user_id: str, snipe_id: str, update_data: dict | None = None
) -> Snipe:
    """Update bid_amount, snipe_seconds, and/or notify on a snipe.

    Only fields explicitly present in update_data are applied. This prevents
    a partial update (sending only bid_amount) from accidentally nulling out
    snipe_seconds or notify. Pydantic schema defaults of None would otherwise
    make it impossible to distinguish "not provided" from "set to null".
    """
    snipe = (
        db.query(Snipe)
        .join(BuyWanderLogin)
        .filter(
            Snipe.id == snipe_id,
            BuyWanderLogin.user_id == user_id,
        )
        .first()
    )
    if not snipe:
        raise ValueError("Snipe not found.")
    if snipe.status in SnipeStatus.terminal():
        raise ValueError(f"Cannot update a snipe in {snipe.status} state.")
    if update_data is None:
        update_data = {}
    if "bid_amount" in update_data:
        snipe.bid_amount = update_data["bid_amount"]
    if "snipe_seconds" in update_data:
        snipe.snipe_seconds = update_data["snipe_seconds"]
    if "notify" in update_data:
        snipe.notify = update_data["notify"]
    db.commit()
    db.refresh(snipe)

    # Update the running worker's parameters if alive
    worker = pool.get(snipe_id)
    if worker and worker.is_alive():
        if "bid_amount" in update_data:
            worker.bid_amount = update_data["bid_amount"]
        if "snipe_seconds" in update_data:
            worker.snipe_seconds = update_data["snipe_seconds"]

    return snipe


def delete_snipe(db: DBSession, user_id: str, snipe_id: str) -> bool:
    """Stop the worker and mark snipe as Deleted."""
    snipe = (
        db.query(Snipe)
        .join(BuyWanderLogin)
        .filter(
            Snipe.id == snipe_id,
            BuyWanderLogin.user_id == user_id,
        )
        .first()
    )
    if not snipe:
        return False
    pool.stop(snipe_id)
    snipe.status = SnipeStatus.DELETED
    db.commit()
    return True


def get_user_snipes(
    db: DBSession,
    user_id: str,
    login_id: str | None = None,
    include_deleted: bool = False,
) -> list[Snipe]:
    """Return all snipes belonging to the user, optionally filtered."""
    q = db.query(Snipe).join(BuyWanderLogin).filter(BuyWanderLogin.user_id == user_id)
    if login_id:
        q = q.filter(Snipe.login_id == login_id)
    if not include_deleted:
        q = q.filter(Snipe.status != SnipeStatus.DELETED)
    return q.order_by(Snipe.created_at.desc()).all()


def restart_active_snipes(db: DBSession, ws_manager=None):
    """On server startup, restart workers for all non-terminal snipes.

    NOTE: ERROR snipes are intentionally excluded from restart. An ERROR state
    indicates a persistent failure (e.g. invalid session, auction unavailable)
    that is unlikely to resolve on its own. Restarting them would create a
    restart loop — the worker would hit the same error immediately and transition
    back to ERROR. Manual user intervention is required to fix the underlying
    issue (re-authenticate, correct the snipe URL, etc.).

    SnipeStatus.active() does NOT include ERROR by design; ERROR is treated as
    a terminal-like state for restart purposes even though it is not in
    SnipeStatus.terminal() (which is used for display/filtering only).
    """
    snipes = db.query(Snipe).filter(Snipe.status.in_(list(SnipeStatus.active()))).all()
    _logger = logging.getLogger(__name__)
    _logger.info("Restarting %d active snipe(s) on startup", len(snipes))

    # Throttle: spawn workers in batches of 10 with a short sleep between
    # batches to avoid overwhelming the system with threads on startup.
    BATCH_SIZE = 10
    for batch_start in range(0, len(snipes), BATCH_SIZE):
        batch = snipes[batch_start : batch_start + BATCH_SIZE]
        for snipe in batch:
            login = snipe.login
            if not login or not login.is_active:
                continue
            bw_session = _get_bw_session(login)
            worker = AuctionWorker(
                snipe_id=snipe.id,
                login_id=snipe.login_id,
                user_id=login.user_id,
                bw_session=bw_session,
                customer_id=login.customer_id or "",
                handle=snipe.handle or extract_handle(snipe.url),
                bid_amount=snipe.bid_amount,
                snipe_seconds=snipe.snipe_seconds,
                ws_manager=ws_manager,
                bw_email=login.bw_email,
                encrypted_password=login.encrypted_password,
            )
            pool.spawn(snipe.id, worker)
        if batch_start + BATCH_SIZE < len(snipes):
            time.sleep(0.25)  # brief pause between batches
