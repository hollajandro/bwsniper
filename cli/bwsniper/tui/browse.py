"""
cli/bwsniper/tui/browse.py — Browse Active Auctions tab for the thin client.
"""

import curses
from datetime import datetime, timezone

from ..config import (
    SITE_BASE, BROWSE_SORT_LABELS, QUICK_FILTERS, COND_MAP, COND_CYCLE,
)
from ..state import ClientState
from .common import (
    CP_HEADER, CP_WON, CP_SNIPED, CP_DIM, CP_ERROR,
    PROMPT_FIELDS,
    _safe, _hline, _snipe_header_str, parse_dt, fmt_time,
)

FOOTER_HEIGHT = 7


def _wrap(text: str, width: int) -> list:
    if not text:
        return []
    words = text.split()
    lines, cur = [], ""
    for word in words:
        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= width:
            cur += " " + word
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _auction_url(it: dict) -> str:
    auction_id = it.get("id") or ""
    hdl = it.get("handle") or (it.get("item") or {}).get("handle") or ""
    if auction_id:
        return f"https://www.buywander.com/auction/{auction_id}"
    if hdl:
        return f"https://www.buywander.com/auctions/{hdl}"
    return ""


def draw_browse_detail(stdscr, it: dict, detail_scroll: int = 0,
                       detail_status: str = "",
                       detail_data: dict = None,
                       customer_id: str = "") -> int:
    max_y, max_x = stdscr.getmaxyx()

    item_sub_base   = it.get("item") or {}
    item_sub_detail = (detail_data or {}).get("item") or {}
    def _pick(key):
        return item_sub_detail.get(key) or item_sub_base.get(key) or ""

    title       = _pick("title") or "?"
    description = (_pick("description") or _pick("longDescription")
                   or _pick("details"))
    _dd = detail_data or {}
    notes = (
        _pick("notes") or _pick("sellerNotes") or _pick("itemNotes")
        or _pick("auctionNotes")
        or it.get("notes") or it.get("sellerNotes") or it.get("itemNotes")
        or _dd.get("notes") or _dd.get("sellerNotes") or _dd.get("itemNotes")
        or _dd.get("auctionNotes") or ""
    )
    cond_raw = _pick("condition")
    cond     = COND_MAP.get(cond_raw, cond_raw) or "Unknown"
    retail   = float(_pick("price") or 0.0)
    brand    = _pick("brand") or _pick("manufacturer")
    model_num = _pick("modelNumber") or _pick("model")

    wb      = it.get("winningBid") or (detail_data or {}).get("winningBid") or {}
    bid_amt = wb.get("amount") or 0.0

    loc_sub  = it.get("storeLocation") or {}
    loc_city = loc_sub.get("city") or loc_sub.get("name") or "?"
    loc_st   = loc_sub.get("state") or ""
    location = f"{loc_city}, {loc_st}" if loc_st else loc_city

    ends = "?"
    ends_abs = ""
    end_dt = None
    try:
        now_utc = datetime.now(timezone.utc)
        end_dt  = parse_dt(it.get("endDate", ""))
        secs_left = (end_dt - now_utc).total_seconds()
        ends = fmt_time(secs_left) if secs_left > 0 else "ENDED"
    except Exception:
        pass
    if end_dt is not None:
        try:
            d = end_dt.astimezone()
            h = d.hour % 12 or 12
            ends_abs = f"{d.strftime('%a %b')} {d.day} at {h}:{d.strftime('%M %p %Z')}"
        except Exception:
            ends_abs = ""

    retail_s = f"${retail:,.2f}" if retail else "—"
    bid_s    = f"${bid_amt:,.2f}" if bid_amt else "—"
    off_s    = ""
    if retail and bid_amt:
        off_pct = int(100 * (1 - bid_amt / retail))
        off_s   = f"  ({off_pct}% off retail)"

    url = _auction_url(it)
    modal_w = min(max_x - 2, 96)
    modal_h = min(max_y - 2, 42)
    y0 = max(0, (max_y - modal_h) // 2)
    x0 = max(0, (max_x - modal_w) // 2)
    inner_w = modal_w - 4

    content = []
    content += _wrap(title, inner_w)
    content.append("")
    if brand:
        content.append(f"Brand:       {brand}")
    if model_num:
        content.append(f"Model:       {model_num}")
    content.append(f"Condition:   {cond}")
    content.append(f"Current Bid: {bid_s}")
    content.append(f"Retail:      {retail_s}{off_s}")
    content.append(f"Time Left:   {ends}")
    if ends_abs:
        content.append(f"Ends:        {ends_abs}")
    content.append(f"Location:    {location}")
    if url:
        content.append(f"URL:         {url[:inner_w]}")
    if description:
        content.append("")
        content.append("─── Description " + "─" * max(0, inner_w - 16))
        content += _wrap(description, inner_w)
    if notes or detail_status == "done":
        content.append("")
        content.append("─── Seller Notes " + "─" * max(0, inner_w - 17))
        if notes:
            content += _wrap(notes, inner_w)
        else:
            content.append("  (none)")

    if detail_status == "loading":
        content.append("")
        content.append("─── Bid History " + "─" * max(0, inner_w - 16))
        content.append("  ⏳  Loading bid history…")
    elif detail_status == "error":
        content.append("")
        content.append("─── Bid History " + "─" * max(0, inner_w - 16))
        content.append("  ⚠  Could not load bid history")
    elif detail_status == "done" and detail_data is not None:
        bids = (detail_data.get("computedBidHistory")
                or detail_data.get("bidHistory")
                or detail_data.get("bids") or [])
        content.append("")
        content.append("─── Bid History " + "─" * max(0, inner_w - 16))
        if bids:
            sorted_bids = sorted(
                bids, key=lambda b: b.get("amount") or 0, reverse=True)
            for bid in sorted_bids:
                amt    = bid.get("amount") or 0
                ts_raw = bid.get("placedAt") or bid.get("createdAt") or ""
                ts_s   = ""
                try:
                    bd = parse_dt(ts_raw).astimezone()
                    bh = bd.hour % 12 or 12
                    ts_s = f"{bd.strftime('%m/%d')} {bh}:{bd.strftime('%M %p')}"
                except Exception:
                    pass
                is_me  = bool(customer_id
                              and bid.get("customerId") == customer_id)
                handle = bid.get("handle") or "?"
                me_tag = "  ← YOU" if is_me else ""
                content.append(
                    f"  ${amt:>8.2f}   @{handle:<18} {ts_s}{me_tag}")
        else:
            content.append("  No bids yet")

    HEADER_H   = 3
    FOOTER_H   = 3
    avail_h    = modal_h - HEADER_H - FOOTER_H
    sep_top    = 2
    sep_bottom = modal_h - FOOTER_H

    max_scroll    = max(0, len(content) - avail_h)
    detail_scroll = max(0, min(detail_scroll, max_scroll))

    for dy in range(modal_h):
        y = y0 + dy
        if y >= max_y:
            break
        if dy == 0:
            row_str = "╔" + "═" * (modal_w - 2) + "╗"
        elif dy == modal_h - 1:
            row_str = "╚" + "═" * (modal_w - 2) + "╝"
        elif dy == sep_top or dy == sep_bottom:
            row_str = "╠" + "═" * (modal_w - 2) + "╣"
        else:
            row_str = "║" + " " * (modal_w - 2) + "║"
        _safe(stdscr, y, x0, row_str, curses.color_pair(CP_HEADER))

    _safe(stdscr, y0 + 1, x0 + 2,
          "  Auction Detail".center(modal_w - 4),
          curses.color_pair(CP_HEADER) | curses.A_BOLD)

    visible = content[detail_scroll: detail_scroll + avail_h]
    for i, ln in enumerate(visible):
        _safe(stdscr, y0 + HEADER_H + i, x0 + 2, ln[:inner_w])

    if max_scroll > 0:
        pct = int(100 * detail_scroll / max_scroll)
        _safe(stdscr, y0 + sep_bottom - 1, x0 + modal_w - 9,
              f" {pct:>3}% ↕", curses.color_pair(CP_DIM))

    hints = ("  [B] Snipe   [O] Open in Browser   "
             "[A] Amazon Search   [↑↓] Scroll   [Esc] Close  ")
    _safe(stdscr, y0 + sep_bottom + 1, x0 + 2,
          hints[:inner_w], curses.color_pair(CP_DIM))

    return detail_scroll


def _draw_footer(stdscr, max_y, max_x,
                 active_quick, loc_id, locations,
                 active_conds, price_min, price_max,
                 loading, prompt):
    _hline(stdscr, max_y - FOOTER_HEIGHT)

    col = 2
    for i, (val, lbl) in enumerate(QUICK_FILTERS, start=1):
        on   = val in active_quick
        text = f" {i}:{lbl} "
        if col + len(text) >= max_x - 1:
            break
        attr = (curses.color_pair(CP_WON) | curses.A_BOLD) if on else curses.color_pair(CP_DIM)
        _safe(stdscr, max_y - 6, col, text, attr)
        col += len(text)
        if col < max_x - 2:
            _safe(stdscr, max_y - 6, col, "│", curses.color_pair(CP_DIM))
            col += 1

    if locations:
        loc_label = "All"
        for loc in locations:
            lid = loc.get("id") or loc.get("storeLocationId")
            if lid == loc_id:
                city       = loc.get("city", "")
                state_abbr = loc.get("state", "")
                loc_label  = f"{city}, {state_abbr}" if state_abbr else city
                break
    else:
        loc_label = "…"
    loc_on   = bool(loc_id)
    loc_attr = ((curses.color_pair(CP_SNIPED) | curses.A_BOLD)
                if loc_on else curses.color_pair(CP_DIM))

    if active_conds:
        cond_label = "/".join(COND_MAP.get(c, c) for c in active_conds)
        cond_attr  = curses.color_pair(CP_WON) | curses.A_BOLD
    else:
        cond_label = "All"
        cond_attr  = curses.color_pair(CP_DIM)

    if price_min is not None or price_max is not None:
        lo = f"${price_min:.0f}" if price_min is not None else "any"
        hi = f"${price_max:.0f}" if price_max is not None else "any"
        price_label = f"{lo}–{hi}"
        price_attr  = curses.color_pair(CP_WON) | curses.A_BOLD
    else:
        price_label = "Any"
        price_attr  = curses.color_pair(CP_DIM)

    bar_x = 0
    _safe(stdscr, max_y - 5, bar_x, "  [L] Loc: ", curses.color_pair(CP_DIM))
    bar_x += 11
    _safe(stdscr, max_y - 5, bar_x, loc_label, loc_attr)
    bar_x += len(loc_label)
    _safe(stdscr, max_y - 5, bar_x, "   [C] Cond: ", curses.color_pair(CP_DIM))
    bar_x += 13
    _safe(stdscr, max_y - 5, bar_x, cond_label, cond_attr)
    bar_x += len(cond_label)
    _safe(stdscr, max_y - 5, bar_x, "   [P] Retail: ", curses.color_pair(CP_DIM))
    bar_x += 15
    _safe(stdscr, max_y - 5, bar_x, price_label, price_attr)

    p_mode = prompt.get("mode", "")

    if p_mode == "browse_detail":
        ds            = prompt["data"].get("detail_scroll", 0)
        it_data       = prompt["data"].get("item", {})
        detail_status = prompt["data"].get("_detail_status", "")
        detail_data   = prompt["data"].get("_detail_data", None)
        cust_id       = prompt["data"].get("_customer_id", "")
        new_ds = draw_browse_detail(stdscr, it_data, ds,
                                    detail_status=detail_status,
                                    detail_data=detail_data,
                                    customer_id=cust_id)
        prompt["data"]["detail_scroll"] = new_ds
        try:
            stdscr.move(max_y - 1, 0)
        except curses.error:
            pass

    elif p_mode == "browse_snipe":
        fields  = PROMPT_FIELDS["browse_snipe"]
        step    = prompt.get("step", 0)
        _key, label, _default = fields[step]
        error_s = prompt.get("error", "")
        prefix  = f"  ❯  {label}:  "
        if error_s:
            _safe(stdscr, max_y - 4, 0,
                  f"  ⚠  {error_s}", curses.color_pair(CP_ERROR))
        else:
            _safe(stdscr, max_y - 4, 0,
                  f"  Sniping: step {step + 1}/{len(fields)}"
                  f"   ↵ confirm  ·  Esc cancel",
                  curses.color_pair(CP_DIM))
        buf     = prompt.get("buf", "")
        avail   = max(1, max_x - len(prefix) - 1)
        visible = buf[-avail:] if len(buf) > avail else buf
        _safe(stdscr, max_y - 2, 0, prefix + visible)
        try:
            stdscr.move(max_y - 2, min(len(prefix) + len(visible), max_x - 1))
        except curses.error:
            pass

    elif p_mode == "browse_search":
        label  = "  Search: "
        buf    = prompt.get("buf", "")
        avail  = max(1, max_x - len(label) - 1)
        vis    = buf[-avail:] if len(buf) > avail else buf
        _safe(stdscr, max_y - 4, 0,
              "  Type search term, ↵ to apply, Esc to cancel",
              curses.color_pair(CP_DIM))
        _safe(stdscr, max_y - 2, 0, label + vis)
        try:
            stdscr.move(max_y - 2, min(len(label) + len(vis), max_x - 1))
        except curses.error:
            pass

    elif p_mode == "browse_price":
        step    = prompt.get("step", 0)
        labels  = ["Min retail price (blank = no min, Enter to skip)",
                   "Max retail price (blank = no max)"]
        label   = labels[step] if step < len(labels) else labels[-1]
        error_s = prompt.get("error", "")
        prefix  = f"  $ {label}:  "
        if error_s:
            _safe(stdscr, max_y - 4, 0,
                  f"  ⚠  {error_s}", curses.color_pair(CP_ERROR))
        else:
            _safe(stdscr, max_y - 4, 0,
                  f"  Price range — step {step + 1}/2"
                  f"   ↵ confirm  ·  Esc cancel",
                  curses.color_pair(CP_DIM))
        buf     = prompt.get("buf", "")
        avail   = max(1, max_x - len(prefix) - 1)
        visible = buf[-avail:] if len(buf) > avail else buf
        _safe(stdscr, max_y - 2, 0, prefix + visible)
        try:
            stdscr.move(max_y - 2, min(len(prefix) + len(visible), max_x - 1))
        except curses.error:
            pass

    else:
        _safe(stdscr, max_y - 4, 0,
              "  ↑↓ move  [↵] Detail  [o] Open  [a] Amazon  [b] Snipe",
              curses.color_pair(CP_DIM))
        _safe(stdscr, max_y - 3, 0,
              "  [1-7] Filters  [L] Location  [C] Condition"
              "  [P] Price  [/] Search  [s] Sort  [r] Refresh  [q] Quit",
              curses.color_pair(CP_DIM))
        spinner = "⏳ refreshing…" if loading else ""
        _safe(stdscr, max_y - 2, 0, f"  {spinner}", curses.color_pair(CP_DIM))
        try:
            stdscr.move(max_y - 1, 0)
        except curses.error:
            pass


def draw_browse(stdscr, state: ClientState, prompt: dict) -> None:
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()
    row = 0

    now_str    = datetime.now().strftime("%a %b %d %Y  %I:%M:%S %p")
    tab_hint   = "[Tab] back"
    snipe_info = _snipe_header_str(state)
    acct       = state.active_login_name or state.user_display
    header     = (f"  BuyWander Sniper  │  {acct}"
                  f"  │  Browse Auctions  │  {now_str}{snipe_info}")
    header_pad = (header.ljust(max_x - len(tab_hint) - 2)
                  [:max_x - len(tab_hint) - 2])
    _safe(stdscr, row, 0,
          (header_pad + tab_hint + " ").ljust(max_x - 1),
          curses.color_pair(CP_HEADER) | curses.A_BOLD)
    row += 1
    _hline(stdscr, row); row += 1

    with state.lock:
        items       = list(state.browse_items)
        loading     = state.browse_loading
        total_count = state.browse_total
        sort_lbl    = BROWSE_SORT_LABELS.get(state.browse_sort, state.browse_sort)
        search_q    = state.browse_search
        cursor      = state.browse_cursor
        scroll      = state.browse_scroll
        active_quick = set(state.browse_quick_filters)
        active_conds = list(state.browse_conditions)
        price_min   = state.browse_price_min
        price_max   = state.browse_price_max
        loc_id      = state.browse_location_id
        locations   = list(state.browse_locations)
        detail_cache = dict(state.browse_detail_cache)
        customer_id  = state.customer_id

    # Sync detail cache into modal
    if prompt.get("mode") == "browse_detail":
        aid = prompt["data"].get("_detail_auction_id", "")
        if aid and aid in detail_cache:
            prompt["data"]["_detail_status"] = state.browse_detail_status.get(aid, "")
            prompt["data"]["_detail_data"]   = detail_cache.get(aid)

    # Sort / count bar
    filter_parts = [f"Sort: {sort_lbl}"]
    if search_q:
        filter_parts.append(f"Search: \"{search_q}\"")
    filter_info = "  " + "  │  ".join(filter_parts)

    n_loaded = len(items)
    count_info = f"({total_count:,} auctions)" if total_count else f"({n_loaded} loaded)"
    filter_padded = (filter_info.ljust(max_x - len(count_info) - 2)
                     [:max_x - len(count_info) - 2])
    _safe(stdscr, row, 0, filter_padded + count_info + " ",
          curses.color_pair(CP_DIM))
    row += 1
    _hline(stdscr, row); row += 1

    if loading and not items:
        _safe(stdscr, row, 0, "  ⏳  Loading auctions…", curses.color_pair(CP_DIM))
    elif not items:
        _safe(stdscr, row, 0,
              "  No auctions found — try different filters.",
              curses.color_pair(CP_DIM))
    else:
        col_hdr = (f"  {'#':<4}  {'Title':<72}  {'Cond':<12}"
                   f"  {'Bid':>6}  {'Retail':>7}  {'Off':>4}  {'Ends':>9}  {'Location':<12}")
        _safe(stdscr, row, 0, col_hdr[:max_x - 1],
              curses.A_BOLD | curses.A_UNDERLINE)
        row += 1

        content_lines = max(1, max_y - row - FOOTER_HEIGHT)
        visible_rows  = max(1, content_lines - 1)

        cursor = max(0, min(cursor, max(0, len(items) - 1)))
        if cursor < scroll:
            scroll = cursor
        elif cursor >= scroll + visible_rows:
            scroll = cursor - visible_rows + 1

        with state.lock:
            state.browse_cursor = cursor
            state.browse_scroll = scroll

        now_utc = datetime.now(timezone.utc)
        cur_row = row
        for idx, it in enumerate(items[scroll: scroll + visible_rows]):
            if cur_row >= max_y - FOOTER_HEIGHT:
                break
            abs_idx = scroll + idx
            is_sel  = (abs_idx == cursor)

            item_sub = it.get("item") or {}
            title    = item_sub.get("title") or "?"
            cond_raw = item_sub.get("condition") or ""
            cond     = COND_MAP.get(cond_raw, cond_raw)[:12]
            retail   = item_sub.get("price") or 0.0
            loc_sub  = it.get("storeLocation") or {}
            loc_city = loc_sub.get("city") or loc_sub.get("name") or "?"
            loc_st   = loc_sub.get("state") or ""
            loc_disp = (f"{loc_city}, {loc_st}" if loc_st else loc_city)[:12]

            wb      = it.get("winningBid") or {}
            bid_amt = wb.get("amount") or 0.0
            bid_s   = f"${bid_amt:.0f}" if bid_amt else "  --"
            retail_s = f"${retail:.0f}" if retail else "  --"

            if retail and bid_amt:
                off   = int(100 * (1 - bid_amt / retail))
                off_s = f"{off}%"
            else:
                off_s = " --"

            secs_left = None
            try:
                end_dt    = parse_dt(it.get("endDate", ""))
                secs_left = (end_dt - now_utc).total_seconds()
                left_s    = fmt_time(secs_left) if secs_left > 0 else "ENDED"
            except Exception:
                left_s = "?"

            title_t = title[:72]
            line = (f"  {abs_idx + 1:<4}  {title_t:<72}  {cond:<12}"
                    f"  {bid_s:>6}  {retail_s:>7}  {off_s:>4}"
                    f"  {left_s:>9}  {loc_disp:<12}")

            if is_sel:
                attr = curses.color_pair(CP_HEADER) | curses.A_BOLD
            elif secs_left is not None and secs_left <= 300:
                attr = curses.color_pair(CP_SNIPED)
            else:
                attr = 0
            _safe(stdscr, cur_row, 0, line[:max_x - 1], attr)
            cur_row += 1

        if loading and items and cur_row < max_y - FOOTER_HEIGHT:
            _safe(stdscr, cur_row, 2, "⏳ Loading more…", curses.color_pair(CP_DIM))

        if len(items) > visible_rows:
            pct = int(100 * scroll / max(1, len(items) - visible_rows))
            _safe(stdscr, max_y - FOOTER_HEIGHT - 1, max_x - 8,
                  f" {pct:>3}%  ", curses.color_pair(CP_DIM))

    _draw_footer(stdscr, max_y, max_x,
                 active_quick, loc_id, locations,
                 active_conds, price_min, price_max,
                 loading, prompt)
    stdscr.refresh()
