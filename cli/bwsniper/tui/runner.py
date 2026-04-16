"""
cli/bwsniper/tui/runner.py — Main TUI event loop for the thin client.

All data comes from the API server via ClientState.  No direct BuyWander
API calls happen here.
"""

import time
import curses
import threading
import webbrowser
from datetime import datetime
from urllib.parse import quote_plus

from ..config import (
    VIEW_MONITOR, VIEW_HISTORY, VIEW_CART, VIEW_BROWSE,
    VIEW_LOG, VIEW_SETTINGS, VIEW_COUNT,
    BROWSE_SORTS, BROWSE_SORT_LABELS, QUICK_FILTERS, COND_CYCLE,
)
from ..state import ClientState
from .common import (
    CP_HEADER, CP_WON, CP_LOST, CP_LEADING, CP_SNIPED, CP_DIM, CP_ERROR, CP_BOLD,
    PROMPT_FIELDS, PROMPT_TITLES,
    _fresh_prompt, execute_prompt,
)
from .monitor import draw_ui, draw_fireworks, FIREWORKS_DURATION
from .history import draw_history, draw_history_search_bar
from .cart import draw_cart
from .browse import draw_browse, _auction_url
from .log import draw_log
from .settings import (
    draw_settings, SETTINGS_DEFS, FIELD_INDICES,
    fresh_settings_state, settings_move,
    _get_nested, _set_nested,
)


