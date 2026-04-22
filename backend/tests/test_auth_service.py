from types import SimpleNamespace

import pytest
from cryptography.fernet import InvalidToken
from fastapi import HTTPException

import app.api.cart as cart_module
import app.services.auth_service as auth_service
import app.utils.crypto as crypto


def test_reauth_bw_login_raises_actionable_error_for_undecryptable_password(
    monkeypatch,
):
    login = SimpleNamespace(
        encrypted_password="not-decryptable",
        bw_email="buywonder@example.com",
    )
    db = SimpleNamespace()

    monkeypatch.setattr(
        crypto,
        "decrypt",
        lambda _value: (_ for _ in ()).throw(InvalidToken()),
    )

    with pytest.raises(auth_service.BuyWanderCredentialDecryptError) as exc:
        auth_service.reauth_bw_login(login, db)

    assert "Update this login's password" in str(exc.value)


def test_cart_resolve_returns_409_for_undecryptable_stored_credentials(monkeypatch):
    user = SimpleNamespace(id="user-1")
    login = SimpleNamespace(
        id="login-1",
        user_id=user.id,
        bw_email="buywonder@example.com",
        encrypted_cookies="cookies",
    )

    class FakeQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return login

    class FakeDb:
        def query(self, _model):
            return FakeQuery()

    monkeypatch.setattr(cart_module, "create_bw_session", lambda _cookies: object())
    monkeypatch.setattr(cart_module, "validate_session", lambda _session: False)
    monkeypatch.setattr(
        cart_module,
        "reauth_bw_login",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            auth_service.BuyWanderCredentialDecryptError(
                "Stored BuyWander credentials can no longer be decrypted. "
                "Update this login's password to continue."
            )
        ),
    )

    with pytest.raises(HTTPException) as exc:
        cart_module._resolve(FakeDb(), user, login.id)

    assert exc.value.status_code == 409
    assert "Update this login's password" in exc.value.detail
