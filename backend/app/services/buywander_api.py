"""
backend/app/services/buywander_api.py — BuyWander upstream API calls.

All functions accept a requests.Session (already authenticated with BW)
plus parameters, and return parsed Python data or raise on error.

Extracted from the original bw/api.py and parameterised for multi-login use.
"""

import logging
import re
import json
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from typing import Optional

import requests as _requests

from ..config import BW_API_BASE, BW_SITE_BASE, BW_SESSION_HEADERS, BROWSE_PAGE_SIZE
from ..utils.crypto import decrypt

log = logging.getLogger(__name__)

# Allowlists for filter parameters to prevent injection into BuyWander API
ALLOWED_CONDITIONS = frozenset(
    {
        "New",
        "AppearsNew",
        "UsedGood",
        "UsedFair",
        "Damaged",
        "GentlyUsed",
        "Used",
        "EasyFix",
        "HeavyUse",
        "MajorFix",
        "MixedCondition",
    }
)
ALLOWED_AUCTION_FILTERS = frozenset({"BuyNow", "NoReserve", "HasBids", "Featured"})
ALLOWED_SORT = frozenset(
    {
        "EndingSoonest",
        "NewlyListed",
        "LowestBid",
        "HighestBid",
        "MostBids",
        "HighestRetail",
        "LowestRetail",
    }
)

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)

# Patterns that match Stripe publishable and secret keys — used to redact
# sensitive values from logs so keys are never written to disk/logs in plaintext.
_STRIPE_KEY_RE = re.compile(
    r"(pk_live_[A-Za-z0-9]{20,}|pk_test_[A-Za-z0-9]{20,}|"
    r"sk_live_[A-Za-z0-9]{20,}|sk_test_[A-Za-z0-9]{20,})"
)


def _redact_stripe_keys(text: str) -> str:
    """Replace any Stripe key literals with [REDACTED] in log strings."""
    if not text:
        return text
    return _STRIPE_KEY_RE.sub("[REDACTED]", text)


# ── Session factory ──────────────────────────────────────────────────────────


def create_bw_session(encrypted_cookies: str | None = None) -> _requests.Session:
    """Build a requests.Session pre-loaded with BW headers and optional cookies."""
    s = _requests.Session()
    s.headers.update(BW_SESSION_HEADERS)
    if encrypted_cookies:
        try:
            cookie_data = json.loads(decrypt(encrypted_cookies))
            for k, v in cookie_data.items():
                s.cookies.set(k, v)
        except Exception:
            pass
    return s


def serialise_cookies(session: _requests.Session) -> str:
    """Return a JSON dict of session cookies (unencrypted)."""
    return json.dumps({k: v for k, v in session.cookies.items()})


# ── Auth ─────────────────────────────────────────────────────────────────────


def validate_session(session: _requests.Session) -> Optional[dict]:
    """Return customer dict if the BW session is valid, else None."""
    try:
        r = session.get(f"{BW_API_BASE}/api/site/Customers/me", timeout=8)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def bw_login(session: _requests.Session, email: str, password: str) -> dict:
    """Authenticate with BuyWander.  Raises ValueError on failure."""
    r = session.post(
        f"{BW_API_BASE}/api/site/ShopifyAuth/login",
        json={"email": email, "password": password},
        timeout=10,
    )
    if r.status_code == 401:
        raise ValueError("Invalid BuyWander email or password.")
    if r.status_code == 403:
        raise ValueError("BuyWander email not verified — check your inbox.")
    r.raise_for_status()
    data = r.json()
    if not data.get("isSuccess"):
        raise ValueError(data.get("errorMessage") or "BuyWander login failed.")
    return data


# ── URL / handle helpers ─────────────────────────────────────────────────────


def is_uuid(s: str) -> bool:
    return bool(_UUID_RE.match(s))


