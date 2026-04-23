from types import SimpleNamespace

from app.services.auction_worker import AuctionWorker


def test_notify_if_bid_limit_exceeded_sends_once():
    notifications = []
    updates = []
    logs = []
    worker = AuctionWorker(
        snipe_id="snipe-1",
        login_id="login-1",
        user_id="user-1",
        bw_session=SimpleNamespace(),
        customer_id="customer-1",
        handle="auction-handle",
        bid_amount=25.0,
        snipe_seconds=5,
        notification_fn=lambda **kwargs: notifications.append(kwargs),
    )
    worker._update_snipe = lambda **fields: updates.append(fields)
    worker._log_event = lambda message, event_type="info", auction_id=None: logs.append(
        (message, event_type, auction_id)
    )

    worker._notify_if_bid_limit_exceeded("Auction title", 31.0, is_me=False)
    worker._notify_if_bid_limit_exceeded("Auction title", 35.0, is_me=False)

    assert updates == [{"max_bid_exceeded_notified": True}]
    assert len(notifications) == 1
    assert notifications[0]["event_type"] == "max_bid_exceeded"
    assert notifications[0]["title"] == "Auction title"
    assert notifications[0]["bid_amount"] == 25.0
    assert notifications[0]["current_bid"] == 31.0
    assert logs
    assert "exceeded your snipe max" in logs[0][0]


def test_notify_if_bid_limit_exceeded_skips_when_user_is_winning():
    notifications = []
    updates = []
    worker = AuctionWorker(
        snipe_id="snipe-1",
        login_id="login-1",
        user_id="user-1",
        bw_session=SimpleNamespace(),
        customer_id="customer-1",
        handle="auction-handle",
        bid_amount=25.0,
        snipe_seconds=5,
        notification_fn=lambda **kwargs: notifications.append(kwargs),
    )
    worker._update_snipe = lambda **fields: updates.append(fields)
    worker._log_event = lambda *_args, **_kwargs: None

    worker._notify_if_bid_limit_exceeded("Auction title", 31.0, is_me=True)

    assert notifications == []
    assert updates == []
    assert worker.max_bid_exceeded_notified is False
