"""
cli/bwsniper/tui/common.py — Shared TUI primitives for the thin client.

Color pairs, safe drawing, prompt definitions, and prompt execution
via API calls to the backend server.
"""

import curses
import threading
import webbrowser
from datetime import datetime, timezone

from ..config import SITE_BASE, BROWSE_SORTS, BROWSE_SORT_LABELS, QUICK_FILTERS
from ..state import ClientState

# ── Color pair indices ────────────────────────────────────────────────────────

CP_HEADER  = 1
CP_WON     = 2
CP_LOST    = 3
CP_LEADING = 4
CP_SNIPED  = 5
CP_DIM     = 6
CP_ERROR   = 7
CP_BOLD    = 8


# ── Low-level drawing helpers ─────────────────────────────────────────────────

def _safe(stdscr, y: int, x: int, s: str, attr: int = 0):
    """Write string s at (y, x), clamped to screen bounds. Never raises."""
    max_y, max_x = stdscr.getmaxyx()
    if y < 0 or y >= max_y or x < 0 or x >= max_x:
        return
    try:
        stdscr.addstr(y, x, s[:max(0, max_x - x - 1)], attr)
    except curses.error:
        pass


def _hline(stdscr, y: int, char: str = "─"):
    """Draw a full-width horizontal line at row y."""
    _, max_x = stdscr.getmaxyx()
    _safe(stdscr, y, 0, char * (max_x - 1))


# ── Prompt definitions ────────────────────────────────────────────────────────

PROMPT_FIELDS = {
    "add":        [("url",     "Auction URL or UUID",                    ""),
                   ("amount",  "Bid amount ($)",                         ""),
                   ("seconds", "Snipe seconds",                          "5")],
    "rm":         [("id",      "Snipe ID to remove",                     "")],
    "bid":        [("id",      "Snipe ID",                               ""),
                   ("amount",  "New bid amount ($)",                     "")],
    "snipe":      [("id",      "Snipe ID",                               ""),
                   ("seconds", "New snipe seconds",                      "5")],
    "pay":        [("confirm", "Pay cart with saved card? (y/n)",        "y")],
    "sched":      [("day",     "Pickup date (YYYY-MM-DD)",               ""),
                   ("slot",    "Slot # to book (see list above)",        "1")],
    "cancel_apt": [("confirm", "Cancel this appointment? (y/n)",         "n")],
    "rm_cart":    [("id",      "Item auction_id to remove",              ""),
                   ("confirm", "Confirm removal? (y/n)",                 "y")],
    "browse_snipe": [("amount",  "Bid / snipe amount ($)",               ""),
                     ("seconds", "Snipe seconds before end",             "5")],
}

PROMPT_TITLES = {
    "add":          "Add snipe",
    "rm":           "Remove snipe",
    "bid":          "Change bid amount",
    "snipe":        "Change snipe timing",
    "pay":          "Pay cart",
    "sched":        "Schedule pickup",
    "cancel_apt":   "Cancel appointment",
    "rm_cart":      "Remove cart item",
    "browse_snipe": "Snipe from browse",
}


def _snipe_header_str(state: ClientState) -> str:
    """Return a header fragment like '  │  3 queued  │  Next: 4m 12s'."""
    now = datetime.now(timezone.utc)
    with state.lock:
        active = [s for s in state.snipes
                  if s.get("status") not in ("Won", "Lost", "Ended", "Error")]
    if not active:
        return ""
    n = len(active)
    next_secs = None
    for s in active:
        et = s.get("end_time") or s.get("endDate") or ""
        if et:
            try:
                from datetime import datetime as _dt
                end = _dt.fromisoformat(et.replace("Z", "+00:00"))
                diff = (end - now).total_seconds()
                if diff > 0 and (next_secs is None or diff < next_secs):
                    next_secs = diff
            except Exception:
                pass
    if next_secs is not None:
        secs = int(next_secs)
        if secs >= 3600:
            t = f"{secs // 3600}h {(secs % 3600) // 60}m"
        elif secs >= 60:
            t = f"{secs // 60}m {secs % 60}s"
        else:
            t = f"{secs}s"
        return f"  │  {n} queued  │  Next: {t}"
    return f"  │  {n} queued"


def _fresh_prompt() -> dict:
    """Return a blank prompt state dict."""
    return {"mode": "", "step": 0, "data": {}, "buf": "", "error": ""}


def normalize_auction_url(raw: str) -> str:
    """Accept a bare UUID, a slug, or a full URL — always return a full URL."""
    raw = raw.strip()
    if raw.startswith("http"):
        return raw
    # Simple UUID check
    parts = raw.replace("-", "")
    if len(parts) == 32 and all(c in "0123456789abcdefABCDEF" for c in parts):
        return f"{SITE_BASE}/auction/{raw}"
    return f"{SITE_BASE}/auctions/{raw}"


def fmt_time(secs: float) -> str:
    """Format seconds as e.g. '1h 23m 45s'."""
    secs = int(secs)
    if secs < 0:
        return "Ended"
    if secs >= 86400:
        d = secs // 86400
        h = (secs % 86400) // 3600
        return f"{d}d {h}h"
    if secs >= 3600:
        h = secs // 3600
        m = (secs % 3600) // 60
        return f"{h}h {m}m"
    if secs >= 60:
        m = secs // 60
        s = secs % 60
        return f"{m}m {s}s"
    return f"{secs}s"


def parse_dt(s: str):
    """Parse an ISO datetime string, handling 'Z' suffix."""
    if not s:
        raise ValueError("empty")
    from datetime import datetime as _dt
    return _dt.fromisoformat(s.replace("Z", "+00:00"))


# ── Prompt execution (via API) ────────────────────────────────────────────────

