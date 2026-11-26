import json
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import Mock

import app.services.keyword_watcher as watcher


def test_keyword_scan_consumes_normalized_search_items_and_deduplicates(monkeypatch):
    login = SimpleNamespace(user_id="user-1", encrypted_cookies="cookies")
    config = {"notifications": {"keyword_watches": ["camera"]}}
    query = Mock()
    query.join.return_value = query
    query.filter.return_value = query
    query.all.return_value = [(login, SimpleNamespace(config_json=json.dumps(config)))]
    db = SimpleNamespace(query=lambda *_args: query, close=Mock())
    notify = Mock()
    monkeypatch.setattr(watcher, "SessionLocal", lambda: db)
    monkeypatch.setattr(watcher, "create_bw_session", lambda _cookies: object())
    monkeypatch.setattr(watcher, "_seen", defaultdict(dict))
    monkeypatch.setattr(
        watcher,
        "fetch_active_auctions",
        lambda *_args, **_kwargs: {
            "items": [
                {
                    "id": "auction-1",
                    "item": {"title": "Camera", "handle": None},
                    "winningBid": {"amount": 3},
                }
            ],
        },
    )
    monkeypatch.setattr(watcher.notification_service, "notify_keyword_match", notify)

    watcher._scan_once()
    watcher._scan_once()

    notify.assert_called_once_with(
        config,
        "camera",
        "Camera",
        3,
        "https://www.buywander.com/auctions?auctionId=auction-1",
    )
    assert db.close.call_count == 2
