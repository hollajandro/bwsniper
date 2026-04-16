"""
cli/bwsniper/tui/cart.py — Cart & Pickup tab for the thin client.
"""

import curses
from datetime import datetime

from ..state import ClientState
from .common import (
    CP_HEADER, CP_WON, CP_LEADING, CP_SNIPED, CP_DIM, CP_ERROR,
    PROMPT_FIELDS, PROMPT_TITLES,
    _safe, _hline, _snipe_header_str,
)


def draw_cart(stdscr, state: ClientState, prompt: dict) -> None:
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()
    row = 0

    now_str    = datetime.now().strftime("%a %b %d %Y  %I:%M:%S %p")
    tab_hint   = "[Tab] Monitor/History"
    snipe_info = _snipe_header_str(state)
    acct       = state.active_login_name or state.user_display
    header     = (f"  BuyWander Sniper  │  {acct}"
                  f"  │  Cart & Pickup  │  {now_str}{snipe_info}")
    header_padded = (header.ljust(max_x - len(tab_hint) - 2)
                     [:max_x - len(tab_hint) - 2])
    full_header = header_padded + tab_hint + " "
    _safe(stdscr, row, 0, full_header.ljust(max_x - 1),
          curses.color_pair(CP_HEADER) | curses.A_BOLD)
    row += 1
    _hline(stdscr, row); row += 1

    with state.lock:
        loading   = state.cart_loading
        cart_data = state.cart_data
        checkout  = list(state.cart_checkout)
        methods   = list(state.cart_methods)

    if loading and not cart_data:
        _safe(stdscr, row, 0, "  ⏳  Loading cart & pickup info…",
              curses.color_pair(CP_DIM))
        try:
            stdscr.move(max_y - 1, 0)
        except curses.error:
            pass
        stdscr.refresh()
        return

    paid_items = (cart_data.get("paidItems") or []) if cart_data else []
    visits     = (cart_data.get("visits")    or []) if cart_data else []
    cart_items = checkout if isinstance(checkout, list) else []
    total      = sum(
        float((a.get("winningBid") or {}).get("amount") or
              a.get("finalAmount") or 0)
        for a in cart_items
    )

    # PAID ITEMS
    _safe(stdscr, row, 0,
          f"  {'PAID ITEMS AWAITING PICKUP':<{max_x - 3}}",
          curses.A_BOLD | curses.A_UNDERLINE)
    row += 1

    if paid_items:
        col = f"  {'Item':<36}  {'SKU':<14}  {'Location':<18}  Paid"
        _safe(stdscr, row, 0, col, curses.A_DIM)
        row += 1
        for item in paid_items:
            if row >= max_y - 12:
                _safe(stdscr, row, 0,
                      f"  … ({len(paid_items)} total)",
                      curses.color_pair(CP_DIM))
                row += 1
                break
            title   = (item.get("title") or "Unknown")[:35]
            sku     = item.get("bwsku") or "—"
            loc_obj = item.get("currentLocation") or {}
            loc     = loc_obj.get("description") or "—"
            paid_at = ""
            if item.get("paidAt"):
                try:
                    paid_at = datetime.fromisoformat(
                        item["paidAt"].replace("Z", "+00:00")
                    ).astimezone().strftime("%b %d")
                except Exception:
                    pass
            line = f"  {title:<36}  {sku:<14}  {loc:<18}  {paid_at}"
            _safe(stdscr, row, 0, line, curses.color_pair(CP_LEADING))
            row += 1
    else:
        _safe(stdscr, row, 0, "  (no paid items awaiting pickup)",
              curses.color_pair(CP_DIM))
        row += 1

    row += 1

    # PENDING PAYMENT
    _safe(stdscr, row, 0,
          f"  {'CART — PENDING PAYMENT':<{max_x - 3}}",
          curses.A_BOLD | curses.A_UNDERLINE)
    row += 1

    if cart_items:
        col = (f"  {'#':<3}  {'Item':<33}  {'Winning Bid':>11}"
               f"  {'Est. Retail':>11}  Reserved Until")
        _safe(stdscr, row, 0, col, curses.A_DIM)
        row += 1
        for idx, ci in enumerate(cart_items):
            if row >= max_y - 10:
                _safe(stdscr, row, 0,
                      f"  … ({len(cart_items)} total)",
                      curses.color_pair(CP_DIM))
                row += 1
                break
            item_obj = ci.get("item") or {}
            title    = (item_obj.get("title") or "Unknown")[:32]
            wb       = ci.get("winningBid") or {}
            win_bid  = float(wb.get("amount") or ci.get("finalAmount") or 0)
            retail   = float(
                item_obj.get("retailPrice") or item_obj.get("retail") or 0)
            retail_s = f"${retail:.2f}" if retail else "—"
            reserved_s = ""
            end = ci.get("endDate") or ci.get("reservedUntil") or ""
            if end:
                try:
                    dt_r = datetime.fromisoformat(
                        end.replace("Z", "+00:00")).astimezone()
                    reserved_s = dt_r.strftime("%b %d %I:%M %p")
                except Exception:
                    reserved_s = end[:16]
            line = (f"  {idx + 1:<3}  {title:<33}  ${win_bid:>10.2f}"
                    f"  {retail_s:>11}  {reserved_s}")
            _safe(stdscr, row, 0, line, curses.color_pair(CP_SNIPED))
            row += 1
        pm_info = ""
        if methods:
            m       = methods[0]
            pm_info = f"  ·  {m.get('brand','').title()} ****{m.get('last4','')}"
        _safe(stdscr, row, 0,
              f"  Total: ${total:.2f}{pm_info}",
              curses.A_BOLD | curses.color_pair(CP_SNIPED))
        row += 1
    else:
        _safe(stdscr, row, 0, "  (cart is empty — nothing pending payment)",
              curses.color_pair(CP_DIM))
        row += 1

    row += 1

    # PICKUP APPOINTMENT
    _safe(stdscr, row, 0,
          f"  {'PICKUP APPOINTMENT':<{max_x - 3}}",
          curses.A_BOLD | curses.A_UNDERLINE)
    row += 1

    active_visit = None
    for v in visits:
        if not v.get("cancelledAt") and v.get("status") != "Cancelled":
            active_visit = v
            break

    if active_visit:
        try:
            dt = datetime.fromisoformat(
                active_visit["date"].replace("Z", "+00:00")).astimezone()
            date_s = dt.strftime("%A, %B %d %Y  at  %I:%M %p %Z")
        except Exception:
            date_s = active_visit.get("date", "")
        status_s = active_visit.get("status") or "Booked"
        _safe(stdscr, row, 0,
              f"  {status_s}  │  {date_s}",
              curses.color_pair(CP_WON) | curses.A_BOLD)
        row += 1
    else:
        _safe(stdscr, row, 0,
              "  No pickup appointment scheduled.",
              curses.color_pair(CP_DIM))
        row += 1

    # Available slots
    p_mode = prompt.get("mode", "")
    p_step = prompt.get("step", 0)
    avail_slots = getattr(state, '_avail_slots', [])
    if p_mode == "sched" and p_step == 1 and avail_slots:
        row += 1
        _safe(stdscr, row, 0, "  Available time slots:", curses.A_BOLD)
        row += 1
        for i, sl in enumerate(avail_slots[:12]):
            if row >= max_y - 5:
                break
            try:
                dt_sl = datetime.fromisoformat(
                    sl["date"].replace("Z", "+00:00")).astimezone()
                time_s = dt_sl.strftime("%I:%M %p %Z")
            except Exception:
                time_s = sl.get("date", "")
            _safe(stdscr, row, 0,
                  f"    [{i + 1}]  {time_s}",
                  curses.color_pair(
                      CP_LEADING if sl.get("isAvailable") else CP_DIM))
            row += 1

    # Footer
    cmd_row = max_y - 3
    _hline(stdscr, cmd_row)

    if p_mode in ("pay", "sched", "cancel_apt", "rm_cart"):
        fields = PROMPT_FIELDS[p_mode]
        step = p_step
        total_f = len(fields)
        _key, label, default = fields[step]

        if p_mode == "pay":
            if methods:
                m     = methods[0]
                brand = (m.get("brand") or "card").title()
                last4 = m.get("last4") or "????"
                label = f"Pay with {brand} ****{last4}? (y/n)"
            elif not cart_items:
                label = "Cart is empty — nothing to pay"

        title_p   = PROMPT_TITLES[p_mode]
        hint_line = (f"  {title_p}  —  step {step + 1}/{total_f}"
                     f"   ↵ confirm  ·  Esc cancel")
        if prompt.get("error"):
            hint_line += f"   ⚠ {prompt['error']}"
            _safe(stdscr, cmd_row + 1, 0, hint_line,
                  curses.color_pair(CP_ERROR))
        else:
            _safe(stdscr, cmd_row + 1, 0, hint_line,
                  curses.color_pair(CP_DIM))
        dflt_hint = f" [{default}]" if default else ""
        prefix = f"  {label}{dflt_hint}:  "
    else:
        parts = ["  [P] Pay cart"]
        if cart_items:
            parts.append("[D] Delete item")
        if active_visit:
            parts.append("[C] Cancel appointment")
        parts.append("[S] Schedule pickup")
        parts.append("[R] Refresh")
        parts.append("[Tab] Next view")
        parts.append("[Q] Quit")
        _safe(stdscr, cmd_row + 1, 0, "  ·  ".join(parts),
              curses.color_pair(CP_DIM))
        prefix = "  "

    buf   = prompt.get("buf", "")
    avail = max(1, max_x - len(prefix) - 1)
    if len(buf) > avail:
        visible  = buf[len(buf) - avail:]
        cursor_x = max_x - 2
    else:
        visible  = buf
        cursor_x = len(prefix) + len(buf)

    _safe(stdscr, cmd_row + 2, 0, prefix + visible)
    try:
        stdscr.move(cmd_row + 2, min(cursor_x, max_x - 1))
    except curses.error:
        pass

    stdscr.refresh()