def run_tui(stdscr, state: ClientState):
    curses.curs_set(1)
    stdscr.nodelay(True)
    stdscr.keypad(True)

    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(CP_HEADER,  curses.COLOR_WHITE,  curses.COLOR_BLUE)
    curses.init_pair(CP_WON,     curses.COLOR_GREEN,  -1)
    curses.init_pair(CP_LOST,    curses.COLOR_RED,    -1)
    curses.init_pair(CP_LEADING, curses.COLOR_GREEN,  -1)
    curses.init_pair(CP_SNIPED,  curses.COLOR_YELLOW, -1)
    curses.init_pair(CP_DIM,     curses.COLOR_WHITE,  -1)
    curses.init_pair(CP_ERROR,   curses.COLOR_RED,    -1)
    curses.init_pair(CP_BOLD,    curses.COLOR_WHITE,  -1)

    prompt             = _fresh_prompt()
    current_view       = VIEW_MONITOR
    hist_scroll        = 0
    hist_search_buf    = ""
    hist_search_active = False
    log_scroll         = 0
    settings_st        = fresh_settings_state()

    while True:
        # ── Fireworks ────────────────────────────────────────────────────
        with state.lock:
            fw = state.fireworks
        if fw:
            fw_title = fw.get("title", "Auction")
            fw_price = float(fw.get("price") or 0)
            fw_elapsed = time.time() - state.fireworks_start
            draw_fireworks(stdscr, fw_title, fw_price, fw_elapsed)
            try:
                ch = stdscr.getch()
            except curses.error:
                ch = -1
            if ch != -1 or fw_elapsed >= FIREWORKS_DURATION:
                with state.lock:
                    state.fireworks = None
                stdscr.clear()
            time.sleep(0.05)
            continue

        # ── Draw current view ────────────────────────────────────────────
        if current_view == VIEW_HISTORY:
            hist_scroll = draw_history(stdscr, state, hist_scroll,
                                       search_active=hist_search_active,
                                       search_buf=hist_search_buf)
        elif current_view == VIEW_CART:
            draw_cart(stdscr, state, prompt)
        elif current_view == VIEW_BROWSE:
            draw_browse(stdscr, state, prompt)
        elif current_view == VIEW_LOG:
            log_scroll = draw_log(stdscr, state, log_scroll)
        elif current_view == VIEW_SETTINGS:
            draw_settings(stdscr, state, settings_st)
        else:
            draw_ui(stdscr, state, prompt)

        try:
            ch = stdscr.getch()
        except curses.error:
            ch = -1

        if ch == -1:
            time.sleep(0.1)
            continue

        # ── Tab: cycle views ─────────────────────────────────────────────
        if ch == ord('\t') and not prompt["mode"] and not settings_st["edit"]:
            current_view = (current_view + 1) % VIEW_COUNT
            if current_view == VIEW_HISTORY:
                threading.Thread(
                    target=state.refresh_history, daemon=True).start()
            elif current_view == VIEW_CART:
                threading.Thread(
                    target=state.refresh_cart, daemon=True).start()
            elif current_view == VIEW_BROWSE:
                threading.Thread(
                    target=state.refresh_browse, daemon=True).start()
            elif current_view == VIEW_SETTINGS:
                settings_st["msg"] = ""
                threading.Thread(
                    target=state.refresh_settings, daemon=True).start()
            stdscr.clear()
            continue

        # ── History view ─────────────────────────────────────────────────
        if current_view == VIEW_HISTORY:
            if hist_search_active:
                if ch in (curses.KEY_BACKSPACE, 127, 8):
                    hist_search_buf = hist_search_buf[:-1]
                    with state.lock:
                        state.history_search = hist_search_buf
                    hist_scroll = 0
                elif ch in (ord('\n'), ord('\r'), curses.KEY_ENTER, 27):
                    hist_search_active = False
                elif 32 <= ch <= 126:
                    hist_search_buf += chr(ch)
                    with state.lock:
                        state.history_search = hist_search_buf
                    hist_scroll = 0
            else:
                if ch == curses.KEY_UP:
                    hist_scroll = max(0, hist_scroll - 1)
                elif ch == curses.KEY_DOWN:
                    hist_scroll += 1
                elif ch == curses.KEY_RESIZE:
                    stdscr.clear()
                elif ch == ord('/'):
                    hist_search_active = True
                    hist_scroll = 0
                elif ch == 27:
                    if hist_search_buf:
                        hist_search_buf    = ""
                        hist_search_active = False
                        hist_scroll        = 0
                        with state.lock:
                            state.history_search = ""
                elif ch in (ord('q'), ord('Q')):
                    return
            continue

        # ── Log view ─────────────────────────────────────────────────────
        if current_view == VIEW_LOG:
            if ch == curses.KEY_UP:
                log_scroll += 1
            elif ch == curses.KEY_DOWN:
                log_scroll = max(0, log_scroll - 1)
            elif ch == curses.KEY_RESIZE:
                stdscr.clear()
            elif ch in (ord('q'), ord('Q')):
                return
            continue

        # ── Settings view ────────────────────────────────────────────────
        if current_view == VIEW_SETTINGS:
            _handle_settings(ch, state, settings_st)
            if ch == curses.KEY_RESIZE:
                stdscr.clear()
            continue

        # ── Resize ───────────────────────────────────────────────────────
        if ch == curses.KEY_RESIZE:
            stdscr.clear()
            continue

        # ── Escape ───────────────────────────────────────────────────────
        if ch == 27:
            if prompt["mode"]:
                state.add_log(
                    f"⎋  Cancelled: "
                    f"{PROMPT_TITLES.get(prompt['mode'], prompt['mode'])}")
                prompt = _fresh_prompt()
            elif current_view == VIEW_BROWSE:
                with state.lock:
                    had_any = (bool(state.browse_search)
                               or bool(state.browse_quick_filters)
                               or bool(state.browse_conditions)
                               or state.browse_price_min is not None
                               or state.browse_price_max is not None)
                if had_any:
                    with state.lock:
                        state.browse_search = ""
                        state.browse_quick_filters = []
                        state.browse_conditions = []
                        state.browse_price_min = None
                        state.browse_price_max = None
                    threading.Thread(
                        target=state.refresh_browse, daemon=True).start()
                    state.add_log("⎋  All filters cleared")
            continue

        # ── Browse view ──────────────────────────────────────────────────
        if current_view == VIEW_BROWSE:
            p_mode = prompt["mode"]

            if p_mode == "browse_search":
                if ch in (curses.KEY_BACKSPACE, 127, 8):
                    prompt["buf"] = prompt["buf"][:-1]
                elif ch in (ord('\n'), ord('\r'), curses.KEY_ENTER):
                    with state.lock:
                        state.browse_search = prompt["buf"].strip()
                    threading.Thread(
                        target=state.refresh_browse, daemon=True).start()
                    prompt = _fresh_prompt()
                elif 32 <= ch <= 126:
                    prompt["buf"] += chr(ch)
                continue

            if p_mode == "browse_snipe":
                if ch in (curses.KEY_BACKSPACE, 127, 8):
                    prompt["buf"]   = prompt["buf"][:-1]
                    prompt["error"] = ""
                elif ch in (ord('\n'), ord('\r'), curses.KEY_ENTER):
                    fields = PROMPT_FIELDS["browse_snipe"]
                    step   = prompt["step"]
                    _fkey, _label, default = fields[step]
                    value  = prompt["buf"].strip() or default
                    if not value:
                        prompt["error"] = "Required"
                        continue
                    if _fkey == "amount":
                        try:
                            float(value)
                        except ValueError:
                            prompt["error"] = "Must be a number"
                            continue
                    elif _fkey == "seconds":
                        try:
                            int(value)
                        except ValueError:
                            prompt["error"] = "Must be a whole number"
                            continue
                    prompt["data"][_fkey] = value
                    prompt["buf"]         = ""
                    prompt["error"]       = ""
                    if step + 1 < len(fields):
                        prompt["step"] += 1
                    else:
                        err = execute_prompt(state, "browse_snipe", prompt["data"])
                        if err:
                            state.add_log(f"❌ Snipe: {err}")
                        else:
                            state.add_log("✅ Auction added to monitor")
                        prompt = _fresh_prompt()
                elif 32 <= ch <= 126:
                    prompt["buf"]   += chr(ch)
                    prompt["error"]  = ""
                continue

            if p_mode == "browse_price":
                if ch in (curses.KEY_BACKSPACE, 127, 8):
                    prompt["buf"]   = prompt["buf"][:-1]
                    prompt["error"] = ""
                elif ch in (ord('\n'), ord('\r'), curses.KEY_ENTER):
                    raw  = prompt["buf"].strip()
                    step = prompt["step"]
                    val  = None
                    if raw:
                        try:
                            val = float(raw)
                            if val < 0:
                                raise ValueError
                        except ValueError:
                            prompt["error"] = "Enter a positive number or leave blank"
                            continue
                    if step == 0:
                        prompt["data"]["price_min"] = val
                        prompt["step"]  = 1
                        prompt["buf"]   = ""
                        prompt["error"] = ""
                    else:
                        price_min = prompt["data"].get("price_min")
                        price_max = val
                        with state.lock:
                            state.browse_price_min = price_min
                            state.browse_price_max = price_max
                        lo = f"${price_min:.0f}" if price_min else "any"
                        hi = f"${price_max:.0f}" if price_max else "any"
                        state.add_log(f"💲 Price: {lo}–{hi}")
                        threading.Thread(
                            target=state.refresh_browse, daemon=True).start()
                        prompt = _fresh_prompt()
                elif 32 <= ch <= 126:
                    prompt["buf"]   += chr(ch)
                    prompt["error"]  = ""
                continue

            if p_mode == "browse_detail":
                it = prompt["data"].get("item", {})
                if ch == 27:
                    prompt = _fresh_prompt()
                elif ch == curses.KEY_UP:
                    prompt["data"]["detail_scroll"] = max(
                        0, prompt["data"].get("detail_scroll", 0) - 1)
                elif ch == curses.KEY_DOWN:
                    prompt["data"]["detail_scroll"] = (
                        prompt["data"].get("detail_scroll", 0) + 1)
                else:
                    key = chr(ch).lower() if 32 <= ch <= 126 else ""
                    if key == 'o':
                        url = _auction_url(it)
                        if url:
                            webbrowser.open(url)
                            state.add_log(f"🌐 Opened: {url[-60:]}")
                    elif key == 'a':
                        title = (it.get("item") or {}).get("title") or ""
                        if title:
                            amz = f"https://www.amazon.com/s?k={quote_plus(title)}"
                            webbrowser.open(amz)
                            state.add_log(f"🛒 Amazon: {title[:50]}")
                    elif key == 'b':
                        si  = it.get("item") or {}
                        tit = si.get("title") or "?"
                        url = _auction_url(it)
                        if url:
                            prompt = _fresh_prompt()
                            prompt["mode"]         = "browse_snipe"
                            prompt["data"]["_url"] = url
                            state.add_log(f"⚡ Sniping: {tit[:50]}")
                continue

            # No active prompt — browse navigation
            key = chr(ch).lower() if 32 <= ch <= 126 else ""

            if key == 'q':
                return

            elif ch == curses.KEY_UP:
                with state.lock:
                    state.browse_cursor = max(0, state.browse_cursor - 1)

            elif ch == curses.KEY_DOWN:
                with state.lock:
                    n = len(state.browse_items)
                    state.browse_cursor = min(max(0, n - 1),
                                              state.browse_cursor + 1)

            elif ch in (ord('\n'), ord('\r'), curses.KEY_ENTER):
                with state.lock:
                    items   = state.browse_items
                    cursor  = state.browse_cursor
                    cust_id = state.customer_id
                if 0 <= cursor < len(items):
                    it_sel     = items[cursor]
                    auction_id = it_sel.get("id", "")
                    prompt = _fresh_prompt()
                    prompt["mode"]                       = "browse_detail"
                    prompt["data"]["item"]               = it_sel
                    prompt["data"]["detail_scroll"]      = 0
                    prompt["data"]["_detail_auction_id"] = auction_id
                    prompt["data"]["_detail_status"]     = "loading" if auction_id else ""
                    prompt["data"]["_detail_data"]       = None
                    prompt["data"]["_customer_id"]       = cust_id
                    if auction_id:
                        threading.Thread(
                            target=state.fetch_auction_detail,
                            args=(auction_id,), daemon=True).start()

            elif key == 'o':
                with state.lock:
                    items  = state.browse_items
                    cursor = state.browse_cursor
                if 0 <= cursor < len(items):
                    url = _auction_url(items[cursor])
                    if url:
                        webbrowser.open(url)
                        state.add_log(f"🌐 Opened: {url[-60:]}")

            elif key == 'a':
                with state.lock:
                    items  = state.browse_items
                    cursor = state.browse_cursor
                if 0 <= cursor < len(items):
                    title = (items[cursor].get("item") or {}).get("title") or ""
                    if title:
                        amz = f"https://www.amazon.com/s?k={quote_plus(title)}"
                        webbrowser.open(amz)
                        state.add_log(f"🛒 Amazon search: {title[:50]}")

            elif key == 'b':
                with state.lock:
                    items  = state.browse_items
                    cursor = state.browse_cursor
                if 0 <= cursor < len(items):
                    it  = items[cursor]
                    tit = (it.get("item") or {}).get("title") or "?"
                    url = _auction_url(it)
                    if url:
                        prompt = _fresh_prompt()
                        prompt["mode"]         = "browse_snipe"
                        prompt["data"]["_url"] = url
                        state.add_log(f"⚡ Sniping: {tit[:50]}")

            elif key == '/':
                prompt = _fresh_prompt()
                prompt["mode"] = "browse_search"

            elif key == 's':
                with state.lock:
                    cur_sort = state.browse_sort
                idx = (BROWSE_SORTS.index(cur_sort)
                       if cur_sort in BROWSE_SORTS else 0)
                new_sort = BROWSE_SORTS[(idx + 1) % len(BROWSE_SORTS)]
                with state.lock:
                    state.browse_sort = new_sort
                threading.Thread(
                    target=state.refresh_browse, daemon=True).start()
                state.add_log(f"🔃 Sort: {BROWSE_SORT_LABELS[new_sort]}")

            elif key == 'l':
                with state.lock:
                    locs   = list(state.browse_locations)
                    cur_id = state.browse_location_id
                if locs:
                    loc_ids = [""] + [
                        l.get("id") or l.get("storeLocationId") for l in locs]
                    try:
                        idx = loc_ids.index(cur_id)
                    except ValueError:
                        idx = 0
                    new_id = loc_ids[(idx + 1) % len(loc_ids)]
                    with state.lock:
                        state.browse_location_id = new_id
                    threading.Thread(
                        target=state.refresh_browse, daemon=True).start()
                    if new_id:
                        loc_name = next(
                            (l.get("name") or l.get("city", new_id)
                             for l in locs
                             if (l.get("id") or l.get("storeLocationId")) == new_id),
                            new_id)
                        state.add_log(f"📍 Location: {loc_name}")
                    else:
                        state.add_log("📍 Location: All")

            elif key == 'c':
                with state.lock:
                    cur_conds = list(state.browse_conditions)
                cycle = list(COND_CYCLE)
                cur_val = cur_conds[0] if len(cur_conds) == 1 else ""
                cycle_vals = [v for v, _ in cycle]
                try:
                    idx = cycle_vals.index(cur_val)
                except ValueError:
                    idx = 0
                nv, nl = cycle[(idx + 1) % len(cycle)]
                with state.lock:
                    state.browse_conditions = [nv] if nv else []
                threading.Thread(
                    target=state.refresh_browse, daemon=True).start()
                state.add_log(f"🏷  Condition: {nl}")

            elif key == 'p':
                prompt = _fresh_prompt()
                prompt["mode"] = "browse_price"
                prompt["data"] = {"price_min": None}

            elif key in ('1','2','3','4','5','6','7'):
                qf_idx = int(key) - 1
                if 0 <= qf_idx < len(QUICK_FILTERS):
                    qf_val, qf_lbl = QUICK_FILTERS[qf_idx]
                    with state.lock:
                        qf = list(state.browse_quick_filters)
                    if qf_val in qf:
                        qf.remove(qf_val)
                        state.add_log(f"☐ Filter off: {qf_lbl}")
                    else:
                        qf.append(qf_val)
                        state.add_log(f"☑ Filter on:  {qf_lbl}")
                    with state.lock:
                        state.browse_quick_filters = qf
                    threading.Thread(
                        target=state.refresh_browse, daemon=True).start()

            elif key == 'r':
                with state.lock:
                    state.browse_items = []
                    state.browse_page  = 1
                threading.Thread(
                    target=state.refresh_browse, daemon=True).start()
                state.add_log("🔄 Refreshing browse…")

            continue

        # ── Cart view ────────────────────────────────────────────────────
        if current_view == VIEW_CART and not prompt["mode"]:
            key = chr(ch).lower() if 32 <= ch <= 126 else ""
            if key == 'q':
                return
            if key == 'p':
                with state.lock:
                    has_checkout = bool(state.cart_checkout)
                if not has_checkout:
                    state.add_log("⚠  Cart is empty — nothing to pay")
                else:
                    prompt["mode"] = "pay"
            elif key == 's':
                prompt["mode"] = "sched"
            elif key == 'c':
                with state.lock:
                    cd = state.cart_data
                has_appt = False
                if cd:
                    for v in (cd.get("visits") or []):
                        if (not v.get("cancelledAt")
                                and v.get("status") != "Cancelled"):
                            has_appt = True
                            break
                if not has_appt:
                    state.add_log("⚠  No active appointment to cancel")
                else:
                    prompt["mode"] = "cancel_apt"
            elif key == 'd':
                with state.lock:
                    has_items = bool(state.cart_checkout)
                if not has_items:
                    state.add_log("⚠  Cart is empty — nothing to remove")
                else:
                    prompt["mode"] = "rm_cart"
            elif key == 'r':
                threading.Thread(
                    target=state.refresh_cart, daemon=True).start()
                state.add_log("🔄 Refreshing cart…")
            continue

        # ── Monitor view: hotkeys ────────────────────────────────────────
        if not prompt["mode"]:
            key = chr(ch).lower() if 32 <= ch <= 126 else ""
            if key == 'q':
                return
            if key in ('a', 'r', 'b', 's'):
                mode_map = {'a': 'add', 'r': 'rm', 'b': 'bid', 's': 'snipe'}
                prompt["mode"] = mode_map[key]
            continue

        # ── Active prompt: text input ────────────────────────────────────
        if ch in (curses.KEY_BACKSPACE, 127, 8):
            prompt["buf"]   = prompt["buf"][:-1]
            prompt["error"] = ""

        elif ch in (ord('\n'), ord('\r'), curses.KEY_ENTER):
            fields               = PROMPT_FIELDS[prompt["mode"]]
            step                 = prompt["step"]
            fkey, _label, default = fields[step]
            value = prompt["buf"].strip() or default
            if not value:
                prompt["error"] = "Required"
                continue

            if fkey == "amount":
                try:
                    float(value)
                except ValueError:
                    prompt["error"] = "Must be a number (e.g. 12.50)"
                    continue
            elif fkey in ("id", "seconds", "slot"):
                if fkey == "seconds" or fkey == "slot":
                    try:
                        int(value)
                    except ValueError:
                        prompt["error"] = "Must be a whole number"
                        continue
            elif fkey == "day":
                try:
                    datetime.strptime(value, "%Y-%m-%d")
                except ValueError:
                    prompt["error"] = "Use format YYYY-MM-DD"
                    continue
                # Fetch available slots from server
                try:
                    raw_slots = state.client.get_open_slots(
                        state.active_login_id,
                        state.browse_location_id, value)
                    avail = [s for s in raw_slots if s.get("isAvailable")]
                    if not avail:
                        prompt["error"] = f"No available slots on {value}"
                        continue
                    state._avail_slots = avail
                except Exception as ex:
                    prompt["error"] = f"Failed to load slots: {ex}"
                    continue

            prompt["data"][fkey] = value
            prompt["buf"]        = ""
            prompt["error"]      = ""

            if step + 1 < len(fields):
                prompt["step"] += 1
            else:
                err = execute_prompt(state, prompt["mode"], prompt["data"])
                if err:
                    state.add_log(
                        f"❌ {PROMPT_TITLES[prompt['mode']]}: {err}")
                prompt = _fresh_prompt()

        elif 32 <= ch <= 126:
            prompt["buf"]   += chr(ch)
            prompt["error"]  = ""