def extract_handle(url: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "auctionId" in qs:
        return qs["auctionId"][0]
    return parsed.path.rstrip("/").split("/")[-1]


# ── Generic helpers ──────────────────────────────────────────────────────────


def parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def fmt_time(secs: float) -> str:
    secs = max(0, int(secs))
    if secs >= 3600:
        return f"{secs // 3600}h {(secs % 3600) // 60}m {secs % 60}s"
    if secs >= 60:
        return f"{secs // 60}m {secs % 60}s"
    return f"{secs}s"


# ── Auction read/write ───────────────────────────────────────────────────────


def get_auction(session: _requests.Session, handle: str) -> dict:
    if is_uuid(handle):
        r = session.get(
            f"{BW_API_BASE}/api/site/Auctions/by-auction/{handle}", timeout=10
        )
    else:
        r = session.get(f"{BW_API_BASE}/api/site/Auctions/{handle}", timeout=10)
    if r.status_code == 404:
        raise ValueError(f"Auction not found: '{handle}'")
    r.raise_for_status()
    return r.json()


def place_bid(
    session: _requests.Session, auction_id: str, customer_id: str, amount: float
) -> dict:
    r = session.post(
        f"{BW_API_BASE}/api/site/Auctions/{auction_id}/bid",
        json={"auctionId": auction_id, "customerId": customer_id, "amount": amount},
        timeout=10,
    )
    r.raise_for_status()
    if not r.content or not r.content.strip():
        return {}
    try:
        return r.json()
    except Exception:
        return {}


def fetch_won_auctions(session: _requests.Session, customer_id: str) -> list:
    """Paginated list of won auctions."""
    records = []
    page, page_size = 1, 50
    while True:
        r = session.post(
            f"{BW_API_BASE}/api/site/Auctions/my-auctions",
            json={
                "filter": "Won",
                "pageNumber": page,
                "pageSize": page_size,
                "customerId": customer_id,
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        items = data.get("items") or []
        total_pages = data.get("totalPages", 1)
        for a in items:
            item = a.get("item") or {}
            wb = a.get("winningBid") or {}
            loc_obj = a.get("storeLocation") or {}
            store_loc_id = (
                a.get("storeLocationId")
                or loc_obj.get("id")
                or item.get("storeLocationId")
                or ""
            )
            records.append(
                {
                    "title": item.get("title", "Unknown"),
                    "url": f"{BW_SITE_BASE}/auctions/{item.get('handle', '')}",
                    "auction_id": a.get("id", ""),
                    "won_at": a.get("endDate", ""),
                    "final_price": a.get("finalAmount") or wb.get("amount") or 0.0,
                    "my_bid": wb.get("amount") or 0.0,
                    "condition": item.get("condition", ""),
                    "store_location_id": store_loc_id,
                }
            )
        if page >= total_pages:
            break
        page += 1
    return records


def fetch_active_auctions(
    session: _requests.Session,
    page: int = 1,
    page_size: int = BROWSE_PAGE_SIZE,
    sort_by: str = "EndingSoonest",
    search: str = "",
    conditions: list | None = None,
    categories: list | None = None,
    auction_filters: list | None = None,
    store_location_ids: list | None = None,
    min_retail_price: float | None = None,
    max_retail_price: float | None = None,
) -> dict:
    """Browse all active auctions with filters.

    Validates filter values against allowlists to prevent injection attacks.
    """
    # Sanitize filter inputs against allowlists
    if conditions:
        conditions = [c for c in conditions if c in ALLOWED_CONDITIONS]
    if auction_filters:
        auction_filters = [f for f in auction_filters if f in ALLOWED_AUCTION_FILTERS]
    if sort_by not in ALLOWED_SORT:
        log.warning("Invalid sort_by '%s', defaulting to EndingSoonest", sort_by)
        sort_by = "EndingSoonest"

    payload = {
        "pageNumber": page,
        "pageSize": page_size,
        "sortBy": sort_by,
        "search": search or "",
        "conditions": conditions or [],
        "categories": categories or [],  # categories are free-form from BW
        "auctionFilters": auction_filters or [],
        "storeLocationIds": store_location_ids or [],
        "myAuctions": False,
        "winning": False,
        "losing": False,
        "watching": False,
        "additionalCategories": [],
    }
    # Only include price filters if they have valid numeric values
    if min_retail_price is not None:
        payload["minRetailPrice"] = min_retail_price
    if max_retail_price is not None:
        payload["maxRetailPrice"] = max_retail_price
    r = session.post(
        f"{BW_API_BASE}/api/site/Auctions/search",
        json=payload,
        timeout=15,
    )
    if not r.ok:
        body = r.text[:300].strip()
        raise _requests.HTTPError(f"{r.status_code} {r.reason} — {body}", response=r)
    return r.json()


def fetch_store_locations(session: _requests.Session) -> list:
    r = session.get(f"{BW_API_BASE}/api/site/StoreLocations", timeout=10)
    r.raise_for_status()
    return r.json()


# ── Cart / checkout / appointments ───────────────────────────────────────────


def fetch_cart_and_visits(
    session: _requests.Session, customer_id: str, store_location_id: str
) -> dict:
    r = session.post(
        f"{BW_API_BASE}/api/site/customers/paidItemsAndVisit",
        json={"storeLocationId": store_location_id, "customerId": customer_id},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def fetch_reserved_auctions(session: _requests.Session, customer_id: str) -> list:
    r = session.post(
        f"{BW_API_BASE}/api/site/Auctions/my-auctions",
        json={
            "filter": "Reserved",
            "pageNumber": 1,
            "pageSize": 500,
            "customerId": customer_id,
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("items") or []


def fetch_payment_methods(session: _requests.Session) -> list:
    r = session.get(f"{BW_API_BASE}/api/site/Customers/payment-methods", timeout=10)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, list):
        return data
    return data.get("value") or []


def fetch_open_slots(
    session: _requests.Session, location_id: str, day_iso: str, customer_id: str = ""
) -> list:
    params = {"Day": day_iso, "LocationId": location_id}
    if customer_id:
        params["CustomerId"] = customer_id
    r = session.get(
        f"{BW_API_BASE}/api/site/Visits/openslots",
        params=params,
        timeout=10,
    )
    r.raise_for_status()
    return r.json().get("slots") or []


def fetch_removal_status(session: _requests.Session, store_location_id: str) -> dict:
    r = session.get(
        f"{BW_API_BASE}/api/site/Customers/{store_location_id}/checkAuctionRemovalStatus",
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def _extract_stripe_pm_id(payment_methods: list | None) -> Optional[str]:
    """Return the first Stripe payment method ID (pm_...) from a BW methods list."""
    for pm in payment_methods or []:
        for field in ("stripePaymentMethodId", "paymentMethodId", "id"):
            v = pm.get(field, "")
            if isinstance(v, str) and v.startswith("pm_"):
                return v
    return None


# Module-level cache so we only fetch once per process lifetime.
_stripe_pk_cache: Optional[str] = None
_STRIPE_PK_RE = re.compile(r"(pk_live_[A-Za-z0-9]{20,})")


def fetch_stripe_publishable_key(session: _requests.Session) -> Optional[str]:
    """Auto-discover BuyWander's Stripe publishable key.

    BuyWander embeds the Stripe publishable key (``pk_live_...``) in several
    places accessible via the authenticated session:

    1. A BuyWander config API endpoint (tried first — fast, reliable).
    2. The checkout page HTML / inline scripts (fallback scrape).

    The result is cached at module level so subsequent checkouts are instant.
    """
    global _stripe_pk_cache
    if _stripe_pk_cache:
        return _stripe_pk_cache

    # ── Strategy 1: API config endpoints ────────────────────────────────────
    config_paths = [
        "/api/site/config",
        "/api/site/stripe/config",
        "/api/site/Customers/stripe-config",
        "/api/config",
    ]
    for path in config_paths:
        try:
            r = session.get(f"{BW_API_BASE}{path}", timeout=8)
            if r.ok:
                text = r.text
                m = _STRIPE_PK_RE.search(text)
                if m:
                    _stripe_pk_cache = m.group(1)
                    return _stripe_pk_cache
        except Exception:
            pass

    # ── Strategy 2: scrape the checkout page HTML ────────────────────────────
    # We use the BW site base (not API base) and request the checkout page
    # using the already-authenticated session.  This is the same page the user's
    # browser loads, so no additional authorisation is needed.
    try:
        headers = dict(session.headers)
        headers["Accept"] = (
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        )
        r = session.get(f"{BW_SITE_BASE}/checkout", headers=headers, timeout=12)
        if r.ok:
            m = _STRIPE_PK_RE.search(r.text)
            if m:
                _stripe_pk_cache = m.group(1)
                return _stripe_pk_cache
    except Exception:
        pass

    return None


def _stripe_confirm_pi(
    client_secret: str, payment_method_id: str, publishable_key: str
) -> dict:
    """Confirm a Stripe Payment Intent client-side style (no secret key needed).

    Replicates what Stripe.js does: POST to Stripe's /confirm endpoint
    authenticated by the publishable key, with the client_secret as proof of
    ownership of the PI.

    Raises requests.HTTPError on failure.
    """
    # client_secret format: "pi_XXXXXX_secret_YYYYYY"
    pi_id = client_secret.split("_secret_")[0]
    r = _requests.post(
        f"https://api.stripe.com/v1/payment_intents/{pi_id}/confirm",
        headers={"Authorization": f"Bearer {publishable_key}"},
        data={
            "client_secret": client_secret,
            "payment_method": payment_method_id,
            "return_url": "https://www.buywander.com/checkout",
        },
        timeout=20,
    )
    r.raise_for_status()
    return r.json() if r.content else {}


_BW_CHECKOUT_PAYLOAD_BASE = {
    "pointsToRedeem": 0,
    "confirmFreeOrder": False,
    "savePaymentMethod": True,
    "isFeesOrder": False,
}


def do_pay_checkout(
    session: _requests.Session,
    store_location_id: str,
    payment_methods: list | None = None,
) -> dict:
    """Two-step BuyWander checkout.

    Step 1 — create the Stripe Payment Intent.
    Step 2 — confirm the PI (via Stripe API), then finalise with BW.

    The Stripe publishable key is resolved automatically:
      • STRIPE_PUBLISHABLE_KEY env var (explicit override, highest priority)
      • Auto-discovered from BuyWander's own pages using the authenticated session

    Returns the last BuyWander response dict, which on success contains
    ``orderId`` and ``confirmationNumber``.
    """
    from ..config import STRIPE_PUBLISHABLE_KEY as _cfg_pk

    payload1 = {
        **_BW_CHECKOUT_PAYLOAD_BASE,
        "storeLocationId": store_location_id,
        "paymentIntentRecordId": None,
    }
    r1 = session.post(
        f"{BW_API_BASE}/api/site/Customers/checkout/pay",
        json=payload1,
        timeout=20,
    )
    r1.raise_for_status()
    step1 = r1.json() if r1.content else {}

    # Already complete (free/discounted order or pre-authorised)
    if step1.get("skipPayment") or step1.get("orderId"):
        return step1

    pi_record_id = step1.get("paymentIntentRecordId")
    client_secret = step1.get("clientSecret", "")

    if not pi_record_id:
        # Nothing more we can do — return what BW gave us
        return step1

    # ── Confirm the Stripe PI ────────────────────────────────────────────────
    # BuyWander creates the order via Stripe webhook after the PI is confirmed —
    # there is no second checkout/pay call needed.
    pm_id = _extract_stripe_pm_id(payment_methods)
    # Prefer explicit env var; fall back to auto-discovery via BW session
    stripe_pk = _cfg_pk or (
        fetch_stripe_publishable_key(session) if pm_id and client_secret else None
    )

    if not (stripe_pk and pm_id and client_secret):
        raise RuntimeError(
            "Cannot complete checkout: no saved Stripe payment method found "
            "or Stripe publishable key could not be discovered. "
            "Ensure a payment method is saved in BuyWander."
        )

    stripe_result = _stripe_confirm_pi(client_secret, pm_id, stripe_pk)
    # Redact Stripe keys from logged result to prevent accidental key exposure
    log.warning("Stripe PI confirmed: %s", _redact_stripe_keys(str(stripe_result)))

    # Stripe returns the confirmed PI; merge useful fields back into the BW response
    stripe_status = stripe_result.get("status", "")
    if stripe_status not in ("succeeded", "processing", "requires_capture"):
        raise RuntimeError(
            f"Stripe returned unexpected status '{stripe_status}' after confirmation. "
            "The payment may not have been charged — check your BuyWander account."
        )

    # Return the BW step-1 payload augmented with a synthetic success marker so
    # callers know the charge went through (BW will create the order via webhook).
    return {
        **step1,
        "stripeStatus": stripe_status,
        "chargeConfirmed": True,
    }


def _to_utc_z(iso: str) -> str:
    """Convert any ISO datetime string to UTC ending in Z."""
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass
    return iso


def _parse_api_error(r: _requests.Response) -> str:
    """Extract a human-readable error message from a failed BW API response."""
    raw = r.text[:400] if r.text else ""
    try:
        body = r.json()
        if isinstance(body, str):
            return body
        if isinstance(body, dict):
            return (
                body.get("message")
                or body.get("title")
                or body.get("detail")
                or body.get("error")
                or str(body)
            )
    except Exception:
        pass
    return raw or f"HTTP {r.status_code}"


def do_create_appointment(
    session: _requests.Session, location_id: str, slot_date_iso: str
) -> dict:
    # BuyWander Visits/create uses query params, not a JSON body
    r = session.post(
        f"{BW_API_BASE}/api/site/Visits/create",
        params={
            "VisitDate": _to_utc_z(slot_date_iso),
            "StoreLocationId": location_id,
            "IsCancelled": "false",
        },
        timeout=15,
    )
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code}: {_parse_api_error(r)}")
    return r.json() if r.content else {}


def _update_visit(
    session: _requests.Session, visit_id: str, date_iso: str, cancelled: bool
) -> dict:
    r = session.post(
        f"{BW_API_BASE}/api/site/Visits/update",
        params={
            "VisitId": visit_id,
            "VisitDate": _to_utc_z(date_iso),
            "IsCancelled": "true" if cancelled else "false",
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json() if r.content else {}


def do_cancel_appointment(
    session: _requests.Session, visit_id: str, visit_date_iso: str
) -> dict:
    return _update_visit(session, visit_id, visit_date_iso, cancelled=True)


def do_reschedule_appointment(
    session: _requests.Session, visit_id: str, new_date_iso: str
) -> dict:
    return _update_visit(session, visit_id, new_date_iso, cancelled=False)


def do_remove_from_cart(
    session: _requests.Session,
    auction_id: str,
    reason: str = "ChangedMind",
    notes: str = "No reason provided",
) -> bool:
    r = session.post(
        f"{BW_API_BASE}/api/site/Auctions/removeItemFromCart",
        json={"auctionId": auction_id, "removeReason": reason, "notes": notes},
        timeout=15,
    )
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code}: {_parse_api_error(r)}")
    return True
