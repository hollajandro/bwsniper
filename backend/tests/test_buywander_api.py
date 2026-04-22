from types import SimpleNamespace

import pytest
import requests

from app.services.buywander_api import fetch_active_auctions


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return self._responses.pop(0)


def make_response(status_code, payload=None, body=""):
    ok = 200 <= status_code < 300
    return SimpleNamespace(
        ok=ok,
        status_code=status_code,
        reason="OK" if ok else "Bad Request",
        text=body,
        json=lambda: payload if payload is not None else {},
    )


def test_fetch_active_auctions_retries_newly_listed_with_fallback_sort():
    session = FakeSession(
        [
            make_response(400, body=""),
            make_response(200, payload={"auctions": [{"id": "auction-1"}]}),
        ]
    )

    result = fetch_active_auctions(session, sort_by="NewlyListed", search="ssd")

    assert result == {"auctions": [{"id": "auction-1"}]}
    assert len(session.calls) == 2
    assert session.calls[0]["json"]["sortBy"] == "NewlyListed"
    assert session.calls[1]["json"]["sortBy"] == "EndingSoonest"


def test_fetch_active_auctions_raises_when_fallback_sort_also_fails():
    session = FakeSession(
        [
            make_response(400, body=""),
            make_response(400, body="still bad"),
        ]
    )

    with pytest.raises(requests.HTTPError) as exc:
        fetch_active_auctions(session, sort_by="NewlyListed", search="ssd")

    assert "400 Bad Request" in str(exc.value)
    assert len(session.calls) == 2