# ── Settings key handler ─────────────────────────────────────────────────────

def _handle_settings(ch: int, state: ClientState, st: dict) -> None:
    cursor = st["cursor"]
    edit   = st["edit"]
    buf    = st["buf"]

    if edit:
        defn = SETTINGS_DEFS[cursor]
        kind = defn["kind"]

        if kind == "bool":
            if ch == 27:
                st["edit"] = False
                st["buf"]  = ""
            else:
                val = _get_nested(state.user_config, defn["path"])
                _set_nested(state.user_config, defn["path"], not bool(val))
                st["edit"] = False
                st["buf"]  = ""
                st["msg"]  = "Changed — press [S] to save"
        else:
            if ch == 27:
                st["edit"] = False
                st["buf"]  = ""
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                st["buf"] = buf[:-1]
            elif ch in (ord('\n'), ord('\r'), curses.KEY_ENTER):
                raw = buf.strip()
                if kind == "int":
                    try:
                        val = int(raw) if raw else None
                    except ValueError:
                        st["msg"] = "⚠  Must be a whole number"
                        return
                else:
                    val = raw or None
                _set_nested(state.user_config, defn["path"], val)
                st["edit"] = False
                st["buf"]  = ""
                st["msg"]  = "Changed — press [S] to save"
            elif 32 <= ch <= 126:
                st["buf"] = buf + chr(ch)
        return

    key = chr(ch).lower() if 32 <= ch <= 126 else ""

    if ch == curses.KEY_UP:
        settings_move(st, -1)
        st["msg"] = ""
    elif ch == curses.KEY_DOWN:
        settings_move(st, +1)
        st["msg"] = ""
    elif ch in (ord('\n'), ord('\r'), curses.KEY_ENTER, ord(' ')):
        defn = SETTINGS_DEFS[cursor]
        kind = defn["kind"]
        st["msg"] = ""
        if kind == "bool":
            val = _get_nested(state.user_config, defn["path"])
            _set_nested(state.user_config, defn["path"], not bool(val))
            st["msg"] = "Changed — press [S] to save"
        else:
            val = _get_nested(state.user_config, defn["path"])
            st["buf"]  = str(val) if val is not None else ""
            st["edit"] = True
    elif key == 's':
        try:
            state.client.update_settings(state.user_config)
            st["msg"] = "✅  Saved to server"
        except Exception:
            st["msg"] = "⚠  Save failed"
    elif key == 'q':
        pass
