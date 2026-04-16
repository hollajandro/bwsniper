"""
cli/bwsniper/tui/settings.py — Settings tab for the thin client.

Settings are stored on the server via the /settings API.
"""

import curses
from datetime import datetime

from ..state import ClientState
from .common import (
    CP_HEADER, CP_WON, CP_SNIPED, CP_DIM, CP_ERROR,
    _safe, _hline, _snipe_header_str,
)


SETTINGS_DEFS: list = [
    {"type": "header", "label": "── Defaults ─────────────────────────────────────────────────"},
    {"type": "field",  "label": "Default Snipe Seconds",   "path": ["defaults", "snipe_seconds"],               "kind": "int"},

    {"type": "header", "label": "── Notifications ────────────────────────────────────────────"},
    {"type": "field",  "label": "Remind Before (seconds)", "path": ["notifications", "remind_before_seconds"],  "kind": "int"},

    {"type": "header", "label": "  ▸ Telegram"},
    {"type": "field",  "label": "    Enabled",             "path": ["notifications", "telegram", "enabled"],    "kind": "bool"},
    {"type": "field",  "label": "    Bot Token",           "path": ["notifications", "telegram", "bot_token"],  "kind": "str"},
    {"type": "field",  "label": "    Chat ID",             "path": ["notifications", "telegram", "chat_id"],    "kind": "str"},

    {"type": "header", "label": "  ▸ SMTP Email"},
    {"type": "field",  "label": "    Enabled",             "path": ["notifications", "smtp", "enabled"],        "kind": "bool"},
    {"type": "field",  "label": "    Host",                "path": ["notifications", "smtp", "host"],           "kind": "str"},
    {"type": "field",  "label": "    Port",                "path": ["notifications", "smtp", "port"],           "kind": "int"},
    {"type": "field",  "label": "    Username",            "path": ["notifications", "smtp", "username"],       "kind": "str"},
    {"type": "field",  "label": "    Password",            "path": ["notifications", "smtp", "password"],       "kind": "password"},
    {"type": "field",  "label": "    From Address",        "path": ["notifications", "smtp", "from_addr"],      "kind": "str"},
    {"type": "field",  "label": "    To Address",          "path": ["notifications", "smtp", "to_addr"],        "kind": "str"},

    {"type": "header", "label": "  ▸ Pushover"},
    {"type": "field",  "label": "    Enabled",             "path": ["notifications", "pushover", "enabled"],    "kind": "bool"},
    {"type": "field",  "label": "    User Key",            "path": ["notifications", "pushover", "user_key"],   "kind": "str"},
    {"type": "field",  "label": "    App Token",           "path": ["notifications", "pushover", "app_token"],  "kind": "str"},

    {"type": "header", "label": "  ▸ Gotify"},
    {"type": "field",  "label": "    Enabled",             "path": ["notifications", "gotify", "enabled"],      "kind": "bool"},
    {"type": "field",  "label": "    Server URL",          "path": ["notifications", "gotify", "url"],          "kind": "str"},
    {"type": "field",  "label": "    Token",               "path": ["notifications", "gotify", "token"],        "kind": "str"},
    {"type": "field",  "label": "    Priority (1-10)",     "path": ["notifications", "gotify", "priority"],     "kind": "int"},
]

FIELD_INDICES: list = [i for i, d in enumerate(SETTINGS_DEFS) if d["type"] == "field"]


def fresh_settings_state() -> dict:
    return {
        "cursor": FIELD_INDICES[0],
        "edit":   False,
        "buf":    "",
        "scroll": 0,
        "msg":    "",
    }


def settings_move(st: dict, direction: int) -> None:
    try:
        pos = FIELD_INDICES.index(st["cursor"])
    except ValueError:
        pos = 0
    pos = (pos + direction) % len(FIELD_INDICES)
    st["cursor"] = FIELD_INDICES[pos]


def _get_nested(cfg: dict, path: list):
    """Safely get a nested dict value by path."""
    for key in path:
        if isinstance(cfg, dict):
            cfg = cfg.get(key)
        else:
            return None
    return cfg


def _set_nested(cfg: dict, path: list, value):
    """Safely set a nested dict value by path."""
    for key in path[:-1]:
        if key not in cfg or not isinstance(cfg.get(key), dict):
            cfg[key] = {}
        cfg = cfg[key]
    cfg[path[-1]] = value


