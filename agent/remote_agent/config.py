"""
Environment-driven configuration for the remote redundant agent.
"""

from __future__ import annotations

import os


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


MAIN_BACKEND_URL = _required("MAIN_BACKEND_URL").rstrip("/")
AGENT_ID = _required("AGENT_ID")
AGENT_API_KEY = _required("AGENT_API_KEY")
SYNC_INTERVAL_MS = int(os.getenv("SYNC_INTERVAL_MS", "3000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
AGENT_VERSION = os.getenv("AGENT_VERSION", "remote-agent/1.0")
