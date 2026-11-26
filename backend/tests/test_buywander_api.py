import json
from types import SimpleNamespace

import pytest
import requests

from app.services.buywander_api import (
    auction_url,
    bw_login,
    do_cancel_appointment,
    do_create_appointment,
    do_pay_checkout,
    do_remove_from_cart,
    do_reschedule_appointment,
    fetch_active_auctions,
    fetch_cart_and_visits,
    place_bid,
    validate_session,
)


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def post(self, url, json=None, timeout=None, params=None):
        call = {"url": url, "timeout": timeout}
        if json is not None:
            call["json"] = json
        if params is not None:
            call["params"] = params
        self.calls.append(call)
        return self._responses.pop(0)

    def get(self, url, timeout):
        self.calls.append({"url": url, "timeout": timeout})
        return self._responses.pop(0)


def make_response(status_code, payload=None, body=""):
    ok = 200 <= status_code < 300

    def raise_for_status():
        if not ok:
            raise requests.HTTPError(f"{status_code} Bad Request")

    return SimpleNamespace(
        ok=ok,
        status_code=status_code,
        reason="OK" if ok else "Bad Request",
        text=body,
        content=json.dumps(payload).encode() if payload is not None else body.encode(),
        json=lambda: payload if payload is not None else {},
        raise_for_status=raise_for_status,
    )


def test_bw_login_uses_current_versioned_auth_endpoint():
    session = FakeSession([make_response(200, payload={"isSuccess": True})])

    result = bw_login(session, "user@example.com", "password")

    assert result == {"isSuccess": True}
    assert session.calls == [
        {
            "url": "https://bwapi.buywander.com/api/site/v1/ShopifyAuth/login",
            "json": {"email": "user@example.com", "password": "password"},
            "timeout": 10,
        }
    ]


def test_validate_session_uses_current_versioned_customer_endpoint():
    customer = {"id": "customer-1", "displayName": "Test User"}
    session = FakeSession([make_response(200, payload=customer)])

    result = validate_session(session)

    assert result == customer
    assert session.calls == [
        {
            "url": "https://bwapi.buywander.com/api/site/v1/Customers/me",
            "timeout": 8,
        }
    ]


def test_fetch_active_auctions_normalizes_legacy_newly_listed_sort_alias():
    session = FakeSession(
        [make_response(200, payload={"auctions": [{"id": "auction-1"}]})]
    )

    result = fetch_active_auctions(session, sort_by="NewlyListed", search="ssd")

    assert result == {"auctions": [{"id": "auction-1"}]}
    assert len(session.calls) == 1
    assert session.calls[0]["json"]["sortBy"] == "NewArrivals"


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        ("LowestBid", "CurrentPriceLowest"),
        ("HighestBid", "CurrentPriceHighest"),
        ("MostBids", "BidsHighest"),
        ("LowestRetail", "RetailPriceLowest"),
        ("HighestRetail", "RetailPriceHighest"),
    ],
)
def test_search_translates_existing_sort_choices(sort, expected):
    session = FakeSession([make_response(200, payload={"items": []})])
    fetch_active_auctions(session, sort_by=sort)
    assert session.calls[0]["json"]["sortBy"] == expected


def test_search_unwraps_auctions_and_round_trips_structured_cursor():
    cursor = {
        "searchType": "Auctions",
        "auctions": [1795309200000, "auction-24"],
        "comingSoon": None,
        "buyNow": None,
        "auctionsTotal": 100,
    }
    auction = {"id": "auction-25", "item": {"title": "Item", "handle": None}}
    session = FakeSession(
        [
            make_response(
                200,
                payload={
                    "items": [
                        {"type": "Auction", "auction": auction},
                        {
                            "type": "ComingSoon",
                            "auction": None,
                            "comingSoon": {"id": "future-1"},
                        },
                    ],
                    "cursor": cursor,
                    "totalCount": 100,
                },
            )
        ]
    )

    result = fetch_active_auctions(session, cursor=cursor)

    assert session.calls[0]["json"]["cursor"] == cursor
    assert session.calls[0]["json"]["includeBuyNow"] is False
    assert result["items"] == [auction]
    assert result["cursor"] == cursor
    assert result["hasNextPage"] is True
    assert result["totalCount"] == 100


def test_search_stops_when_current_api_returns_no_cursor():
    session = FakeSession([make_response(200, payload={"items": [], "cursor": None})])
    assert fetch_active_auctions(session)["hasNextPage"] is False


def test_search_preserves_flat_my_auctions_results():
    payload = {"items": [{"id": "auction-1"}], "hasNextPage": True, "totalPages": 2}
    session = FakeSession([make_response(200, payload=payload)])
    assert fetch_active_auctions(session, watching=True) == payload