def draw_settings(stdscr, state: ClientState, st: dict) -> None:
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()
    row = 0

    now_str    = datetime.now().strftime("%a %b %d %Y  %I:%M:%S %p")
    tab_hint   = "[Tab] next"
    snipe_info = _snipe_header_str(state)
    acct       = state.active_login_name or state.user_display
    header     = (f"  BuyWander Sniper  │  {acct}"
                  f"  │  Settings  │  {now_str}{snipe_info}")
    hpad = (header.ljust(max_x - len(tab_hint) - 2)
            [:max_x - len(tab_hint) - 2])
    _safe(stdscr, row, 0, (hpad + tab_hint + " ").ljust(max_x - 1),
          curses.color_pair(CP_HEADER) | curses.A_BOLD)
    row += 1
    _hline(stdscr, row); row += 1

    cfg    = state.user_config
    cursor = st["cursor"]
    edit   = st["edit"]
    buf    = st["buf"]

    FOOTER_ROWS = 3
    avail = max(1, max_y - row - FOOTER_ROWS)

    scroll_top = st.get("scroll", 0)
    if cursor < scroll_top:
        scroll_top = cursor
    elif cursor >= scroll_top + avail:
        scroll_top = cursor - avail + 1
    scroll_top   = max(0, scroll_top)
    st["scroll"] = scroll_top

    visible = SETTINGS_DEFS[scroll_top: scroll_top + avail]

    for i, defn in enumerate(visible):
        def_idx = scroll_top + i
        scr_row = row + i
        if scr_row >= max_y - FOOTER_ROWS:
            break

        if defn["type"] == "header":
            _safe(stdscr, scr_row, 2, defn["label"][:max_x - 3],
                  curses.A_BOLD | curses.color_pair(CP_SNIPED))
            continue

        is_sel = (def_idx == cursor)
        val    = _get_nested(cfg, defn["path"])
        kind   = defn["kind"]
        label  = defn["label"]

        if kind == "bool":
            val_s = "✓ Yes" if val else "  No"
        elif kind == "password":
            val_s = ("•" * min(len(str(val or "")), 24)) if val else "(not set)"
        else:
            val_s = str(val) if val is not None else "(not set)"

        if is_sel and edit:
            val_s = buf + "▌"
        elif is_sel and kind == "bool":
            val_s = ("✓ Yes" if val else "  No") + "  [Space/↵ to toggle]"

        prefix = "▶ " if is_sel else "  "
        line   = f"{prefix}{label:<38}  {val_s}"
        attr   = (curses.color_pair(CP_HEADER) | curses.A_BOLD) if is_sel else 0
        _safe(stdscr, scr_row, 0, line[:max_x - 1], attr)

    _hline(stdscr, max_y - FOOTER_ROWS)

    if st.get("msg"):
        _safe(stdscr, max_y - FOOTER_ROWS + 1, 0,
              f"  {st['msg']}", curses.color_pair(CP_WON) | curses.A_BOLD)
    elif edit:
        defn = SETTINGS_DEFS[cursor]
        kind = defn["kind"]
        if kind == "bool":
            hint = "  [Space/↵] toggle   [Esc] cancel"
        else:
            hint = "  Type new value   [↵] save   [Esc] cancel"
        _safe(stdscr, max_y - FOOTER_ROWS + 1, 0, hint[:max_x - 1],
              curses.color_pair(CP_DIM))
    else:
        hint = ("  ↑↓ navigate   [↵/Space] edit / toggle"
                "   [S] save to server   [Tab] next tab   [Q] quit")
        _safe(stdscr, max_y - FOOTER_ROWS + 1, 0, hint[:max_x - 1],
              curses.color_pair(CP_DIM))

    try:
        cur_pos = FIELD_INDICES.index(cursor) + 1
    except ValueError:
        cur_pos = 1
    total_fields = len(FIELD_INDICES)
    _safe(stdscr, max_y - FOOTER_ROWS + 2, 0,
          f"  Field {cur_pos}/{total_fields}",
          curses.color_pair(CP_DIM))

    try:
        stdscr.move(max_y - 1, 0)
    except curses.error:
        pass
    stdscr.refresh()
