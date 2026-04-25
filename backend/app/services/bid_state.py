"""
Helpers for interpreting bid outcomes in redundant execution scenarios.
"""

from __future__ import annotations

import requests as _requests


def extract_http_error_detail(ex: Exception) -> str:
    """Return the most useful message available from an HTTP exception."""
    if isinstance(ex, _requests.HTTPError) and ex.response is not None:
        try:
            detail = ex.response.json().get("detail")
            if detail:
                return str(detail)
        except Exception:
            pass
        try:
            body = ex.response.text.strip()
            if body:
                return body
        except Exception:
            pass
    return str(ex)


def auction_shows_bid_applied(
    auction: dict,
    customer_id: str,
    bid_amount: float,
) -> bool:
    """
    Detect whether a just-submitted bid likely succeeded despite a stale/conflict
    response by inspecting the refreshed auction payload.
    """
    winning_bid = auction.get("winningBid") or {}
    if winning_bid.get("customerId") == customer_id:
        return True

    my_max_raw = auction.get("customerMaxBid")
    if my_max_raw is None:
        return False

    try:
        my_max_bid = float(my_max_raw)
    except (TypeError, ValueError):
        return False

    return my_max_bid + 1e-9 >= bid_amount
