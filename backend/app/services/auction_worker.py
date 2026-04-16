"""
backend/app/services/auction_worker.py — Background thread that monitors an
auction and fires a snipe bid when the timer is within range.

Ported from the original bw/state.py:AuctionWorker with these changes:
- Updates the database instead of in-memory AppState
- Publishes events via the WebSocket ConnectionManager
- Takes a BuyWander session + snipe DB record instead of AppState+AuctionEntry
"""

import threading
from datetime import datetime, timezone

import requests as _requests
from sqlalchemy.orm import Session as DBSession

from ..db.database import SessionLocal
from ..db.models import Snipe, EventLog, HistoryRecord, SnipeStatus, BuyWanderLogin
from ..utils.retry import with_retry as _with_retry
from ..utils.crypto import decrypt as _decrypt, encrypt as _encrypt
from .buywander_api import (get_auction, place_bid, parse_dt,
                             bw_login, create_bw_session, serialise_cookies)


class AuctionWorker(threading.Thread):
    """Daemon thread that polls a single auction and fires a snipe."""

    def __init__(self, snipe_id: str, login_id: str, user_id: str,
                 bw_session: _requests.Session, customer_id: str,
                 handle: str, bid_amount: float, snipe_seconds: int,
                 ws_manager=None, notification_fn=None,
                 bw_email: str = None, encrypted_password: str = None):
        super().__init__(daemon=True)
        self.snipe_id          = snipe_id
        self.login_id          = login_id
        self.user_id           = user_id
        self.bw_session        = bw_session
        self.customer_id       = customer_id
        self.handle            = handle
        self.ws_manager        = ws_manager
        self.notification_fn   = notification_fn
        self._bw_email         = bw_email
        self._encrypted_pw     = encrypted_password
        self._stop_event       = threading.Event()
        # bid_amount and snipe_seconds can be updated live from the HTTP
        # request thread via snipe_service.update_snipe().  Protect with a
        # lock so the worker thread always reads a consistent pair.
        self._params_lock   = threading.Lock()
        self._bid_amount    = bid_amount
        self._snipe_seconds = snipe_seconds

    # ── Thread-safe parameter accessors ──────────────────────────────────────

    @property
    def bid_amount(self) -> float:
        with self._params_lock:
            return self._bid_amount

    @bid_amount.setter
    def bid_amount(self, value: float) -> None:
        with self._params_lock:
            self._bid_amount = value

    @property
    def snipe_seconds(self) -> int:
        with self._params_lock:
            return self._snipe_seconds

    @snipe_seconds.setter
    def snipe_seconds(self, value: int) -> None:
        with self._params_lock:
            self._snipe_seconds = value

    def stop(self):
        self._stop_event.set()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _reauthenticate(self) -> bool:
        """Re-login to BuyWander, refresh self.bw_session, and persist new cookies."""
        if not self._bw_email or not self._encrypted_pw:
            self._log_event("Cannot re-authenticate: credentials not available", "error")
            return False
        try:
            password = _decrypt(self._encrypted_pw)
            new_session = create_bw_session()
            bw_login(new_session, self._bw_email, password)
            new_cookies_enc = _encrypt(serialise_cookies(new_session))
            db = self._db()
            try:
                login = db.query(BuyWanderLogin).filter(
                    BuyWanderLogin.id == self.login_id).first()
                if login:
                    login.encrypted_cookies = new_cookies_enc
                    db.commit()
            finally:
                db.close()
            self.bw_session = new_session
            self._log_event("Session refreshed — re-authenticated with BuyWander", "info")
            return True
        except Exception as ex:
            self._log_event(f"Re-authentication failed: {ex}", "error")
            return False

    def _db(self) -> DBSession:
        """Create a fresh DB session (caller must close)."""
        return SessionLocal()

    def _update_snipe(self, **fields):
        """Persist snipe field updates to the database."""
        db = self._db()
        try:
            snipe = db.query(Snipe).filter(Snipe.id == self.snipe_id).first()
            if snipe:
                for k, v in fields.items():
                    setattr(snipe, k, v)
                db.commit()
        finally:
            db.close()

    def _log_event(self, message: str, event_type: str = "info",
                   auction_id: str = None):
        """Write an event to the DB and broadcast via WebSocket."""
        db = self._db()
        try:
            ev = EventLog(
                login_id=self.login_id,
                user_id=self.user_id,
                event_type=event_type,
                message=message,
                auction_id=auction_id or self.snipe_id,
            )
            db.add(ev)
            db.commit()
        finally:
            db.close()
        if self.ws_manager:
            self.ws_manager.broadcast_to_user(self.user_id, {
                "type": "log.event",
                "data": {
                    "message": message,
                    "event_type": event_type,
                    "snipe_id": self.snipe_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })

    def _broadcast_status(self, status: str, extra: dict = None):
        """Push a snipe status change to WebSocket subscribers."""
        if not self.ws_manager:
            return
        data = {"snipe_id": self.snipe_id, "status": status}
        if extra:
            data.update(extra)
        self.ws_manager.broadcast_to_user(self.user_id, {
            "type": "snipe.status_changed",
            "data": data,
        })

    def _update_and_broadcast(self, fields: dict, log_msg: str = None,
                               log_type: str = "info", status: str = None,
                               ws_extra: dict = None):
        """Batch DB updates + event logging into a single session."""
        db = self._db()
        try:
            snipe = db.query(Snipe).filter(Snipe.id == self.snipe_id).first()
            if snipe:
                for k, v in fields.items():
                    setattr(snipe, k, v)
            if log_msg:
                ev = EventLog(
                    login_id=self.login_id,
                    user_id=self.user_id,
                    event_type=log_type,
                    message=log_msg,
                    auction_id=self.snipe_id,
                )
                db.add(ev)
            db.commit()
        finally:
            db.close()
        if log_msg and self.ws_manager:
            self.ws_manager.broadcast_to_user(self.user_id, {
                "type": "log.event",
                "data": {
                    "message": log_msg,
                    "event_type": log_type,
                    "snipe_id": self.snipe_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })
        if status and self.ws_manager:
            data = {"snipe_id": self.snipe_id, "status": status}
            if ws_extra:
                data.update(ws_extra)
            self.ws_manager.broadcast_to_user(self.user_id, {
                "type": "snipe.status_changed",
                "data": data,
            })

    def _record_history(self, title: str, url: str, auction_uuid: str,
                        final_price: float, my_bid: float):
        """Write a won-auction record to history."""
        db = self._db()
        try:
            rec = HistoryRecord(
                login_id=self.login_id,
                auction_id=auction_uuid,
                title=title,
                url=url,
                final_price=final_price,
                my_bid=my_bid,
                won_at=datetime.now(timezone.utc),
            )
            db.add(rec)
            db.commit()
        finally:
            db.close()

    # ── Main loop ────────────────────────────────────────────────────────────

    def run(self):
        # ── Initial load ────────────────────────────────────────────────────
        try:
            auction = _with_retry(lambda: get_auction(self.bw_session, self.handle))
        except Exception as ex:
            self._update_and_broadcast(
                fields={"status": SnipeStatus.ERROR, "error_msg": str(ex)[:200]},
                log_msg=f"Load failed: {ex}",
                log_type="error",
                status=SnipeStatus.ERROR,
                ws_extra={"error_msg": str(ex)[:200]},
            )
            return

        item = auction.get("item") or {}
        title = item.get("title", self.handle)
        auction_uuid = auction.get("id", self.handle)
        end_str = auction.get("endDate")
        end_time = parse_dt(end_str) if end_str else None
        url = f"https://www.buywander.com/auctions/{item.get('handle', self.handle)}"

        self._update_and_broadcast(
            fields={
                "status": SnipeStatus.WATCHING,
                "title": title,
                "auction_uuid": auction_uuid,
                "end_time": end_time,
            },
            log_msg=f"Watching: {title[:45]}",
            log_type="info",
            status=SnipeStatus.WATCHING,
            ws_extra={
                "title": title,
                "auction_uuid": auction_uuid,
                "end_time": end_time.isoformat() if end_time else None,
            },
        )

        seen_bids = set()
        bid_placed = False

        # ── Poll loop ───────────────────────────────────────────────────────
        while not self._stop_event.is_set():
            try:
                auction = _with_retry(lambda: get_auction(self.bw_session, self.handle))
            except _requests.HTTPError as ex:
                if ex.response is not None and ex.response.status_code == 401:
                    self._log_event("Session expired — re-authenticating…", "info")
                    if self._reauthenticate():
                        continue  # retry the poll immediately with the new session
                    # Re-auth failed — give up
                    self._update_and_broadcast(
                        fields={"status": SnipeStatus.ERROR,
                                "error_msg": "Session expired and re-authentication failed"},
                        log_msg="Stopped: session expired and could not re-authenticate",
                        log_type="error",
                        status=SnipeStatus.ERROR,
                        ws_extra={"error_msg": "Session expired"},
                    )
                    return
                self._log_event(f"Fetch error: {ex}", "error")
                self._stop_event.wait(30)
                continue
            except Exception as ex:
                self._log_event(f"{ex}", "error")
                self._stop_event.wait(30)
                continue

            wb         = auction.get("winningBid")
            cur_bid    = wb["amount"]      if wb else 0.0
            winner_h   = wb.get("handle")  if wb else None
            winner_cid = wb["customerId"]  if wb else None
            history    = auction.get("computedBidHistory") or []
            end_str    = auction.get("endDate")
            end_time   = parse_dt(end_str) if end_str else None
            my_max_raw = auction.get("customerMaxBid")
            is_me      = (winner_cid == self.customer_id)

            # Log new bids
            for bid in reversed(history):
                key = (bid.get("customerId"), bid.get("amount"), bid.get("placedAt"))
                if key not in seen_bids:
                    seen_bids.add(key)
                    handle = bid.get("handle", "?")
                    amount = bid.get("amount", 0)
                    me_tag = " <- YOU" if bid.get("customerId") == self.customer_id else ""
                    short  = title[:22] + "..." if len(title) > 22 else title
                    self._log_event(
                        f"@{handle} ${amount:.2f}{me_tag} ({short})", "bid")

            self._update_and_broadcast(
                fields={
                    "current_bid": cur_bid,
                    "winner_handle": winner_h,
                    "winner_id": winner_cid,
                    "bid_count": len(history),
                    "end_time": end_time,
                    "my_max_bid": float(my_max_raw) if my_max_raw and float(my_max_raw) > 0 else None,
                    "is_me": is_me,
                },
                status=SnipeStatus.WATCHING,
                ws_extra={
                    "current_bid": cur_bid,
                    "winner_handle": winner_h,
                    "bid_count": len(history),
                    "is_me": is_me,
                    "end_time": end_time.isoformat() if end_time else None,
                },
            )

            if not end_time:
                self._stop_event.wait(60)
                continue

            now       = datetime.now(timezone.utc)
            secs_left = (end_time - now).total_seconds()

            # ── Auction ended ───────────────────────────────────────────────
            if secs_left <= 0:
                if bid_placed:
                    final_status = SnipeStatus.WON if is_me else SnipeStatus.LOST
                    msg = (f"WON: {title[:40]} @ ${cur_bid:.2f}"
                           if is_me else
                           f"LOST: {title[:40]} — @{winner_h} ${cur_bid:.2f}")
                else:
                    final_status = SnipeStatus.ENDED
                    msg = f"Ended (no snipe fired): {title[:40]}"

                self._update_and_broadcast(
                    fields={
                        "status": final_status,
                        "final_price": cur_bid,
                        "ended_at": datetime.now(timezone.utc),
                    },
                    log_msg=msg,
                    log_type=final_status.lower(),
                    status=final_status,
                    ws_extra={
                        "final_price": cur_bid,
                        "winner_handle": winner_h,
                    },
                )

                if bid_placed and is_me:
                    self._record_history(title, url, auction_uuid, cur_bid,
                                         self.bid_amount)
                    if self.ws_manager:
                        self.ws_manager.broadcast_to_user(self.user_id, {
                            "type": "snipe.won",
                            "data": {
                                "snipe_id": self.snipe_id,
                                "title": title,
                                "final_price": cur_bid,
                            },
                        })

                if self.notification_fn:
                    self.notification_fn(title, final_status, self.bid_amount,
                                         cur_bid)
                return

            # ── Fire snipe ──────────────────────────────────────────────────
            if not bid_placed and secs_left <= self.snipe_seconds:
                self._log_event(
                    f"SNIPING {title[:28]}: ${self.bid_amount:.2f} "
                    f"({secs_left:.1f}s left)", "bid")

                try:
                    result = place_bid(
                        self.bw_session, auction_uuid,
                        self.customer_id, self.bid_amount)

                    if result.get("requiresCardAuth"):
                        self._update_and_broadcast(
                            fields={"status": SnipeStatus.ERROR, "error_msg": "Card auth required"},
                            log_msg="Card auth required — open browser",
                            log_type="error",
                            status=SnipeStatus.ERROR,
                            ws_extra={"error_msg": "Card auth required"},
                        )
                        return

                    bid_placed = True
                    self._update_and_broadcast(
                        fields={
                            "bid_placed": True,
                            "status": SnipeStatus.SNIPED,
                            "fired_at": datetime.now(timezone.utc),
                        },
                        log_msg=f"Bid submitted: ${self.bid_amount:.2f} on {title[:30]}",
                        log_type="bid",
                        status=SnipeStatus.SNIPED,
                        ws_extra={"bid_amount": self.bid_amount},
                    )
                    if self.ws_manager:
                        self.ws_manager.broadcast_to_user(self.user_id, {
                            "type": "snipe.fired",
                            "data": {
                                "snipe_id": self.snipe_id,
                                "bid_amount": self.bid_amount,
                                "title": title,
                            },
                        })
                    self._stop_event.wait(2)

                except _requests.HTTPError as ex:
                    if ex.response is not None and ex.response.status_code == 401:
                        self._log_event("Session expired during bid — re-authenticating…", "info")
                        if self._reauthenticate():
                            try:
                                result = place_bid(self.bw_session, auction_uuid,
                                                   self.customer_id, self.bid_amount)
                                if result.get("requiresCardAuth"):
                                    self._update_and_broadcast(
                                        fields={"status": SnipeStatus.ERROR,
                                                "error_msg": "Card auth required"},
                                        log_msg="Card auth required — open browser",
                                        log_type="error",
                                        status=SnipeStatus.ERROR,
                                        ws_extra={"error_msg": "Card auth required"},
                                    )
                                    return
                                bid_placed = True
                                self._update_and_broadcast(
                                    fields={
                                        "bid_placed": True,
                                        "status": SnipeStatus.SNIPED,
                                        "fired_at": datetime.now(timezone.utc),
                                    },
                                    log_msg=f"Bid submitted (after re-auth): ${self.bid_amount:.2f} on {title[:30]}",
                                    log_type="bid",
                                    status=SnipeStatus.SNIPED,
                                    ws_extra={"bid_amount": self.bid_amount},
                                )
                                if self.ws_manager:
                                    self.ws_manager.broadcast_to_user(self.user_id, {
                                        "type": "snipe.fired",
                                        "data": {
                                            "snipe_id": self.snipe_id,
                                            "bid_amount": self.bid_amount,
                                            "title": title,
                                        },
                                    })
                                self._stop_event.wait(2)
                            except Exception as retry_ex:
                                self._update_and_broadcast(
                                    fields={"status": SnipeStatus.ERROR,
                                            "error_msg": str(retry_ex)[:200]},
                                    log_msg=f"Bid retry failed: {retry_ex}",
                                    log_type="error",
                                    status=SnipeStatus.ERROR,
                                    ws_extra={"error_msg": str(retry_ex)[:200]},
                                )
                                return
                        else:
                            self._update_and_broadcast(
                                fields={"status": SnipeStatus.ERROR,
                                        "error_msg": "Session expired — re-auth failed"},
                                log_msg="Bid failed: session expired and could not re-authenticate",
                                log_type="error",
                                status=SnipeStatus.ERROR,
                                ws_extra={"error_msg": "Session expired"},
                            )
                            return
                    else:
                        detail = ""
                        try:
                            detail = ex.response.json().get("detail", ex.response.text)
                        except Exception:
                            detail = str(ex)
                        self._update_and_broadcast(
                            fields={"status": SnipeStatus.ERROR, "error_msg": str(detail)[:200]},
                            log_msg=f"Bid failed: {detail}",
                            log_type="error",
                            status=SnipeStatus.ERROR,
                            ws_extra={"error_msg": str(detail)[:200]},
                        )
                        return
                continue

            if secs_left <= self.snipe_seconds + 5:
                poll = 0.5        # tight loop near snipe window
            elif secs_left <= 120:
                poll = 5.0        # 5-second ticks in the last 2 minutes
            else:
                poll = 60.0       # 1-minute ticks while watching far out
            self._stop_event.wait(poll)
