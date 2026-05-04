from datetime import datetime, timezone
from types import SimpleNamespace

import app.api.watchlist as watchlist_module


def test_watchlist_response_includes_cached_snapshot():
    item = SimpleNamespace(
        id="watch-1",
        user_id="user-1",
        login_id="login-1",
        handle="auction-handle",
        auction_id="auction-1",
        url="https://www.buywander.com/auctions/auction-handle",
        title="Cached title",
        notes=None,
        snapshot_json='{"id": "auction-1", "item": {"title": "Cached title"}}',
        created_at=datetime(2026, 4, 25, tzinfo=timezone.utc),
    )

    result = watchlist_module._watchlist_response(item)

    assert result["auction_id"] == "auction-1"
    assert result["snapshot"]["item"]["title"] == "Cached title"