def test_search_request_validates_structured_cursor():
    from pydantic import ValidationError
    from app.db.schemas import AuctionSearchParams

    cursor = {
        "searchType": "Auctions",
        "auctions": [123, "auction-24"],
        "auctionsTotal": 100,
    }
    params = AuctionSearchParams(login_id="login-1", cursor=cursor)
    assert params.cursor == cursor
    with pytest.raises(ValidationError):
        AuctionSearchParams(login_id="login-1", cursor={"searchType": "x" * 4096})


def test_search_route_forwards_cursor_and_normalizes_results(monkeypatch):
    import app.api.auctions as routes
    from app.db.schemas import AuctionSearchParams

    cursor = {"searchType": "Auctions", "auctions": [123, "auction-24"]}
    auction = {"id": "auction-25", "item": {"title": "Camera"}}
    session = FakeSession(
        [
            make_response(
                200,
                payload={
                    "items": [{"type": "Auction", "auction": auction}],
                    "cursor": None,
                },
            )
        ]
    )
    monkeypatch.setattr(
        routes,
        "_get_bw_session",
        lambda *_args: (
            session,
            SimpleNamespace(customer_id="customer-1"),
        ),
    )

    result = routes.search_auctions(
        AuctionSearchParams(login_id="login-1", cursor=cursor, sort_by="LowestBid"),
        user=SimpleNamespace(id="user-1"),
        db=SimpleNamespace(),
    )

    assert result["items"] == [auction]
    assert result["hasNextPage"] is False
    assert session.calls[0]["json"]["cursor"] == cursor
    assert session.calls[0]["json"]["sortBy"] == "CurrentPriceLowest"


def test_login_handles_email_verification_response():
    session = FakeSession(
        [
            make_response(
                200, payload={"isSuccess": False, "requireEmailVerification": True}
            )
        ]
    )
    with pytest.raises(ValueError, match="email not verified"):
        bw_login(session, "user@example.com", "password")


def test_auction_url_works_without_legacy_handle():
    url = auction_url({"id": "auction-1", "item": {"handle": None}})
    assert url == "https://www.buywander.com/auctions?auctionId=auction-1"


@pytest.mark.parametrize(
    ("action", "path", "body"),
    [
        (
            lambda session: place_bid(session, "auction-1", "customer-1", 12.5),
            "/Auctions/auction-1/bid",
            {
                "json": {
                    "auctionId": "auction-1",
                    "customerId": "customer-1",
                    "amount": 12.5,
                }
            },
        ),
        (
            lambda session: do_create_appointment(
                session, "store-1", "2026-12-01T12:00:00+00:00"
            ),
            "/Visits/create",
            {
                "params": {
                    "VisitDate": "2026-12-01T12:00:00Z",
                    "StoreLocationId": "store-1",
                    "IsCancelled": "false",
                }
            },
        ),
        (
            lambda session: do_reschedule_appointment(
                session, "visit-1", "2026-12-01T12:00:00+00:00"
            ),
            "/Visits/update",
            {
                "params": {
                    "VisitId": "visit-1",
                    "VisitDate": "2026-12-01T12:00:00Z",
                    "IsCancelled": "false",
                }
            },
        ),
        (
            lambda session: do_cancel_appointment(
                session, "visit-1", "2026-12-01T12:00:00+00:00"
            ),
            "/Visits/update",
            {
                "params": {
                    "VisitId": "visit-1",
                    "VisitDate": "2026-12-01T12:00:00Z",
                    "IsCancelled": "true",
                }
            },
        ),
        (
            lambda session: do_remove_from_cart(session, "auction-1"),
            "/Auctions/removeItemFromCart",
            {
                "json": {
                    "auctionId": "auction-1",
                    "removeReason": "ChangedMind",
                    "notes": "No reason provided",
                }
            },
        ),
    ],
)
def test_transaction_contracts_without_live_mutations(action, path, body):
    session = FakeSession([make_response(200, payload={})])
    action(session)
    assert len(session.calls) == 1
    assert session.calls[0]["url"] == f"https://bwapi.buywander.com/api/site/v1{path}"
    for key, expected in body.items():
        assert session.calls[0][key] == expected


def test_free_checkout_requires_explicit_order_confirmation():
    session = FakeSession(
        [
            make_response(
                200, payload={"skipPayment": True, "paymentIntentRecordId": "intent-1"}
            ),
            make_response(200, payload={"orderId": "order-1"}),
        ]
    )

    assert do_pay_checkout(session, "store-1") == {"orderId": "order-1"}
    assert session.calls[0]["json"]["confirmFreeOrder"] is False
    assert session.calls[1]["json"] == {
        "storeLocationId": "store-1",
        "pointsToRedeem": 0,
        "confirmFreeOrder": True,
        "paymentIntentRecordId": "intent-1",
        "savePaymentMethod": False,
        "isFeesOrder": False,
    }


