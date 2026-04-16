"""
cli/bwsniper/tui/monitor.py — Monitor tab and fireworks overlay.

Adapted for the thin client: reads snipe dicts from server instead of
AuctionEntry objects.
"""

import math
import random
import curses
from datetime import datetime, timezone

from ..state import ClientState
from .common import (
    CP_HEADER, CP_WON, CP_LOST, CP_LEADING, CP_SNIPED, CP_DIM, CP_ERROR,
    PROMPT_FIELDS, PROMPT_TITLES,
    _safe, _hline, _snipe_header_str, fmt_time, parse_dt,
)

FIREWORKS_DURATION = 6.0

_BURSTS = [
    (0.15, 0.25, 0.0,  CP_WON),
    (0.82, 0.22, 0.5,  CP_SNIPED),
    (0.50, 0.14, 0.9,  CP_LEADING),
    (0.30, 0.30, 1.4,  CP_WON),
    (0.72, 0.20, 1.7,  CP_SNIPED),
    (0.10, 0.18, 2.3,  CP_LEADING),
    (0.88, 0.26, 2.7,  CP_WON),
    (0.45, 0.13, 3.2,  CP_SNIPED),
    (0.62, 0.22, 3.6,  CP_LEADING),
    (0.25, 0.17, 4.1,  CP_WON),
    (0.77, 0.28, 4.5,  CP_SNIPED),
]


