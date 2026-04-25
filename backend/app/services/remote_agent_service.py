"""
Control-plane helpers for remote redundant snipe agents.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..config import REMOTE_AGENT_POLL_INTERVAL_MS
from ..db.models import (
    BuyWanderLogin,
    EventLog,
    RemoteAgent,
    RemoteSnipeState,
    Snipe,
    SnipeStatus,
    User,
)
from ..db.schemas import (
    RemoteAgentDesiredSnipe,
    RemoteAgentEventCreate,
    RemoteAgentSyncRequest,
    RemoteAgentSyncResponse,
)
from ..websocket.manager import ws_manager


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def authenticate_remote_agent(
    db: Session,
    agent_id: str,
    raw_key: str,
) -> RemoteAgent | None:
    agent = db.query(RemoteAgent).filter(RemoteAgent.id == agent_id).first()
    if not agent:
        return None
    expected = agent.api_key_hash or ""
    actual = hash_api_key(raw_key)
    if not hmac.compare_digest(expected, actual):
        return None
    return agent


def _build_payload_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _get_remote_state(
    db: Session,
    agent_id: str,
    snipe_id: str,
) -> RemoteSnipeState | None:
    return (
        db.query(RemoteSnipeState)
        .filter(
            RemoteSnipeState.agent_id == agent_id,
            RemoteSnipeState.snipe_id == snipe_id,
        )
        .first()
    )


def _get_or_create_remote_state(
    db: Session,
    agent_id: str,
    snipe_id: str,
) -> RemoteSnipeState:
    state = _get_remote_state(db, agent_id, snipe_id)
    if state:
        return state
    state = RemoteSnipeState(
        agent_id=agent_id,
        snipe_id=snipe_id,
        status=SnipeStatus.LOADING,
    )
    db.add(state)
    db.flush()
    return state


def _query_agent_owned_snipe(
    db: Session,
    agent_id: str,
    snipe_id: str,
) -> Snipe | None:
    return (
        db.query(Snipe)
        .join(BuyWanderLogin, BuyWanderLogin.id == Snipe.login_id)
        .join(User, User.id == BuyWanderLogin.user_id)
        .filter(
            Snipe.id == snipe_id,
            User.remote_redundancy_enabled == True,  # noqa: E712
            User.remote_agent_id == agent_id,
        )
        .first()
    )


def _desired_snipes_for_agent(
    db: Session,
    agent_id: str,
) -> list[RemoteAgentDesiredSnipe]:
    rows = (
        db.query(Snipe, BuyWanderLogin, User)
        .join(BuyWanderLogin, BuyWanderLogin.id == Snipe.login_id)
        .join(User, User.id == BuyWanderLogin.user_id)
        .filter(
            User.remote_redundancy_enabled == True,  # noqa: E712
            User.remote_agent_id == agent_id,
            BuyWanderLogin.is_active == True,  # noqa: E712
            Snipe.status.in_(list(SnipeStatus.active())),
        )
        .order_by(Snipe.created_at.asc())
        .all()
    )

    desired: list[RemoteAgentDesiredSnipe] = []
    for snipe, login, user in rows:
        payload = {
            "snipe_id": snipe.id,
            "login_id": login.id,
            "user_id": user.id,
            "url": snipe.url,
            "handle": snipe.handle or "",
            "bid_amount": snipe.bid_amount,
            "snipe_seconds": snipe.snipe_seconds,
            "customer_id": login.customer_id or "",
            "bw_email": login.bw_email,
            "encrypted_password": login.encrypted_password,
            "encrypted_cookies": login.encrypted_cookies,
        }
        desired.append(
            RemoteAgentDesiredSnipe(
                **payload,
                payload_hash=_build_payload_hash(payload),
            )
        )

    return desired


def _status_value(status: str | SnipeStatus) -> str:
    return status.value if isinstance(status, SnipeStatus) else str(status)


def _is_terminal_status(status: str | SnipeStatus) -> bool:
    return _status_value(status) in {_status_value(item) for item in SnipeStatus.terminal()}


def _broadcast_remote_update(
    snipe: Snipe,
    *,
    message: str,
    event_type: str,
    status: str | None = None,
    extra: dict | None = None,
) -> None:
    login = snipe.login
    user_id = login.user_id if login else None
    if not user_id:
        return

    ws_manager.broadcast_to_user(
        user_id,
        {
            "type": "log.event",
            "data": {
                "message": message,
                "event_type": event_type,
                "snipe_id": snipe.id,
                "timestamp": _utcnow().isoformat(),
            },
        },
    )
    if status:
        data = {"snipe_id": snipe.id, "status": status}
        if extra:
            data.update(extra)
        ws_manager.broadcast_to_user(
            user_id,
            {
                "type": "snipe.status_changed",
                "data": data,
            },
        )


def _promote_remote_status(
    snipe: Snipe,
    *,
    status: str | None,
    error_msg: str | None = None,
    fired_at: datetime | None = None,
    ended_at: datetime | None = None,
) -> dict:
    if not status:
        return {}

    status_value = _status_value(status)
    updates: dict = {}

    if status_value == _status_value(SnipeStatus.SNIPED):
        updates["status"] = SnipeStatus.SNIPED
        updates["bid_placed"] = True
        if fired_at is not None:
            updates["fired_at"] = fired_at
        elif snipe.fired_at is None:
            updates["fired_at"] = _utcnow()
        updates["error_msg"] = None
    elif status_value == _status_value(SnipeStatus.ERROR):
        updates["status"] = SnipeStatus.ERROR
        updates["error_msg"] = (error_msg or "Remote agent error")[:512]
        if ended_at is not None:
            updates["ended_at"] = ended_at
    elif status_value in {
        _status_value(SnipeStatus.WON),
        _status_value(SnipeStatus.LOST),
        _status_value(SnipeStatus.ENDED),
    }:
        updates["status"] = status_value
        updates["ended_at"] = ended_at or _utcnow()
        updates["error_msg"] = None
        if status_value in {_status_value(SnipeStatus.WON), _status_value(SnipeStatus.LOST)}:
            updates["bid_placed"] = True
            if fired_at is not None:
                updates["fired_at"] = fired_at
            elif snipe.fired_at is None:
                updates["fired_at"] = _utcnow()
    elif not _is_terminal_status(snipe.status):
        updates["status"] = status_value

    if _is_terminal_status(snipe.status) and snipe.status != SnipeStatus.SNIPED:
        terminal_updates = {
            key: value
            for key, value in updates.items()
            if key in {"error_msg"} and value is not None
        }
        return terminal_updates

    for key, value in updates.items():
        setattr(snipe, key, value)
    return updates


def build_sync_response(
    db: Session,
    agent: RemoteAgent,
    body: RemoteAgentSyncRequest,
) -> RemoteAgentSyncResponse:
    now = _utcnow()
    agent.last_seen_at = now
    agent.clock_offset_ms = body.clock_offset_ms
    active_errors: list[str] = []

    for report in body.workers:
        snipe = _query_agent_owned_snipe(db, agent.id, report.snipe_id)
        if not snipe:
            continue

        state = _get_or_create_remote_state(db, agent.id, report.snipe_id)
        state.status = report.status
        state.last_error = report.error_msg
        state.payload_hash = report.payload_hash
        state.last_heartbeat_at = now
        state.fired_at = report.fired_at
        state.ended_at = report.ended_at
        if report.error_msg and not _is_terminal_status(report.status):
            active_errors.append(report.error_msg)

    agent.last_error = active_errors[-1][:512] if active_errors else None

    db.commit()

    desired_snipes = _desired_snipes_for_agent(db, agent.id) if agent.enabled else []
    return RemoteAgentSyncResponse(
        agent_id=agent.id,
        enabled=agent.enabled,
        poll_interval_ms=REMOTE_AGENT_POLL_INTERVAL_MS,
        server_time=now,
        snipes=desired_snipes,
    )


def record_remote_agent_event(
    db: Session,
    agent: RemoteAgent,
    body: RemoteAgentEventCreate,
) -> None:
    snipe = _query_agent_owned_snipe(db, agent.id, body.snipe_id)
    if not snipe:
        raise ValueError("Snipe not found for this agent.")

    state = _get_or_create_remote_state(db, agent.id, body.snipe_id)
    state.last_heartbeat_at = _utcnow()
    if body.status is not None:
        state.status = body.status
    if body.error_msg is not None:
        state.last_error = body.error_msg
        agent.last_error = body.error_msg
    if body.fired_at is not None:
        state.fired_at = body.fired_at
    if body.ended_at is not None:
        state.ended_at = body.ended_at

    updates = _promote_remote_status(
        snipe,
        status=body.status,
        error_msg=body.error_msg,
        fired_at=body.fired_at,
        ended_at=body.ended_at,
    )

    login = snipe.login
    if body.encrypted_cookies is not None and login is not None:
        login.encrypted_cookies = body.encrypted_cookies

    db.add(
        EventLog(
            login_id=snipe.login_id,
            user_id=login.user_id if login else "",
            event_type=body.event_type,
            message=f"[remote:{agent.name}] {body.message}"[:512],
            auction_id=snipe.id,
        )
    )
    db.commit()

    if body.status or body.message:
        _broadcast_remote_update(
            snipe,
            message=f"[remote:{agent.name}] {body.message}"[:512],
            event_type=body.event_type,
            status=body.status,
            extra={
                key: value
                for key, value in {
                    "bid_amount": snipe.bid_amount if updates.get("bid_placed") else None,
                    "error_msg": updates.get("error_msg"),
                }.items()
                if value is not None
            },
        )