def test_free_checkout_does_not_report_success_without_confirmed_order():
    session = FakeSession(
        [
            make_response(200, payload={"skipPayment": True}),
            make_response(200, payload={}),
        ]
    )
    with pytest.raises(RuntimeError, match="did not confirm"):
        do_pay_checkout(session, "store-1")


def test_paid_checkout_confirms_using_saved_method_without_charging(monkeypatch):
    import app.config as config
    import app.services.buywander_api as api
    from unittest.mock import Mock

    session = FakeSession(
        [
            make_response(
                200,
                payload={
                    "paymentIntentRecordId": "intent-1",
                    "clientSecret": "mock-client-secret",
                },
            )
        ]
    )
    confirm = Mock(return_value={"status": "succeeded"})
    monkeypatch.setattr(config, "STRIPE_PUBLISHABLE_KEY", "mock-publishable-key")
    monkeypatch.setattr(api, "_stripe_confirm_pi", confirm)

    result = do_pay_checkout(session, "store-1", [{"id": "pm_mock"}])

    assert result["chargeConfirmed"] is True
    confirm.assert_called_once_with(
        "mock-client-secret", "pm_mock", "mock-publishable-key"
    )


def test_fetch_active_auctions_sends_v1_search_cursor_for_next_page():
    session = FakeSession([make_response(200, payload={"items": []})])
    search_after = [1788220800000, "auction-24"]

    fetch_active_auctions(
        session,
        page=2,
        search_after=search_after,
        search_id="search-session-1",
    )

    assert session.calls[0]["json"]["searchAfter"] == search_after
    assert session.calls[0]["json"]["searchId"] == "search-session-1"


def test_fetch_active_auctions_sends_supported_v1_filter():
    session = FakeSession([make_response(200, payload={"items": []})])

    fetch_active_auctions(session, auction_filter="EndsTomorrow")

    assert session.calls[0]["json"]["filter"] == "EndsTomorrow"
    assert "auctionFilters" not in session.calls[0]["json"]


def test_fetch_active_auctions_uses_my_auctions_for_watched_items():
    session = FakeSession([make_response(200, payload={"items": []})])

    fetch_active_auctions(
        session,
        watching=True,
        customer_id="customer-1",
    )

    assert session.calls[0]["url"].endswith("/Auctions/my-auctions")
    assert session.calls[0]["json"]["filter"] == "Watching"
    assert session.calls[0]["json"]["customerId"] == "customer-1"


def test_fetch_active_auctions_retries_new_arrivals_with_fallback_sort():
    session = FakeSession(
        [
            make_response(400, body=""),
            make_response(200, payload={"auctions": [{"id": "auction-1"}]}),
        ]
    )

    result = fetch_active_auctions(session, sort_by="NewArrivals", search="ssd")

    assert result == {"auctions": [{"id": "auction-1"}]}
    assert len(session.calls) == 2
    assert session.calls[0]["json"]["sortBy"] == "NewArrivals"
    assert session.calls[1]["json"]["sortBy"] == "EndingSoonest"


def test_fetch_active_auctions_raises_when_fallback_sort_also_fails():
    session = FakeSession(
        [
            make_response(400, body=""),
            make_response(400, body="still bad"),
        ]
    )

    with pytest.raises(requests.HTTPError) as exc:
        fetch_active_auctions(session, sort_by="NewArrivals", search="ssd")

    assert "400 Bad Request" in str(exc.value)
    assert len(session.calls) == 2


def test_fetch_cart_and_visits_filters_items_already_attached_to_visits():
    session = FakeSession(
        [
            make_response(
                200,
                payload={
                    "visits": [
                        {"id": "booked-visit", "status": "Booked"},
                        {"id": "complete-visit", "status": "Complete"},
                        {"id": "rescheduled-visit", "status": "ReScheduled"},
                    ],
                    "paidItems": [
                        {"id": "unscheduled", "visitId": None},
                        {"id": "scheduled", "visitId": "booked-visit"},
                        {"id": "picked-up", "visitId": "complete-visit"},
                        {"id": "needs-new-visit", "visitId": "rescheduled-visit"},
                    ],
                },
            )
        ]
    )

    result = fetch_cart_and_visits(session, "customer-1", "store-1")

    assert session.calls[0]["json"] == {
        "storeLocationId": "store-1",
        "customerId": "customer-1",
        "showCancelled": False,
        "showCompleted": True,
        "showRescheduled": False,
    }
    assert [item["id"] for item in result["paidItems"]] == [
        "unscheduled",
        "needs-new-visit",
    ]
    assert [visit["id"] for visit in result["visits"]] == [
        "booked-visit",
        "complete-visit",
    ]