def execute_prompt(state: ClientState, mode: str, data: dict) -> str:
    """Execute a completed prompt via server API. Returns '' on success or error."""

    if mode == "add":
        url = normalize_auction_url(data["url"])
        try:
            amount = float(data["amount"])
        except ValueError:
            return "Bid amount must be a number"
        try:
            secs = int(data.get("seconds") or 5)
        except ValueError:
            return "Snipe seconds must be a whole number"
        state.add_log(f"➕ Adding: {url[-50:]}  bid=${amount:.2f}  snipe={secs}s")
        try:
            state.client.create_snipe(
                state.active_login_id, url, amount, secs)
            state.refresh_snipes()
            return ""
        except Exception as ex:
            return f"Failed: {ex}"

    if mode == "rm":
        snipe_id = data["id"].strip()
        try:
            state.client.delete_snipe(snipe_id)
            state.add_log(f"🗑  Removed snipe {snipe_id}")
            state.refresh_snipes()
            return ""
        except Exception as ex:
            return f"Remove failed: {ex}"

    if mode == "bid":
        snipe_id = data["id"].strip()
        try:
            amount = float(data["amount"])
        except ValueError:
            return "Invalid amount"
        try:
            state.client.update_snipe(snipe_id, bid_amount=amount)
            state.add_log(f"✏️  Snipe {snipe_id} bid → ${amount:.2f}")
            state.refresh_snipes()
            return ""
        except Exception as ex:
            return f"Update failed: {ex}"

    if mode == "snipe":
        snipe_id = data["id"].strip()
        try:
            secs = int(data["seconds"])
        except ValueError:
            return "Invalid seconds"
        try:
            state.client.update_snipe(snipe_id, snipe_seconds=secs)
            state.add_log(f"⏱  Snipe {snipe_id} window → {secs}s")
            state.refresh_snipes()
            return ""
        except Exception as ex:
            return f"Update failed: {ex}"

    if mode == "pay":
        if data.get("confirm", "").strip().lower() not in ("y", "yes"):
            state.add_log("💳 Pay cancelled.")
            return ""
        state.add_log("💳 Initiating payment…")
        try:
            result = state.client.pay_cart(
                state.active_login_id, state.browse_location_id)
            if isinstance(result, dict) and result.get("clientSecret"):
                state.add_log(
                    "⚠  Stripe auth required — open buywander.com/dashboard/cart")
            else:
                state.add_log("✅ Payment submitted!  Cart refreshing…")
                threading.Thread(
                    target=state.refresh_cart, daemon=True).start()
            return ""
        except Exception as ex:
            return f"Payment failed: {ex}"

    if mode == "sched":
        day_raw = data.get("day", "").strip()
        slot_raw = data.get("slot", "1").strip()
        try:
            slot_idx = int(slot_raw) - 1
        except ValueError:
            return "Slot # must be a whole number"
        with state.lock:
            avail = list(getattr(state, '_avail_slots', []))
        if not avail:
            return "No available slots loaded"
        if slot_idx < 0 or slot_idx >= len(avail):
            return f"Slot # must be 1–{len(avail)}"
        slot_date = avail[slot_idx].get("date", "")
        if not slot_date:
            return "Slot is missing a date"
        state.add_log(f"📅 Booking pickup: {slot_date}")
        try:
            state.client.create_appointment(
                state.active_login_id,
                state.browse_location_id,
                slot_date)
            state.add_log("✅ Appointment booked!  Cart refreshing…")
            threading.Thread(target=state.refresh_cart, daemon=True).start()
            return ""
        except Exception as ex:
            return f"Booking failed: {ex}"

    if mode == "rm_cart":
        if data.get("confirm", "").strip().lower() not in ("y", "yes"):
            state.add_log("⎋  Cart removal cancelled.")
            return ""
        auction_id = data.get("id", "").strip()
        if not auction_id:
            return "No auction ID provided"
        state.add_log(f"🗑 Removing item {auction_id[:12]}…")
        try:
            state.client.remove_cart_item(state.active_login_id, auction_id)
            state.add_log("✅ Item removed from cart.  Refreshing…")
            threading.Thread(target=state.refresh_cart, daemon=True).start()
            return ""
        except Exception as ex:
            return f"Removal failed: {ex}"

    if mode == "cancel_apt":
        if data.get("confirm", "").strip().lower() not in ("y", "yes"):
            state.add_log("🗑 Cancel appointment — aborted.")
            return ""
        with state.lock:
            cd = state.cart_data
        visit = None
        if cd:
            for v in (cd.get("visits") or []):
                if not v.get("cancelledAt") and v.get("status") != "Cancelled":
                    visit = v
                    break
        if not visit:
            return "No active appointment found"
        state.add_log("🗑 Cancelling appointment…")
        try:
            state.client.cancel_appointment(
                state.active_login_id,
                visit["id"], visit["date"])
            state.add_log("✅ Appointment cancelled.  Cart refreshing…")
            threading.Thread(target=state.refresh_cart, daemon=True).start()
            return ""
        except Exception as ex:
            return f"Cancel failed: {ex}"

    if mode == "browse_snipe":
        url = data.get("_url", "")
        if not url:
            return "No auction URL"
        try:
            amount = float(data["amount"])
        except ValueError:
            return "Bid amount must be a number"
        try:
            secs = int(data.get("seconds") or 5)
        except ValueError:
            return "Snipe seconds must be a whole number"
        state.add_log(
            f"➕ Sniping: {url[-48:]}  bid=${amount:.2f}  snipe={secs}s")
        try:
            state.client.create_snipe(
                state.active_login_id, url, amount, secs)
            state.refresh_snipes()
            return ""
        except Exception as ex:
            return f"Failed: {ex}"

    return f"Unknown mode: {mode}"
