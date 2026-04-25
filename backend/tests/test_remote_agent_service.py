import sys
import os
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from types import SimpleNamespace

from app.db.models import SnipeStatus
from app.db.schemas import RemoteAgentEventCreate, RemoteAgentSyncRequest, RemoteAgentWorkerReport
from app.services import remote_agent_service

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.append(str(AGENT_ROOT))

os.environ.setdefault("MAIN_BACKEND_URL", "http://backend.test")
os.environ.setdefault("AGENT_ID", "agent-test")
os.environ.setdefault("AGENT_API_KEY", "agent-key")

from remote_agent.manager import RemoteAgentManager  # noqa: E402


def test_authenticate_remote_agent_accepts_valid_key():
    raw_key = "secret-key"
    agent = SimpleNamespace(api_key_hash=remote_agent_service.hash_api_key(raw_key))

    class FakeQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return agent

    class FakeDb:
        def query(self, _model):
            return FakeQuery()

    assert (
        remote_agent_service.authenticate_remote_agent(FakeDb(), "agent-1", raw_key)
        is agent
    )


def test_authenticate_remote_agent_rejects_invalid_key():
    agent = SimpleNamespace(api_key_hash=remote_agent_service.hash_api_key("good-key"))

    class FakeQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return agent

    class FakeDb:
        def query(self, _model):
            return FakeQuery()

    assert (
        remote_agent_service.authenticate_remote_agent(
            FakeDb(), "agent-1", "bad-key"
        )
        is None
    )


def test_record_remote_agent_event_promotes_sniped_status(monkeypatch):
    snipe = SimpleNamespace(
        id="snipe-1",
        login_id="login-1",
        login=SimpleNamespace(user_id="user-1"),
        status=SnipeStatus.WATCHING,
        bid_placed=False,
        fired_at=None,
        ended_at=None,
        error_msg="old error",
        bid_amount=42.0,
    )
    state = SimpleNamespace(
        status=None,
        last_error=None,
        last_heartbeat_at=None,
        fired_at=None,
        ended_at=None,
    )
    added = []
    broadcasts = []

    monkeypatch.setattr(remote_agent_service, "_query_agent_owned_snipe", lambda *_args: snipe)
    monkeypatch.setattr(remote_agent_service, "_get_or_create_remote_state", lambda *_args: state)
    monkeypatch.setattr(
        remote_agent_service.ws_manager,
        "broadcast_to_user",
        lambda user_id, payload: broadcasts.append((user_id, payload)),
    )

    class FakeDb:
        def add(self, item):
            added.append(item)

        def commit(self):
            pass

    remote_agent_service.record_remote_agent_event(
        FakeDb(),
        SimpleNamespace(id="agent-1", name="West Agent", last_error=None),
        RemoteAgentEventCreate(
            snipe_id="snipe-1",
            event_type="bid",
            message="Remote bid submitted",
            status=SnipeStatus.SNIPED,
            fired_at="2026-04-24T12:00:00Z",
        ),
    )

    assert snipe.status == SnipeStatus.SNIPED
    assert snipe.bid_placed is True
    assert snipe.fired_at is not None
    assert snipe.error_msg is None
    assert added
    assert any(payload["type"] == "snipe.status_changed" for _, payload in broadcasts)


def test_build_sync_response_keeps_active_worker_error_as_agent_error(monkeypatch):
    state = SimpleNamespace(
        status=None,
        last_error=None,
        payload_hash=None,
        last_heartbeat_at=None,
        fired_at=None,
        ended_at=None,
    )
    agent = SimpleNamespace(
        id="agent-1",
        enabled=True,
        last_seen_at=None,
        clock_offset_ms=None,
        last_error="previous error",
    )

    monkeypatch.setattr(remote_agent_service, "_query_agent_owned_snipe", lambda *_args: SimpleNamespace(id="snipe-1"))
    monkeypatch.setattr(remote_agent_service, "_get_or_create_remote_state", lambda *_args: state)
    monkeypatch.setattr(remote_agent_service, "_desired_snipes_for_agent", lambda *_args: [])

    class FakeDb:
        def commit(self):
            pass

    remote_agent_service.build_sync_response(
        FakeDb(),
        agent,
        RemoteAgentSyncRequest(
            clock_offset_ms=123,
            workers=[
                RemoteAgentWorkerReport(
                    snipe_id="snipe-1",
                    status=SnipeStatus.WATCHING,
                    error_msg="remote fetch failed",
                )
            ],
        ),
    )

    assert agent.clock_offset_ms == 123
    assert agent.last_error == "remote fetch failed"
    assert state.last_error == "remote fetch failed"


def test_remote_agent_manager_parses_server_clock_offset_ms():
    server_time = format_datetime(datetime.now(timezone.utc), usegmt=True)

    offset = RemoteAgentManager._parse_server_clock_offset_ms(
        {"server_time": server_time}
    )

    assert offset is not None
    assert abs(offset) < 5000


def test_remote_agent_manager_sends_observed_at_and_clock_offset(monkeypatch):
    payloads = []

    class Client:
        def sync(self, payload):
            payloads.append(payload)
            return {
                "enabled": False,
                "poll_interval_ms": 500,
                "server_time": datetime.now(timezone.utc).isoformat(),
            }

    manager = RemoteAgentManager(Client())
    manager._clock_offset_ms = 42

    def stop_after_one_wait(_seconds):
        manager._stop_event.set()
        return False

    monkeypatch.setattr(manager._stop_event, "wait", stop_after_one_wait)

    manager.run_forever()

    assert payloads
    assert payloads[0]["clock_offset_ms"] == 42
    assert payloads[0]["observed_at"]
