"""
cli/bwsniper/main.py — Entry point for the BWSNiper TUI client.

Usage:
    python -m bwsniper [--server URL]

Authenticates against the FastAPI backend, loads initial state,
and launches the curses TUI.
"""

import argparse
import curses
import os
import sys

from .api_client import ApiClient
from .auth import try_restore_session, interactive_login, clear_session
from .state import ClientState
from .tui.runner import run_tui

DEFAULT_SERVER = os.environ.get("BWSNIPER_SERVER", "http://localhost:8000")


def main():
    parser = argparse.ArgumentParser(
        description="BuyWander Sniper — TUI Client")
    parser.add_argument(
        "--server", "-s",
        default=DEFAULT_SERVER,
        help=f"Server URL (default: {DEFAULT_SERVER})")
    parser.add_argument(
        "--logout",
        action="store_true",
        help="Clear saved session and log in fresh")
    args = parser.parse_args()

    if args.logout:
        clear_session()
        print("  Session cleared.\n")

    # Authenticate
    client = try_restore_session(args.server)
    if client is None:
        client = interactive_login(args.server)

    # Build client state and start background sync
    state = ClientState(client)
    print("  Loading data from server…")
    state.start_poller()

    # Launch TUI
    try:
        curses.wrapper(run_tui, state)
    except KeyboardInterrupt:
        pass
    finally:
        state.stop_poller()
        print("\n  Goodbye!\n")


if __name__ == "__main__":
    main()
