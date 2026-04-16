"""
cli/bwsniper/auth.py — Interactive login / register for the TUI client.

Runs in the normal terminal (before curses is initialised).
Persists tokens to ~/.config/bwsniper-cli/session.json so subsequent
launches skip the login prompt.
"""

import getpass
import json
import os
import stat
import sys
from pathlib import Path
from typing import Optional

from .api_client import ApiClient, AuthError

SESSION_DIR = Path(os.environ.get(
    "BWSNIPER_CLI_CONFIG", Path.home() / ".config" / "bwsniper-cli"))
SESSION_FILE = SESSION_DIR / "session.json"


def _save_session(client: ApiClient, server_url: str) -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps({
        "server": server_url,
        "access_token": client.access_token,
        "refresh_token": client.refresh_token,
        "user_id": client.user_id,
        "display_name": client.display_name,
    }, indent=2))
    # Restrict to owner-read/write only — tokens are sensitive credentials
    try:
        SESSION_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # Windows or unusual FS — best effort


def _load_session() -> Optional[dict]:
    if SESSION_FILE.exists():
        try:
            return json.loads(SESSION_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return None


def clear_session() -> None:
    if SESSION_FILE.exists():
        SESSION_FILE.unlink(missing_ok=True)


def try_restore_session(server_url: str) -> Optional[ApiClient]:
    """Attempt to restore a saved session.  Returns ApiClient or None."""
    saved = _load_session()
    if not saved:
        return None
    if saved.get("server") != server_url:
        return None
    client = ApiClient(server_url)
    client.access_token = saved.get("access_token", "")
    client.refresh_token = saved.get("refresh_token", "")
    client.user_id = saved.get("user_id", "")
    client.display_name = saved.get("display_name", "")
    # Verify tokens are still valid by fetching settings
    try:
        client.get_settings()
        return client
    except (AuthError, Exception):
        # Token expired and couldn't refresh — fall through to interactive
        return None


def interactive_login(server_url: str) -> ApiClient:
    """Interactive terminal flow: login or register, returns authenticated client."""
    client = ApiClient(server_url)

    print(f"\n  BuyWander Sniper — Server: {server_url}\n")
    print("  [L] Log in   [R] Register   [Q] Quit\n")

    while True:
        choice = input("  > ").strip().lower()
        if choice in ("q", "quit", "exit"):
            sys.exit(0)
        if choice in ("l", "login"):
            return _do_login(client, server_url)
        if choice in ("r", "register"):
            return _do_register(client, server_url)
        print("  Please enter L, R, or Q.")


def _do_login(client: ApiClient, server_url: str) -> ApiClient:
    print()
    email = input("  Email: ").strip()
    password = getpass.getpass("  Password: ")
    try:
        client.login(email, password)
        _save_session(client, server_url)
        print(f"\n  Welcome back, {client.display_name or email}!\n")
        return client
    except AuthError as e:
        print(f"\n  Login failed: {e}")
        return interactive_login(server_url)
    except Exception as e:
        print(f"\n  Connection error: {e}")
        print("  Make sure the server is running.\n")
        sys.exit(1)


def _do_register(client: ApiClient, server_url: str) -> ApiClient:
    print()
    email = input("  Email: ").strip()
    display = input("  Display name (optional): ").strip()
    password = getpass.getpass("  Password: ")
    confirm = getpass.getpass("  Confirm password: ")
    if password != confirm:
        print("\n  Passwords don't match.\n")
        return interactive_login(server_url)
    try:
        client.register(email, password, display)
        # Auto-login after registration
        client.login(email, password)
        _save_session(client, server_url)
        print(f"\n  Account created! Welcome, {client.display_name or email}.\n")
        return client
    except Exception as e:
        print(f"\n  Registration failed: {e}\n")
        return interactive_login(server_url)
