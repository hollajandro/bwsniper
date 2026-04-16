"""
backend/app/api/price_compare.py — Google Shopping price comparison via Serper.dev.

Requires a free Serper.dev API key (2,500 searches/month free):
  https://serper.dev → sign up → Dashboard → API Key
Set as environment variable: SERPER_API_KEY=<your key>
"""

import json
import re
import logging

import requests as _requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from ..config import SERPER_API_KEY as _ENV_SERPER_KEY
from ..db.database import get_db
from ..db.models import User, UserConfig
from ..dependencies import get_current_user

log = logging.getLogger(__name__)

router = APIRouter(prefix="/price-compare", tags=["price-compare"])
limiter = Limiter(key_func=get_remote_address)

_SERPER_URL = "https://google.serper.dev/shopping"
_MAX_RESULTS = 10


def _parse_price(price_str: str) -> float | None:
    """Extract a numeric price from a string like '$29.99', '€249', '£19.50 - £49'."""
    if not price_str:
        return None
    # Take only the first price if a range is given
    first = price_str.split("-")[0].split("–")[0]
    m = re.search(r"[\d]+(?:[.,]\d+)*", first)
    if not m:
        return None
    try:
        return float(m.group().replace(",", ""))
    except ValueError:
        return None


def _fetch_shopping(query: str, api_key: str) -> list[dict]:
    """Call Serper.dev and return top results sorted by price ascending."""
    try:
        resp = _requests.post(
            _SERPER_URL,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": 20},
            timeout=10,
        )
        resp.raise_for_status()
    except _requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Price compare request timed out.")
    except _requests.HTTPError as exc:
        log.warning("Serper API error: %s", exc)
        raise HTTPException(status_code=502, detail="Price compare service error.")
    except _requests.exceptions.RequestException as exc:
        log.warning("Serper request failed: %s", exc)
        raise HTTPException(status_code=502, detail="Price compare service unavailable.")

    shopping = resp.json().get("shopping", [])
    parsed = []
    for item in shopping:
        price_str = item.get("price", "")
        price_num = _parse_price(price_str)
        if price_num is None or price_num <= 0:
            continue
        parsed.append({
            "title":     item.get("title", ""),
            "price":     price_num,
            "price_str": price_str,
            "source":    item.get("source", ""),
            "link":      item.get("link", ""),
        })

    parsed.sort(key=lambda x: x["price"])
    return parsed[:_MAX_RESULTS]


def _get_api_key(user: User, db: Session) -> str:
    """Return the user's stored Serper key, or fall back to the server env var."""
    cfg = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
    if cfg:
        try:
            key = json.loads(cfg.config_json).get("serper_api_key", "")
            if key:
                return key
        except Exception:
            pass
    return _ENV_SERPER_KEY


@router.get("")
@limiter.limit("30/minute")
def price_compare(
    request: Request,
    q: str = Query(..., min_length=1, max_length=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return up to 10 cheapest Google Shopping listings for the given query."""
    api_key = _get_api_key(user, db)
    if not api_key:
        raise HTTPException(status_code=503, detail="no_key")
    results = _fetch_shopping(q.strip(), api_key)
    return {"query": q.strip(), "results": results}
