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
