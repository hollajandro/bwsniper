from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from fastapi import HTTPException

import app.api.auctions as routes
from app.db.schemas import AuctionSearchParams
from app.services.auth_service import BuyWanderCredentialDecryptError


def upstream_error(status):
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(response=response)


def setup_search(monkeypatch, outcomes):
    old_session = object()
    login = SimpleNamespace(customer_id="customer-1")
    fetch = Mock(side_effect=outcomes)
    refresh = Mock(return_value=object())
    monkeypatch.setattr(routes, "_get_bw_session", lambda *_args: (old_session, login))
    monkeypatch.setattr(routes, "fetch_active_auctions", fetch)
    monkeypatch.setattr(routes, "reauth_bw_login", refresh)
    return old_session, login, fetch, refresh


def search():
    return routes.search_auctions(
        AuctionSearchParams(login_id="login-1", watching=True),
        user=SimpleNamespace(id="user-1"),
        db=SimpleNamespace(),
    )


def test_watched_search_refreshes_expired_session_and_retries_once(monkeypatch):
    expected = {"items": [{"id": "watched-1"}], "hasNextPage": False}
    old_session, login, fetch, refresh = setup_search(
        monkeypatch, [upstream_error(401), expected]
    )

    assert search() == expected
    assert refresh.call_count == 1
    assert refresh.call_args.args[0] is login
    assert fetch.call_count == 2
    assert fetch.call_args_list[0].args[0] is old_session
    assert fetch.call_args_list[1].args[0] is refresh.return_value
    assert fetch.call_args_list[0].kwargs == fetch.call_args_list[1].kwargs
    assert fetch.call_args.kwargs["watching"] is True


@pytest.mark.parametrize("status", [400, 403, 500])
def test_search_does_not_refresh_for_other_upstream_errors(monkeypatch, status):
    _, _, fetch, refresh = setup_search(monkeypatch, [upstream_error(status)])

    with pytest.raises(HTTPException) as error:
        search()

    assert error.value.status_code == 502
    refresh.assert_not_called()
    assert fetch.call_count == 1


def test_search_does_not_loop_if_refreshed_session_is_rejected(monkeypatch):
    _, _, fetch, refresh = setup_search(
        monkeypatch, [upstream_error(401), upstream_error(401)]
    )

    with pytest.raises(HTTPException) as error:
        search()

    assert error.value.status_code == 502
    assert refresh.call_count == 1
    assert fetch.call_count == 2


def test_search_reports_when_stored_credentials_need_updating(monkeypatch):
    _, _, _, refresh = setup_search(monkeypatch, [upstream_error(401)])
    refresh.side_effect = BuyWanderCredentialDecryptError(
        "Update this login's password to continue."
    )

    with pytest.raises(HTTPException) as error:
        search()

    assert error.value.status_code == 409
    assert "Update this login's password" in error.value.detail
