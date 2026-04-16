"""
cli/bwsniper/tui/history.py — History tab for the thin client.
"""

import curses
from datetime import datetime

from ..state import ClientState
from .common import (
    CP_HEADER, CP_WON, CP_DIM, CP_ERROR, CP_SNIPED,
    _safe, _hline, _snipe_header_str,
)


def draw_history_search_bar(stdscr, max_y, max_x,
                             search_active: bool,
                             search_buf: str,
                             total: int,
                             shown: int) -> None:
    _hline(stdscr, max_y - 3)

    if search_active:
        label  = "  Search: "
        avail  = max(1, max_x - len(label) - 1)
        vis    = search_buf[-avail:] if len(search_buf) > avail else search_buf
        _safe(stdscr, max_y - 2, 0,
              "  Type to filter, ↵/Esc to commit  │  [Q] Quit",
              curses.color_pair(CP_DIM))
        _safe(stdscr, max_y - 1, 0, label + vis,
              curses.color_pair(CP_SNIPED) | curses.A_BOLD)
        try:
            stdscr.move(max_y - 1,
                        min(len(label) + len(vis), max_x - 1))
        except curses.error:
            pass
    else:
        count_s = f"{shown} shown" if shown != total else f"{total} total"
        if search_buf:
            filter_s = f"  Filtering: \"{search_buf}\"   {count_s}"
            filter_a = curses.color_pair(CP_SNIPED) | curses.A_BOLD
        else:
            filter_s = f"  {total} won auction{'s' if total != 1 else ''}   │   {count_s}"
            filter_a = curses.color_pair(CP_DIM)
        _safe(stdscr, max_y - 2, 0,
              (filter_s +
               "   │   ↑↓ scroll   │   [/] Search   │   [Esc] Clear   │   [Tab] back")
              [:max_x - 1],
              filter_a)
        try:
            stdscr.move(max_y - 1, 0)
        except curses.error:
            pass


def draw_history(stdscr, state: ClientState, scroll: int,
                 search_active: bool = False,
                 search_buf: str = "") -> int:
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()
    row = 0

    now_str    = datetime.now().strftime("%a %b %d %Y  %I:%M:%S %p")
    snipe_info = _snipe_header_str(state)
    acct       = state.active_login_name or state.user_display
    header     = (f"  BuyWander Sniper  │  {acct}"
                  f"  │  Auction History  │  {now_str}{snipe_info}")
    _safe(stdscr, row, 0, header.ljust(max_x - 1),
          curses.color_pair(CP_HEADER) | curses.A_BOLD)
    row += 1
    _hline(stdscr, row); row += 1

    col_hdr = (f"  {'Date Won':<20}  {'Item':<46}"
               f"  {'Final':>8}  {'My Bid':>8}")
    _safe(stdscr, row, 0, col_hdr[:max_x - 1],
          curses.A_BOLD | curses.A_UNDERLINE)
    row += 1

    with state.lock:
        records = list(state.history)
        search  = state.history_search

    total = len(records)

    active_term = search_buf if search_active else search
    if active_term:
        sq = active_term.lower()
        records = [r for r in records
                   if sq in (r.get("title") or "").lower()
                   or sq in (r.get("url") or "").lower()]

    shown       = len(records)
    FOOTER_ROWS = 3
    visible_rows = max(1, max_y - row - FOOTER_ROWS)
    scroll       = max(0, min(scroll, max(0, shown - visible_rows)))

    if not records:
        if active_term:
            _safe(stdscr, row, 0,
                  f"  No results for \"{active_term}\".",
                  curses.color_pair(CP_DIM))
        else:
            _safe(stdscr, row, 0,
                  "  No won auctions found.",
                  curses.color_pair(CP_DIM))
        row += 1
    else:
        for rec in records[scroll: scroll + visible_rows]:
            if row >= max_y - FOOTER_ROWS:
                break
            try:
                dt     = datetime.fromisoformat(rec["won_at"]).astimezone()
                date_s = dt.strftime("%b %d %Y  %I:%M %p")
            except Exception:
                date_s = rec.get("won_at", "")[:20]

            title_s = rec.get("title", rec.get("url", "?"))[:45]
            final_s = f"${rec.get('final_price', 0):.2f}"
            mybid_s = f"${rec.get('my_bid', 0):.2f}"
            line    = (f"  {date_s:<20}  {title_s:<46}"
                       f"  {final_s:>8}  {mybid_s:>8}")
            _safe(stdscr, row, 0, line[:max_x - 1], curses.color_pair(CP_WON))
            row += 1

        if shown > visible_rows:
            pct = int(100 * scroll / max(1, shown - visible_rows))
            _safe(stdscr, max_y - FOOTER_ROWS - 1, max_x - 10,
                  f"  {pct:>3}%  ", curses.color_pair(CP_DIM))

    draw_history_search_bar(stdscr, max_y, max_x,
                            search_active, search_buf,
                            total, shown)
    stdscr.refresh()
    return scroll
