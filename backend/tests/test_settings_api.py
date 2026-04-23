import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.api.settings as settings_module
from app.db.schemas import DefaultSettings, SettingsUpdate


class FakeDb:
    def commit(self):
        return None

    def refresh(self, _obj):
        return None


def test_update_settings_accepts_matching_version_without_timezone_suffix(
    monkeypatch,
):
    updated_at = datetime(2026, 4, 22, 12, 34, 56, tzinfo=timezone.utc)
    cfg = SimpleNamespace(
        config_json=json.dumps(settings_module._DEFAULT_CONFIG),
        updated_at=updated_at,
    )
    user = SimpleNamespace(id="user-1")

    monkeypatch.setattr(settings_module, "_get_or_create_config", lambda *_args: cfg)
    monkeypatch.setattr(settings_module, "encrypt_notifications", lambda value: value)
    monkeypatch.setattr(settings_module, "decrypt_notifications", lambda value: value)

    result = settings_module.update_settings(
        SettingsUpdate(
            defaults=DefaultSettings(snipe_seconds=9),
            version="2026-04-22T12:34:56",
        ),
        user=user,
        db=FakeDb(),
    )

    assert result.defaults.snipe_seconds == 9


def test_update_settings_rejects_stale_version(monkeypatch):
    updated_at = datetime(2026, 4, 22, 12, 34, 56, tzinfo=timezone.utc)
    cfg = SimpleNamespace(
        config_json=json.dumps(settings_module._DEFAULT_CONFIG),
        updated_at=updated_at,
    )
    user = SimpleNamespace(id="user-1")

    monkeypatch.setattr(settings_module, "_get_or_create_config", lambda *_args: cfg)

    with pytest.raises(HTTPException) as exc:
        settings_module.update_settings(
            SettingsUpdate(
                defaults=DefaultSettings(snipe_seconds=9),
                version=(updated_at - timedelta(seconds=1)).isoformat(),
            ),
            user=user,
            db=FakeDb(),
        )

    assert exc.value.status_code == 409
