"""
cli/bwsniper/api_client.py — HTTP + WebSocket client for the BWSNiper FastAPI backend.

This is the sole network layer for the TUI client. All server communication
goes through the ApiClient singleton.
"""

import json
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

import requests
import websocket  # websocket-client library

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_BASE = "http://localhost:8000"
WS_RECONNECT_DELAY = 3


class AuthError(Exception):
    """Raised when auth tokens are expired/invalid and cannot be refreshed."""


class ApiClient:
    """Thin HTTP + WebSocket wrapper for server communication."""

    def __init__(self, base_url: str = DEFAULT_BASE):
        self.base_url = base_url.rstrip("/")
        self.access_token: str = ""
        self.refresh_token: str = ""
        self.user_id: str = ""
        self.display_name: str = ""
        self._session = requests.Session()

        # WebSocket
        self._ws: Optional[websocket.WebSocketApp] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._ws_running = False
        self._ws_listeners: List[Callable[[dict], None]] = []

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.access_token:
            h["Authorization"] = f"Bearer {self.access_token}"
        return h

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api{path}"

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        resp = self._session.request(
            method, self._url(path), headers=self._headers(), **kwargs
        )
        if resp.status_code == 401 and self.refresh_token:
            if self._do_refresh():
                resp = self._session.request(
                    method, self._url(path), headers=self._headers(), **kwargs
                )
        if resp.status_code == 401:
            raise AuthError("Session expired. Please log in again.")
        return resp

    def _get(self, path: str, params: Optional[dict] = None) -> requests.Response:
        return self._request("GET", path, params=params)

    def _post(self, path: str, data: Any = None) -> requests.Response:
        return self._request("POST", path, json=data)

    def _put(self, path: str, data: Any = None) -> requests.Response:
        return self._request("PUT", path, json=data)

    def _delete(self, path: str, params: Optional[dict] = None,
                data: Any = None) -> requests.Response:
        return self._request("DELETE", path, params=params, json=data)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def register(self, email: str, password: str, display_name: str = "") -> dict:
        body = {"email": email, "password": password}
        if display_name:
            body["display_name"] = display_name
        resp = self._session.post(
            self._url("/auth/register"),
            headers={"Content-Type": "application/json"},
            json=body,
        )
        resp.raise_for_status()
        return resp.json()

    def login(self, email: str, password: str) -> dict:
        resp = self._session.post(
            self._url("/auth/login"),
            headers={"Content-Type": "application/json"},
            json={"email": email, "password": password},
        )
        if resp.status_code == 401:
            raise AuthError("Invalid email or password.")
        resp.raise_for_status()
        data = resp.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.user_id = data.get("user_id", "")
        self.display_name = data.get("display_name", "")
        return data

    def _do_refresh(self) -> bool:
        resp = self._session.post(
            self._url("/auth/refresh"),
            headers={"Content-Type": "application/json"},
            json={"refresh_token": self.refresh_token},
        )
        if resp.status_code != 200:
            return False
        data = resp.json()
        self.access_token  = data["access_token"]
        self.refresh_token = data.get("refresh_token", self.refresh_token)
        # Re-send auth on the open WS connection with the new access token
        if self._ws:
            try:
                self._ws.send(json.dumps({
                    "type": "auth", "token": self.access_token}))
            except Exception:
                pass
        return True

    # ------------------------------------------------------------------
    # BuyWander Logins
    # ------------------------------------------------------------------

    def list_logins(self) -> list:
        return self._get("/logins").json()

    def add_login(self, bw_email: str, bw_password: str,
                  display_name: str = "") -> dict:
        body = {"bw_email": bw_email, "bw_password": bw_password}
        if display_name:
            body["display_name"] = display_name
        resp = self._post("/logins", body)
        resp.raise_for_status()
        return resp.json()

    def update_login(self, login_id: str, **fields) -> dict:
        resp = self._put(f"/logins/{login_id}", fields)
        resp.raise_for_status()
        return resp.json()

    def delete_login(self, login_id: str) -> None:
        self._delete(f"/logins/{login_id}").raise_for_status()

    # ------------------------------------------------------------------
    # Snipes
    # ------------------------------------------------------------------

    def list_snipes(self, login_id: str = "", status: str = "") -> list:
        params = {}
        if login_id:
            params["login_id"] = login_id
        if status:
            params["status"] = status
        return self._get("/snipes", params=params).json()

    def create_snipe(self, login_id: str, url: str, bid_amount: float,
                     snipe_seconds: int = 10) -> dict:
        resp = self._post("/snipes", {
            "login_id": login_id,
            "url": url,
            "bid_amount": bid_amount,
            "snipe_seconds": snipe_seconds,
        })
        resp.raise_for_status()
        return resp.json()

    def get_snipe(self, snipe_id: str) -> dict:
        return self._get(f"/snipes/{snipe_id}").json()

    def update_snipe(self, snipe_id: str, **fields) -> dict:
        resp = self._put(f"/snipes/{snipe_id}", fields)
        resp.raise_for_status()
        return resp.json()

    def delete_snipe(self, snipe_id: str) -> None:
        self._delete(f"/snipes/{snipe_id}").raise_for_status()

    # ------------------------------------------------------------------
    # Auctions (browse)
    # ------------------------------------------------------------------

    def search_auctions(self, login_id: str, sort: str = "EndingSoonest",
                        search: str = "", page: int = 1, page_size: int = 24,
                        conditions: Optional[list] = None,
                        location_ids: Optional[list] = None,
                        price_min: Optional[float] = None,
                        price_max: Optional[float] = None,
                        quick_filters: Optional[list] = None) -> dict:
        body: Dict[str, Any] = {
            "login_id": login_id,
            "sort": sort,
            "page": page,
            "page_size": page_size,
        }
        if search:
            body["search"] = search
        if conditions:
            body["conditions"] = conditions
        if location_ids:
            body["location_ids"] = location_ids
        if price_min is not None:
            body["price_min"] = price_min
        if price_max is not None:
            body["price_max"] = price_max
        if quick_filters:
            body["quick_filters"] = quick_filters
        resp = self._post("/auctions/search", body)
        resp.raise_for_status()
        return resp.json()

    def get_auction_detail(self, auction_id: str) -> dict:
        return self._get(f"/auctions/{auction_id}").json()

    def list_locations(self) -> list:
        return self._get("/auctions/locations/list").json()

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(self, search: str = "", login_id: str = "") -> list:
        params = {}
        if search:
            params["search"] = search
        if login_id:
            params["login_id"] = login_id
        return self._get("/history", params=params).json()

    def refresh_history(self, login_id: str) -> dict:
        resp = self._post("/history/refresh", {"login_id": login_id})
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Cart
    # ------------------------------------------------------------------

    def get_cart(self, login_id: str, store_location_id: str) -> dict:
        return self._get(f"/cart/{login_id}",
                         params={"store_location_id": store_location_id}).json()

    def pay_cart(self, login_id: str, store_location_id: str) -> dict:
        resp = self._post(f"/cart/{login_id}/pay",
                          {"store_location_id": store_location_id})
        resp.raise_for_status()
        return resp.json()

    def get_open_slots(self, login_id: str, location_id: str,
                       day: str) -> list:
        return self._get(f"/cart/{login_id}/open-slots",
                         params={"location_id": location_id,
                                 "day": day}).json()

    def get_removal_status(self, login_id: str,
                           store_location_id: str) -> dict:
        return self._get(f"/cart/{login_id}/removal-status",
                         params={"store_location_id": store_location_id}).json()

    def create_appointment(self, login_id: str, location_id: str,
                           visit_date_iso: str) -> dict:
        resp = self._post(f"/cart/{login_id}/appointments", {
            "location_id": location_id,
            "visit_date_iso": visit_date_iso,
        })
        resp.raise_for_status()
        return resp.json()

    def cancel_appointment(self, login_id: str, visit_id: str,
                           visit_date: str) -> dict:
        resp = self._delete(f"/cart/{login_id}/appointments/{visit_id}",
                            params={"visit_date": visit_date})
        resp.raise_for_status()
        return resp.json()

    def remove_cart_item(self, login_id: str, auction_id: str,
                         reason: str = "UserRemoval",
                         notes: str = "") -> dict:
        resp = self._delete(f"/cart/{login_id}/items",
                            data={"auction_id": auction_id,
                                  "reason": reason, "notes": notes})
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def get_settings(self) -> dict:
        return self._get("/settings").json()

    def update_settings(self, config: dict) -> dict:
        resp = self._put("/settings", {"config": config})
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------

    def add_ws_listener(self, fn: Callable[[dict], None]) -> None:
        self._ws_listeners.append(fn)

    def remove_ws_listener(self, fn: Callable[[dict], None]) -> None:
        self._ws_listeners = [f for f in self._ws_listeners if f is not fn]

    def start_ws(self) -> None:
        """Start WebSocket connection in a background thread."""
        if self._ws_running:
            return
        self._ws_running = True
        self._ws_thread = threading.Thread(target=self._ws_loop, daemon=True)
        self._ws_thread.start()

    def stop_ws(self) -> None:
        self._ws_running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

    def _ws_loop(self) -> None:
        ws_base = self.base_url.replace("http://", "ws://").replace(
            "https://", "wss://")
        while self._ws_running:
            try:
                url = f"{ws_base}/ws"
                self._ws = websocket.WebSocketApp(
                    url,
                    on_open=self._on_ws_open,
                    on_message=self._on_ws_message,
                    on_error=self._on_ws_error,
                    on_close=self._on_ws_close,
                )
                self._ws.run_forever()
            except Exception:
                pass
            if self._ws_running:
                time.sleep(WS_RECONNECT_DELAY)

    def _on_ws_open(self, ws) -> None:
        """Send auth message immediately after connection is established."""
        try:
            ws.send(json.dumps({"type": "auth", "token": self.access_token}))
        except Exception:
            pass

    def _on_ws_message(self, ws, message: str) -> None:
        try:
            data = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            return
        for fn in self._ws_listeners:
            try:
                fn(data)
            except Exception:
                pass

    def _on_ws_error(self, ws, error) -> None:
        pass  # reconnect handled in _ws_loop

    def _on_ws_close(self, ws, close_status_code, close_msg) -> None:
        pass
