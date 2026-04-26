from types import SimpleNamespace

import pytest
import requests

from app.services.buywander_api import fetch_active_auctions, fetch_cart_and_visits


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
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
        json=lambda: payload if payload is not None else {},
        raise_for_status=raise_for_status,
    )


def test_fetch_active_auctions_normalizes_legacy_newly_listed_sort_alias():
    session = FakeSession([make_response(200, payload={"auctions": [{"id": "auction-1"}]})])

    result = fetch_active_auctions(session, sort_by="NewlyListed", search="ssd")

    assert result == {"auctions": [{"id": "auction-1"}]}
    assert len(session.calls) == 1
    assert session.calls[0]["json"]["sortBy"] == "NewArrivals"


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