def draw_fireworks(stdscr, title: str, price: float, elapsed: float):
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()

    rocket_dur = 0.45
    burst_life = 2.2

    for x_frac, y_frac, launch_t, cpair in _BURSTS:
        cx      = int(x_frac * max_x)
        burst_y = max(2, int(y_frac * max_y))
        t_since = elapsed - launch_t

        if t_since < 0:
            continue

        if t_since < rocket_dur:
            frac     = t_since / rocket_dur
            rocket_y = (max_y - 2) - int(frac * ((max_y - 2) - burst_y))
            try:
                stdscr.addstr(rocket_y, cx, '|',
                              curses.color_pair(cpair) | curses.A_BOLD)
                if rocket_y + 1 < max_y:
                    stdscr.addstr(rocket_y + 1, cx, '.',
                                  curses.color_pair(cpair))
            except curses.error:
                pass
        else:
            t = t_since - rocket_dur
            if t > burst_life:
                continue
            rng = random.Random(
                int(x_frac * 997 + y_frac * 991 + launch_t * 983))
            for i in range(28):
                angle = 2 * math.pi * i / 28 + rng.uniform(-0.12, 0.12)
                speed = rng.uniform(0.9, 2.6)
                px = cx      + int(speed * t * math.cos(angle) * 3.2)
                py = burst_y + int(speed * t * math.sin(angle) + 0.9 * t * t)
                alpha = 1.0 - t / burst_life
                if (alpha <= 0
                        or not (0 <= py < max_y - 1 and 0 <= px < max_x - 1)):
                    continue
                if alpha > 0.65:
                    char, attr = '*', curses.A_BOLD
                elif alpha > 0.35:
                    char, attr = '+', curses.A_NORMAL
                else:
                    char, attr = '.', curses.A_DIM
                try:
                    stdscr.addstr(py, px, char,
                                  curses.color_pair(cpair) | attr)
                except curses.error:
                    pass

            if t < 0.18:
                for dy, dx in [(-1,0),(1,0),(0,-2),(0,2),
                                (-1,-2),(1,2),(-1,2),(1,-2)]:
                    try:
                        stdscr.addstr(burst_y + dy, cx + dx, '*',
                                      curses.color_pair(cpair) | curses.A_BOLD)
                    except curses.error:
                        pass

    flash   = (int(elapsed * 4) % 2 == 0)
    title_s = title[:min(max_x - 8, 56)]
    cy      = max_y // 2
    cx      = max_x // 2
    box_w   = max(len(title_s), 26) + 6

    msg_lines = [
        ("  🎉  YOU WON!  🎉  ",
         curses.color_pair(CP_WON if flash else CP_SNIPED) | curses.A_BOLD),
        ("", curses.A_NORMAL),
        (title_s, curses.A_BOLD),
        (f"  Final price: ${price:.2f}  ",
         curses.color_pair(CP_WON) | curses.A_BOLD),
        ("", curses.A_NORMAL),
        ("  Press any key to continue  ", curses.color_pair(CP_DIM)),
    ]

    start_y = cy - len(msg_lines) // 2
    for i in range(len(msg_lines) + 2):
        row_y = start_y - 1 + i
        if 0 <= row_y < max_y:
            bx = max(0, cx - box_w // 2)
            try:
                stdscr.addstr(row_y, bx, ' ' * min(box_w, max_x - bx))
            except curses.error:
                pass

    for i, (line, attr) in enumerate(msg_lines):
        if not line:
            continue
        x = max(0, cx - len(line) // 2)
        y = start_y + i
        if 0 <= y < max_y:
            try:
                stdscr.addstr(y, x, line[:max_x - x - 1], attr)
            except curses.error:
                pass

    stdscr.refresh()


# ── Monitor tab ──────────────────────────────────────────────────────────────

_UP_COL  = (f"  {'ID':<10}  {'Item':<38}  {'High Bid':>8}  {'My Bid':>7}"
            f"  {'Status':<14}  {'Left':>9}")
_PAST_COL = (f"  {'Item':<38}  {'My Bid':>7}  {'Final':>7}"
             f"  {'Result':<8}  {'Ended'}")


def _snipe_row(snipe: dict, now) -> tuple:
    """Return (line_str, attr) for a live snipe dict."""
    title_s = (snipe.get("title") or snipe.get("url", "?"))[:38]
    high_s  = f"${snipe.get('current_bid', 0):.2f}" if snipe.get("current_bid") else "—"
    mybid_s = f"${snipe.get('bid_amount', 0):.2f}"
    snipe_id = str(snipe.get("id", ""))[:10]

    et = snipe.get("end_time") or snipe.get("endDate") or ""
    left_s = "—"
    if et:
        try:
            end = parse_dt(et)
            secs = (end - now).total_seconds()
            left_s = fmt_time(secs) if secs > 0 else "Ended"
        except Exception:
            pass

    st    = snipe.get("status", "Loading")
    is_me = snipe.get("is_me", False)

    if st == "Watching":
        if is_me:
            icon, st_s, attr = "🏆", "Leading",     curses.color_pair(CP_LEADING)
        elif snipe.get("winner"):
            icon, st_s, attr = "🔴", f"@{snipe['winner'][:11]}", curses.A_NORMAL
        else:
            icon, st_s, attr = "⚪", "No bids yet", curses.color_pair(CP_DIM)
    elif st == "Loading":
        icon, st_s, attr = "⏳", "Loading…",  curses.color_pair(CP_DIM)
    elif st == "Sniped":
        icon, st_s, attr = "🚀", "Sniped!",   curses.color_pair(CP_SNIPED) | curses.A_BOLD
    elif st == "Won":
        icon, st_s, attr = "🎉", "WON!",      curses.color_pair(CP_WON)   | curses.A_BOLD
    elif st == "Lost":
        icon, st_s, attr = "😞", "Lost",      curses.color_pair(CP_LOST)
    elif st == "Ended":
        icon, st_s, attr = "⏰", "Ended",     curses.color_pair(CP_DIM)
    elif st == "Error":
        icon, st_s, attr = "❌", (snipe.get("error_msg") or "Error")[:13], curses.color_pair(CP_ERROR)
    else:
        icon, st_s, attr = "·", st, curses.A_NORMAL

    line = (f"  {snipe_id:<10}  {title_s:<38}  {high_s:>8}"
            f"  {mybid_s:>7}  {icon} {st_s:<12}  {left_s:>9}")
    return line, attr


def _past_row(rec: dict) -> tuple:
    """Return (line_str, attr) for a past-snipe record dict."""
    title_s  = (rec.get("title") or "?")[:38]
    mybid_s  = f"${rec.get('bid_amount', 0):.2f}"
    final    = rec.get("final_price") or rec.get("current_bid")
    final_s  = f"${final:.2f}" if final else "—"
    status   = rec.get("status", "?")
    ended_raw = rec.get("ended_at") or rec.get("updated_at") or ""
    ended_s  = ""
    try:
        d = parse_dt(ended_raw).astimezone()
        bh = d.hour % 12 or 12
        ended_s = f"{d.strftime('%m/%d')} {bh}:{d.strftime('%M %p')}"
    except Exception:
        ended_s = ended_raw[:16]

    if status == "Won":
        result_s, attr = "✅ Won",   curses.color_pair(CP_WON)
    elif status == "Lost":
        result_s, attr = "😞 Lost",  curses.color_pair(CP_LOST)
    elif status == "Error":
        result_s, attr = "❌ Error", curses.color_pair(CP_ERROR)
    else:
        result_s, attr = f"⏰ {status}", curses.color_pair(CP_DIM)

    line = (f"  {title_s:<38}  {mybid_s:>7}  {final_s:>7}"
            f"  {result_s:<8}  {ended_s}")
    return line, attr


def draw_ui(stdscr, state: ClientState, prompt: dict):
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()
    row = 0

    now_str    = datetime.now().strftime("%a %b %d %Y  %I:%M:%S %p")
    tab_hint   = "[Tab] next"
    snipe_info = _snipe_header_str(state)
    acct       = state.active_login_name or state.user_display
    header     = (f"  BuyWander Sniper  │  {acct}"
                  f"  │  Snipe Monitor  │  {now_str}{snipe_info}")
    hpad = (header.ljust(max_x - len(tab_hint) - 2)
            [:max_x - len(tab_hint) - 2])
    _safe(stdscr, row, 0, (hpad + tab_hint + " ").ljust(max_x - 1),
          curses.color_pair(CP_HEADER) | curses.A_BOLD)
    row += 1
    _hline(stdscr, row); row += 1

    with state.lock:
        snipes     = list(state.snipes)
        past_snipes = list(state.past_snipes)

    now = datetime.now(timezone.utc)
    FOOTER_ROWS = 3

    # Upcoming
    _safe(stdscr, row, 0,
          f"  ▶ Upcoming Snipes  ({len(snipes)} active)",
          curses.A_BOLD | curses.color_pair(CP_SNIPED))
    row += 1
    if row < max_y - FOOTER_ROWS:
        _safe(stdscr, row, 0, _UP_COL[:max_x - 1],
              curses.A_UNDERLINE | curses.A_DIM)
        row += 1

    if snipes:
        for snipe in snipes:
            if row >= max_y - FOOTER_ROWS:
                break
            line, attr = _snipe_row(snipe, now)
            _safe(stdscr, row, 0, line[:max_x - 1], attr)
            row += 1
    else:
        _safe(stdscr, row, 0,
              "  (none — press [A] to add an auction URL)",
              curses.color_pair(CP_DIM))
        row += 1

    # Past Snipes
    if row < max_y - FOOTER_ROWS - 1:
        row += 1
    if row < max_y - FOOTER_ROWS:
        _safe(stdscr, row, 0,
              f"  ▶ Past Snipes  ({len(past_snipes)} total)",
              curses.A_BOLD | curses.color_pair(CP_DIM))
        row += 1
    if row < max_y - FOOTER_ROWS:
        _safe(stdscr, row, 0, _PAST_COL[:max_x - 1],
              curses.A_UNDERLINE | curses.A_DIM)
        row += 1

    for rec in reversed(past_snipes):
        if row >= max_y - FOOTER_ROWS:
            break
        line, attr = _past_row(rec)
        _safe(stdscr, row, 0, line[:max_x - 1], attr)
        row += 1

    if not past_snipes:
        if row < max_y - FOOTER_ROWS:
            _safe(stdscr, row, 0, "  (no completed snipes yet)",
                  curses.color_pair(CP_DIM))
            row += 1

    # Command bar
    cmd_row = max_y - FOOTER_ROWS
    _hline(stdscr, cmd_row)

    mode = prompt["mode"]
    if mode:
        fields = PROMPT_FIELDS[mode]
        step = prompt["step"]
        total_f = len(fields)
        _key, label, default = fields[step]
        p_title = PROMPT_TITLES[mode]
        hint_line = (f"  {p_title}  —  step {step + 1}/{total_f}"
                     f"   ↵ next  ·  Esc cancel")
        if prompt["error"]:
            hint_line += f"   ⚠ {prompt['error']}"
            _safe(stdscr, cmd_row + 1, 0, hint_line, curses.color_pair(CP_ERROR))
        else:
            _safe(stdscr, cmd_row + 1, 0, hint_line, curses.color_pair(CP_DIM))
        dflt_hint = f" [{default}]" if default else ""
        prefix = f"  {label}{dflt_hint}:  "
    else:
        hotkeys = ("  [A] Add  [R] Remove  [B] Change Bid  "
                   "[S] Snipe Timing  [Tab] next  [Q] Quit")
        _safe(stdscr, cmd_row + 1, 0, hotkeys, curses.color_pair(CP_DIM))
        prefix = "  "

    buf     = prompt["buf"]
    avail_w = max(1, max_x - len(prefix) - 1)
    visible = buf[-avail_w:] if len(buf) > avail_w else buf
    cursor_x = len(prefix) + len(visible)
    _safe(stdscr, cmd_row + 2, 0, prefix + visible)
    try:
        stdscr.move(cmd_row + 2, min(cursor_x, max_x - 1))
    except curses.error:
        pass

    stdscr.refresh()
