"""
cli/bwsniper/tui/log.py — Event Log tab for the thin client.
"""

import curses
from datetime import datetime

from ..state import ClientState
from .common import (
    CP_HEADER, CP_WON, CP_SNIPED, CP_DIM, CP_ERROR,
    _safe, _hline, _snipe_header_str,
)


def draw_log(stdscr, state: ClientState, scroll: int) -> int:
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()
    row = 0

    now_str    = datetime.now().strftime("%a %b %d %Y  %I:%M:%S %p")
    tab_hint   = "[Tab] next"
    snipe_info = _snipe_header_str(state)
    acct       = state.active_login_name or state.user_display
    header     = (f"  BuyWander Sniper  │  {acct}"
                  f"  │  Event Log  │  {now_str}{snipe_info}")
    hpad = (header.ljust(max_x - len(tab_hint) - 2)
            [:max_x - len(tab_hint) - 2])
    _safe(stdscr, row, 0, (hpad + tab_hint + " ").ljust(max_x - 1),
          curses.color_pair(CP_HEADER) | curses.A_BOLD)
    row += 1
    _hline(stdscr, row); row += 1

    with state.lock:
        log_lines = list(state.log)

    total = len(log_lines)
    avail = max(1, max_y - row - 2)

    max_scroll = max(0, total - avail)
    scroll     = max(0, min(scroll, max_scroll))

    start = max(0, total - avail - scroll)
    end   = total - scroll
    visible = log_lines[start:end]

    for i, ln in enumerate(visible):
        if "❌" in ln or "⚠" in ln:
            attr = curses.color_pair(CP_ERROR)
        elif "🎉" in ln or "✅" in ln or "Won" in ln:
            attr = curses.color_pair(CP_WON)
        elif "🚀" in ln or "Sniped" in ln:
            attr = curses.color_pair(CP_SNIPED)
        else:
            attr = 0
        _safe(stdscr, row + i, 0, f"  {ln}"[:max_x - 1], attr)

    for i in range(len(visible), avail):
        _safe(stdscr, row + i, 0, " " * (max_x - 1))

    _hline(stdscr, max_y - 2)
    count_s = f"{total} events" if total else "no events yet"
    pct_s   = ""
    if max_scroll > 0:
        pct = int(100 * scroll / max_scroll)
        pct_s = f"  ↕ {pct}%"
    hint = (f"  ↑↓ scroll   [Tab] next tab   [Q] quit"
            f"   {count_s}{pct_s}")
    _safe(stdscr, max_y - 1, 0, hint[:max_x - 1], curses.color_pair(CP_DIM))

    try:
        stdscr.move(max_y - 1, 0)
    except curses.error:
        pass
    stdscr.refresh()
    return scroll
