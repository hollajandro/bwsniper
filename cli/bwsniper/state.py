"""
cli/bwsniper/state.py — Client-side state cache backed by the API server.

Replaces the monolithic AppState that did direct BW API calls.
All data comes from the FastAPI backend; background threads here only
handle periodic polling and WebSocket event application.
"""

import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .api_client import ApiClient

MAX_LOG = 300


class ClientState:
    """Thread-safe state container for the TUI client."""

    def __init__(self, client: ApiClient):
        self.client = client
        self.lock = threading.RLock()

        # Auth info
        self.user_display = client.display_name or ""

        # BW Logins
        self.logins: List[dict] = []
        self.active_login_id: str = ""
        self.active_login_name: str = ""
        self.customer_id: str = ""

        # Monitor tab — snipes from server
        self.snipes: List[dict] = []          # active snipes
        self.past_snipes: List[dict] = []     # terminal snipes

        # History tab
        self.history: List[dict] = []
        self.history_search: str = ""

        # Cart tab
        self.cart_data: Optional[dict] = None
        self.cart_checkout: list = []
        self.cart_methods: list = []
        self.cart_loading: bool = False

        # Browse tab
        self.browse_items: list = []
        self.browse_total: int = 0
        self.browse_page: int = 1
        self.browse_sort: str = "EndingSoonest"
        self.browse_search: str = ""
        self.browse_conditions: list = []
        self.browse_location_id: str = ""
        self.browse_locations: list = []
        self.browse_price_min: Optional[float] = None
        self.browse_price_max: Optional[float] = None
        self.browse_quick_filters: list = []
        self.browse_cursor: int = 0
        self.browse_scroll: int = 0
        self.browse_loading: bool = False
        self.browse_detail_cache: Dict[str, dict] = {}
        self.browse_detail_status: Dict[str, str] = {}

        # Log
        self.log: deque = deque(maxlen=MAX_LOG)

        # Settings
        self.user_config: dict = {}

        # Fireworks
        self.fireworks: Optional[dict] = None
        self.fireworks_start: float = 0.0

        # Poller thread
        self._poll_thread: Optional[threading.Thread] = None
        self._running = False

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def add_log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        with self.lock:
            self.log.append(f"[{ts}] {msg}")

    # ------------------------------------------------------------------
    # Data refresh helpers (run on background threads)
    # ------------------------------------------------------------------

    def refresh_logins(self) -> None:
        try:
            logins = self.client.list_logins()
            with self.lock:
                self.logins = logins
                if not self.active_login_id and logins:
                    self.active_login_id = logins[0].get("id", "")
                    self.active_login_name = (
                        logins[0].get("display_name") or
                        logins[0].get("bw_email", ""))
                    self.customer_id = logins[0].get("customer_id", "")
        except Exception as e:
            self.add_log(f"Logins refresh error: {e}")

    def refresh_snipes(self) -> None:
        try:
            all_snipes = self.client.list_snipes()
            terminal = {"Won", "Lost", "Ended", "Error", "Deleted"}
            with self.lock:
                self.snipes = [s for s in all_snipes
                               if s.get("status") not in terminal]
                self.past_snipes = [s for s in all_snipes
                                    if s.get("status") in terminal]
        except Exception as e:
            self.add_log(f"Snipes refresh error: {e}")

    def refresh_history(self) -> None:
        try:
            self.history = self.client.get_history(
                login_id=self.active_login_id)
        except Exception as e:
            self.add_log(f"History refresh error: {e}")

    def refresh_cart(self, store_location_id: str = "") -> None:
        if not self.active_login_id:
            return
        loc = store_location_id or self.browse_location_id
        if not loc:
            return
        with self.lock:
            self.cart_loading = True
        try:
            data = self.client.get_cart(self.active_login_id, loc)
            with self.lock:
                self.cart_data = data.get("cart_data")
                self.cart_checkout = data.get("reserved", [])
                self.cart_methods = data.get("methods", [])
        except Exception as e:
            self.add_log(f"Cart refresh error: {e}")
        finally:
            with self.lock:
                self.cart_loading = False

    def refresh_browse(self) -> None:
        if not self.active_login_id:
            return
        with self.lock:
            self.browse_loading = True
        try:
            data = self.client.search_auctions(
                login_id=self.active_login_id,
                sort=self.browse_sort,
                search=self.browse_search,
                page=self.browse_page,
                conditions=self.browse_conditions or None,
                location_ids=([self.browse_location_id]
                              if self.browse_location_id else None),
                price_min=self.browse_price_min,
                price_max=self.browse_price_max,
                quick_filters=self.browse_quick_filters or None,
            )
            items = data if isinstance(data, list) else data.get("items", [])
            total = data.get("total", len(items)) if isinstance(data, dict) else len(items)
            with self.lock:
                self.browse_items = items
                self.browse_total = total
        except Exception as e:
            self.add_log(f"Browse refresh error: {e}")
        finally:
            with self.lock:
                self.browse_loading = False

    def refresh_locations(self) -> None:
        try:
            locs = self.client.list_locations()
            with self.lock:
                self.browse_locations = locs
                if not self.browse_location_id and locs:
                    first = locs[0]
                    self.browse_location_id = (
                        first.get("id") or
                        first.get("storeLocationId", ""))
        except Exception as e:
            self.add_log(f"Locations refresh error: {e}")

    def refresh_settings(self) -> None:
        try:
            data = self.client.get_settings()
            with self.lock:
                self.user_config = data.get("config", data)
        except Exception as e:
            self.add_log(f"Settings refresh error: {e}")

    def fetch_auction_detail(self, auction_id: str) -> None:
        """Background-fetch full detail for browse detail modal."""
        with self.lock:
            self.browse_detail_status[auction_id] = "loading"
        try:
            detail = self.client.get_auction_detail(auction_id)
            with self.lock:
                self.browse_detail_cache[auction_id] = detail
                self.browse_detail_status[auction_id] = "done"
        except Exception as e:
            with self.lock:
                self.browse_detail_status[auction_id] = "error"
            self.add_log(f"Detail fetch error: {e}")

    # ------------------------------------------------------------------
    # Background poller
    # ------------------------------------------------------------------

    def start_poller(self) -> None:
        """Start the periodic refresh thread + WebSocket listener."""
        self._running = True
        # Initial data load
        self._initial_load()
        # WebSocket for real-time updates
        self.client.add_ws_listener(self._on_ws_event)
        self.client.start_ws()
        # Periodic poller
        self._poll_thread = threading.Thread(
            target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def stop_poller(self) -> None:
        self._running = False
        self.client.stop_ws()

    def _initial_load(self) -> None:
        """Fetch all data on startup."""
        self.refresh_logins()
        self.refresh_snipes()
        self.refresh_locations()
        self.refresh_settings()
        # These can run after the TUI starts drawing
        t = threading.Thread(target=self._deferred_load, daemon=True)
        t.start()

    def _deferred_load(self) -> None:
        self.refresh_history()
        if self.browse_location_id:
            self.refresh_cart(self.browse_location_id)
        self.refresh_browse()

    def _poll_loop(self) -> None:
        """Poll snipes every 5s, other data less frequently."""
        tick = 0
        while self._running:
            time.sleep(5)
            tick += 1
            try:
                self.refresh_snipes()
                if tick % 6 == 0:   # every 30s
                    self.refresh_history()
                    if self.active_login_id and self.browse_location_id:
                        self.refresh_browse()
                if tick % 12 == 0:  # every 60s
                    self.refresh_logins()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # WebSocket event handler
    # ------------------------------------------------------------------

    def _on_ws_event(self, data: dict) -> None:
        # Server sends {"type": "...", "data": {...}} — use "type" as the key
        event = data.get("type", data.get("event", ""))
        payload = data.get("data", data)

        if event == "snipe.status_changed":
            self._apply_snipe_update(payload)
        elif event in ("log", "log.event"):
            msg = payload.get("message", str(payload))
            self.add_log(msg)
        elif event == "history.new":
            with self.lock:
                self.history.insert(0, payload)
        elif event == "snipe.won":
            # Fireworks already triggered via snipe.status_changed;
            # refresh history to pick up the new record.
            threading.Thread(target=self.refresh_history, daemon=True).start()
        elif event == "auth_ok":
            pass  # server acknowledged our auth — nothing to do

    def _apply_snipe_update(self, payload: dict) -> None:
        snipe_id = payload.get("snipe_id") or payload.get("id")
        status = payload.get("status", "")
        terminal = {"Won", "Lost", "Ended", "Error", "Deleted"}

        with self.lock:
            # Find and update in active list
            for i, s in enumerate(self.snipes):
                if s.get("id") == snipe_id:
                    self.snipes[i].update(payload)
                    if status in terminal:
                        moved = self.snipes.pop(i)
                        self.past_snipes.insert(0, moved)
                    break
            else:
                # Not in active list — might be new or already in past
                if status not in terminal:
                    self.snipes.append(payload)

            # Trigger fireworks on win
            if status == "Won":
                title = payload.get("title", "Auction")
                price = payload.get("current_bid") or payload.get("bid_amount")
                self.fireworks = {"title": title, "price": price}
                self.fireworks_start = time.time()

    # ------------------------------------------------------------------
    # Login switching
    # ------------------------------------------------------------------

    def set_active_login(self, login_id: str) -> None:
        with self.lock:
            self.active_login_id = login_id
            for lg in self.logins:
                if lg.get("id") == login_id:
                    self.active_login_name = (
                        lg.get("display_name") or lg.get("bw_email", ""))
                    self.customer_id = lg.get("customer_id", "")
                    break
        # Refresh data for new login
        t = threading.Thread(target=self._deferred_load, daemon=True)
        t.start()
