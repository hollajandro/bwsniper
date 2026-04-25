"""
Remote worker that mirrors the backend's in-process auction worker behavior.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Callable

import requests as _requests

from app.db.models import SnipeStatus
from app.services.bid_state import auction_shows_bid_applied, extract_http_error_detail
from app.services.buywander_api import (
    bw_login,
    create_bw_session,
    get_auction,
    parse_dt,
    place_bid,
    serialise_cookies,
)
from app.utils.crypto import decrypt, encrypt
from app.utils.retry import with_retry

logger = logging.getLogger(__name__)


class RemoteAuctionWorker(threading.Thread):
    def __init__(
        self,
        desired: dict,
        report_event: Callable[[dict], None],
    ) -> None:
        super().__init__(daemon=True)
        self.snipe_id = desired["snipe_id"]
        self.url = desired["url"]
        self.handle = desired["handle"]
        self.bid_amount = desired["bid_amount"]
        self.snipe_seconds = desired["snipe_seconds"]
        self.customer_id = desired["customer_id"]
        self.bw_email = desired["bw_email"]
        self.encrypted_password = desired["encrypted_password"]
        self.encrypted_cookies = desired.get("encrypted_cookies")
        self.payload_hash = desired["payload_hash"]
        self.bw_session = create_bw_session(self.encrypted_cookies)
        self._report_event = report_event
        self._stop_event = threading.Event()
        self._state_lock = threading.Lock()
        self._status = SnipeStatus.LOADING
        self._error_msg: str | None = None
        self._fired_at: datetime | None = None
        self._ended_at: datetime | None = None

    def stop(self) -> None:
        self._stop_event.set()

    def report_state(self) -> dict:
        with self._state_lock:
            return {
                "snipe_id": self.snipe_id,
                "status": self._status,
                "error_msg": self._error_msg,
                "fired_at": self._fired_at.isoformat() if self._fired_at else None,
                "ended_at": self._ended_at.isoformat() if self._ended_at else None,
                "payload_hash": self.payload_hash,
            }

    def is_terminal(self) -> bool:
        with self._state_lock:
            return self._status in SnipeStatus.terminal()

    def _set_status(
        self,
        status: str,
        *,
        error_msg: str | None = None,
        fired: bool = False,
        ended: bool = False,
    ) -> None:
        with self._state_lock:
            self._status = status
            self._error_msg = error_msg
            if fired and self._fired_at is None:
                self._fired_at = datetime.now(timezone.utc)
            if ended:
                self._ended_at = datetime.now(timezone.utc)

    def _post_event(
        self,
        event_type: str,
        message: str,
        *,
        status: str | None = None,
        error_msg: str | None = None,
        encrypted_cookies: str | None = None,
    ) -> None:
        payload = {
            "snipe_id": self.snipe_id,
            "event_type": event_type,
            "message": message,
            "status": status,
            "error_msg": error_msg,
            "fired_at": self._fired_at.isoformat() if self._fired_at else None,
            "ended_at": self._ended_at.isoformat() if self._ended_at else None,
            "encrypted_cookies": encrypted_cookies,
        }
        try:
            self._report_event(payload)
        except Exception as ex:
            logger.warning("Failed to report remote event for %s: %s", self.snipe_id, ex)

    def _reauthenticate(self) -> bool:
        try:
            password = decrypt(self.encrypted_password)
            session = create_bw_session()
            bw_login(session, self.bw_email, password)
            encrypted_cookies = encrypt(serialise_cookies(session))
            self.bw_session = session
            self.encrypted_cookies = encrypted_cookies
            self._post_event(
                "info",
                "Session refreshed on remote agent",
                encrypted_cookies=encrypted_cookies,
            )
            return True
        except Exception as ex:
            self._set_status(SnipeStatus.ERROR, error_msg=str(ex)[:200])
            self._post_event(
                "error",
                f"Remote re-authentication failed: {ex}",
                status=SnipeStatus.ERROR,
                error_msg=str(ex)[:200],
            )
            return False

    def _confirm_bid_from_follow_up(self, auction_uuid: str) -> bool:
        try:
            auction = with_retry(lambda: get_auction(self.bw_session, auction_uuid))
        except Exception:
            return False
        return auction_shows_bid_applied(auction, self.customer_id, self.bid_amount)

    def run(self) -> None:
        try:
            auction = with_retry(lambda: get_auction(self.bw_session, self.handle))
        except Exception as ex:
            detail = str(ex)[:200]
            self._set_status(SnipeStatus.ERROR, error_msg=detail)
            self._post_event(
                "error",
                f"Remote load failed: {detail}",
                status=SnipeStatus.ERROR,
                error_msg=detail,
            )
            return

        item = auction.get("item") or {}
        title = item.get("title", self.handle)
        auction_uuid = auction.get("id", self.handle)
        self._set_status(SnipeStatus.WATCHING)
        self._post_event("info", f"Remote watching: {title[:45]}", status=SnipeStatus.WATCHING)

        bid_placed = False

        while not self._stop_event.is_set():
            try:
                auction = with_retry(lambda: get_auction(self.bw_session, self.handle))
            except _requests.HTTPError as ex:
                if ex.response is not None and ex.response.status_code == 401:
                    if self._reauthenticate():
                        continue
                detail = extract_http_error_detail(ex)[:200]
                self._set_status(SnipeStatus.ERROR, error_msg=detail)
                self._post_event(
                    "error",
                    f"Remote fetch failed: {detail}",
                    status=SnipeStatus.ERROR,
                    error_msg=detail,
                )
                return
            except Exception as ex:
                detail = str(ex)[:200]
                self._set_status(SnipeStatus.ERROR, error_msg=detail)
                self._post_event(
                    "error",
                    f"Remote fetch failed: {detail}",
                    status=SnipeStatus.ERROR,
                    error_msg=detail,
                )
                return

            winning_bid = auction.get("winningBid") or {}
            cur_bid = winning_bid.get("amount", 0.0)
            winner_id = winning_bid.get("customerId")
            end_str = auction.get("endDate")
            end_time = parse_dt(end_str) if end_str else None
            is_me = winner_id == self.customer_id

            if not end_time:
                self._stop_event.wait(60.0)
                continue

            secs_left = (end_time - datetime.now(timezone.utc)).total_seconds()
            if secs_left <= 0:
                if bid_placed:
                    final_status = SnipeStatus.WON if is_me else SnipeStatus.LOST
                    message = (
                        f"Remote WON: {title[:40]} @ ${cur_bid:.2f}"
                        if is_me
                        else f"Remote LOST: {title[:40]} @ ${cur_bid:.2f}"
                    )
                else:
                    final_status = SnipeStatus.ENDED
                    message = f"Remote ended without bid: {title[:40]}"

                self._set_status(final_status, ended=True)
                self._post_event(
                    final_status.lower(),
                    message,
                    status=final_status,
                )
                return

            if not bid_placed and secs_left <= self.snipe_seconds:
                if cur_bid > self.bid_amount:
                    self._stop_event.wait(0.5)
                    continue

                try:
                    result = place_bid(
                        self.bw_session,
                        auction_uuid,
                        self.customer_id,
                        self.bid_amount,
                    )
                    if result.get("requiresCardAuth"):
                        self._set_status(
                            SnipeStatus.ERROR,
                            error_msg="Card auth required",
                        )
                        self._post_event(
                            "error",
                            "Remote bid requires card auth",
                            status=SnipeStatus.ERROR,
                            error_msg="Card auth required",
                        )
                        return
                    bid_placed = True
                    self._set_status(SnipeStatus.SNIPED, fired=True)
                    self._post_event(
                        "bid",
                        f"Remote bid submitted: ${self.bid_amount:.2f} on {title[:30]}",
                        status=SnipeStatus.SNIPED,
                    )
                except _requests.HTTPError as ex:
                    detail = extract_http_error_detail(ex)
                    if ex.response is not None and ex.response.status_code == 401:
                        if self._reauthenticate():
                            continue
                    if self._confirm_bid_from_follow_up(auction_uuid):
                        bid_placed = True
                        self._set_status(SnipeStatus.SNIPED, fired=True)
                        self._post_event(
                            "bid",
                            (
                                "Remote bid confirmed after follow-up fetch: "
                                f"${self.bid_amount:.2f} on {title[:30]}"
                            ),
                            status=SnipeStatus.SNIPED,
                        )
                    else:
                        detail = detail[:200]
                        self._set_status(SnipeStatus.ERROR, error_msg=detail)
                        self._post_event(
                            "error",
                            f"Remote bid failed: {detail}",
                            status=SnipeStatus.ERROR,
                            error_msg=detail,
                        )
                        return

            if secs_left <= self.snipe_seconds + 5:
                poll = 0.5
            elif secs_left <= 120:
                poll = 5.0
            else:
                poll = 60.0
            self._stop_event.wait(poll)
