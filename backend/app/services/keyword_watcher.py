"""
backend/app/services/keyword_watcher.py — Background thread that periodically
searches BuyWander for new auctions matching each user's keyword watches and
fires notifications for any new matches.

Seen auction IDs are tracked in memory (per user+keyword) with periodic
eviction to prevent unbounded growth.  On restart the first scan will
re-notify for any matches already live — acceptable trade-off for avoiding
a DB migration.
"""

import json
import logging
import threading
import time
from collections import defaultdict

from ..db.database import SessionLocal
from ..db.models import BuyWanderLogin, UserConfig
from ..utils.retry import with_retry
from .buywander_api import create_bw_session, fetch_active_auctions
from . import notification_service

log = logging.getLogger(__name__)

# (user_id, keyword) -> {auction_id: timestamp_added}
_seen: dict[tuple, dict[str, float]] = defaultdict(dict)
_seen_lock = threading.Lock()
_SEEN_MAX_AGE = 7 * 24 * 3600  # evict entries older than 7 days

_SCAN_INTERVAL = 300  # seconds between scans


def _evict_stale():
    """Remove entries older than _SEEN_MAX_AGE from the seen cache."""
    cutoff = time.monotonic() - _SEEN_MAX_AGE
    with _seen_lock:
        for key in list(_seen.keys()):
            bucket = _seen[key]
            stale = [aid for aid, ts in bucket.items() if ts < cutoff]
            for aid in stale:
                del bucket[aid]
            if not bucket:
                del _seen[key]


def _scan_once():
    db = SessionLocal()
    try:
        # Single joined query: load all active logins with their user configs
        rows = (
            db.query(BuyWanderLogin, UserConfig)
            .join(UserConfig, UserConfig.user_id == BuyWanderLogin.user_id)
            .filter(BuyWanderLogin.is_active == True)  # noqa: E712
            .all()
        )

        for login, cfg_rec in rows:
            try:
                cfg = json.loads(cfg_rec.config_json)
            except Exception:
                log.warning("Failed to parse config for user %s", login.user_id)
                continue

            keywords = cfg.get("notifications", {}).get("keyword_watches", [])
            if not keywords:
                continue

            kw_locations = cfg.get("notifications", {}).get("keyword_watch_locations", {})

            bw_session = create_bw_session(login.encrypted_cookies)

            for kw in keywords:
                kw = kw.strip()
                if not kw:
                    continue
                # empty list → no location restriction (search all stores)
                # non-empty list → restrict to those store IDs
                # NOTE: passing an empty list to store_location_ids returns no results
                # on the BuyWander API, so we omit the key entirely when unrestricted.
                restricted_locs = kw_locations.get(kw, [])
                try:
                    fetch_kwargs = dict(
                        page=1,
                        page_size=24,
                        sort_by="NewlyListed",
                        search=kw,
                    )
                    if restricted_locs:
                        fetch_kwargs["store_location_ids"] = restricted_locs
                    result = with_retry(lambda: fetch_active_auctions(bw_session, **fetch_kwargs))
                    auctions = result.get("auctions", []) if isinstance(result, dict) else result
                except Exception:
                    log.warning("Keyword search failed for '%s' (user %s)", kw, login.user_id, exc_info=True)
                    continue

                now = time.monotonic()
                new_matches = []
                with _seen_lock:
                    key = (login.user_id, kw.lower())
                    bucket = _seen[key]
                    for auction in auctions:
                        aid = auction.get("id") or auction.get("handle", "")
                        if aid and aid not in bucket:
                            bucket[aid] = now
                            new_matches.append(auction)

                for auction in new_matches:
                    item = auction.get("item") or {}
                    title = item.get("title") or auction.get("handle", kw)
                    cur_bid = (auction.get("winningBid") or {}).get("amount", 0)
                    handle = item.get("handle") or auction.get("handle", "")
                    url = f"https://www.buywander.com/auctions/{handle}" if handle else ""
                    notification_service.notify_keyword_match(cfg, kw, title, cur_bid, url)
    finally:
        db.close()


class KeywordWatcher(threading.Thread):
    """Daemon thread that runs keyword scans on a fixed interval."""

    def __init__(self, interval: int = _SCAN_INTERVAL):
        super().__init__(daemon=True, name="KeywordWatcher")
        self.interval = interval
        self._stop = threading.Event()

    def run(self):
        # Short initial delay so the server can fully start first
        self._stop.wait(15)
        while not self._stop.is_set():
            try:
                _scan_once()
                _evict_stale()
            except Exception:
                log.exception("Keyword watcher scan failed")
            self._stop.wait(self.interval)

    def stop(self):
        self._stop.set()


# Singleton
_watcher: KeywordWatcher | None = None


def start():
    global _watcher
    if _watcher is None or not _watcher.is_alive():
        _watcher = KeywordWatcher()
        _watcher.start()


def stop():
    global _watcher
    if _watcher:
        _watcher.stop()
