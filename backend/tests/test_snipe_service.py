from types import SimpleNamespace

import app.services.snipe_service as snipe_service


def test_restart_active_snipes_attaches_notification_fn(monkeypatch):
    login = SimpleNamespace(
        id="login-1",
        user_id="user-1",
        is_active=True,
        customer_id="customer-1",
        bw_email="buywonder@example.com",
        encrypted_password="secret",
        encrypted_cookies="cookies",
    )
    snipe = SimpleNamespace(
        id="snipe-1",
        login_id=login.id,
        login=login,
        handle="auction-handle",
        url="https://www.buywander.com/auctions/auction-handle",
        bid_amount=12.5,
        snipe_seconds=5,
        max_bid_exceeded_notified=False,
    )

    class FakeQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def all(self):
            return [snipe]

    class FakeDb:
        def query(self, _model):
            return FakeQuery()

    created_workers = []

    class FakeWorker:
        def __init__(self, **kwargs):
            created_workers.append(kwargs)

    monkeypatch.setattr(snipe_service, "_get_bw_session", lambda _login: object())
    monkeypatch.setattr(snipe_service, "AuctionWorker", FakeWorker)
    monkeypatch.setattr(snipe_service.pool, "spawn", lambda *_args, **_kwargs: True)

    snipe_service.restart_active_snipes(FakeDb(), ws_manager=object())

    assert created_workers
    assert callable(created_workers[0]["notification_fn"])
    assert created_workers[0]["max_bid_exceeded_notified"] is False


def test_build_notification_fn_sends_max_bid_exceeded(monkeypatch):
    calls = []

    class FakeQuery:
        def __init__(self, result):
            self.result = result

        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return self.result

    class FakeDb:
        def query(self, model):
            if model is snipe_service.UserConfig:
                return FakeQuery(SimpleNamespace(config_json='{"notifications": {}}'))
            if model is snipe_service.Snipe:
                return FakeQuery(SimpleNamespace(notify=None))
            raise AssertionError(f"Unexpected model {model}")

        def close(self):
            return None

    monkeypatch.setattr(snipe_service, "SessionLocal", lambda: FakeDb())
    monkeypatch.setattr(
        snipe_service.notification_service,
        "notify_max_bid_exceeded",
        lambda cfg, title, bid_amount, current_bid: calls.append(
            (cfg, title, bid_amount, current_bid)
        ),
    )

    fn = snipe_service.build_notification_fn("user-1", "snipe-1")
    fn(
        event_type="max_bid_exceeded",
        title="Test auction",
        bid_amount=25.0,
        current_bid=31.0,
    )

    assert calls == [({"notifications": {}}, "Test auction", 25.0, 31.0)]


def test_update_snipe_resets_max_bid_exceeded_notification(monkeypatch):
    snipe = SimpleNamespace(
        id="snipe-1",
        status=snipe_service.SnipeStatus.WATCHING,
        bid_amount=10.0,
        snipe_seconds=5,
        notify=None,
        max_bid_exceeded_notified=True,
    )

    class FakeQuery:
        def join(self, *_args, **_kwargs):
            return self

        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return snipe

    class FakeDb:
        def __init__(self):
            self.committed = False
            self.refreshed = False

        def query(self, _model):
            return FakeQuery()

        def commit(self):
            self.committed = True

        def refresh(self, obj):
            self.refreshed = True
            assert obj is snipe

    worker = SimpleNamespace(
        bid_amount=10.0,
        snipe_seconds=5,
        max_bid_exceeded_notified=True,
        is_alive=lambda: True,
    )
    db = FakeDb()

    monkeypatch.setattr(snipe_service.pool, "get", lambda _snipe_id: worker)

    updated = snipe_service.update_snipe(
        db,
        "user-1",
        "snipe-1",
        update_data={"bid_amount": 22.0},
    )

    assert updated is snipe
    assert snipe.bid_amount == 22.0
    assert snipe.max_bid_exceeded_notified is False
    assert worker.bid_amount == 22.0
    assert worker.max_bid_exceeded_notified is False
    assert db.committed is True
    assert db.refreshed is True
