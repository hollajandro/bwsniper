"""
backend/app/utils/time.py — Timezone-aware UTC timestamp utility.

Ensures consistent use of timezone-aware UTC datetimes across the codebase.
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)
