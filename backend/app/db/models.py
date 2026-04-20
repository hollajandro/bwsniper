"""
backend/app/db/models.py — SQLAlchemy ORM models.

Tables:
    users             – app-level user accounts
    buywander_logins  – BuyWander credentials (encrypted), many-per-user
    snipes            – upcoming and past snipe records, per-login
    history           – won-auction cache, per-login
    user_config       – notification & default settings, per-user
    event_log         – timestamped event stream, per-login
    notification_queue – dead-letter queue for failed notifications
"""

import uuid as _uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

Base = declarative_base()


class SnipeStatus(str, Enum):
    """Canonical snipe lifecycle states — use instead of bare string literals."""

    LOADING = "Loading"
    WATCHING = "Watching"
    SNIPED = "Sniped"
    WON = "Won"
    LOST = "Lost"
    ENDED = "Ended"
    ERROR = "Error"
    DELETED = "Deleted"

    # Convenience helpers
    @classmethod
    def terminal(cls) -> frozenset:
        return frozenset({cls.WON, cls.LOST, cls.ENDED, cls.ERROR, cls.DELETED})

    @classmethod
    def active(cls) -> frozenset:
        return frozenset({cls.LOADING, cls.WATCHING, cls.SNIPED})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(_uuid.uuid4())


# ─── Users ────────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    logins = relationship(
        "BuyWanderLogin", back_populates="user", cascade="all, delete-orphan"
    )
    config = relationship(
        "UserConfig", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    refresh_tokens = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )


# ─── BuyWander Logins ─────────────────────────────────────────────────────────


class BuyWanderLogin(Base):
    __tablename__ = "buywander_logins"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    bw_email = Column(String(255), nullable=False)
    encrypted_password = Column(Text, nullable=False)  # Fernet-encrypted
    encrypted_cookies = Column(Text, nullable=True)  # Fernet-encrypted JSON
    customer_id = Column(String(64), nullable=True)
    display_name = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user = relationship("User", back_populates="logins")
    snipes = relationship("Snipe", back_populates="login", cascade="all, delete-orphan")
    history_records = relationship(
        "HistoryRecord", back_populates="login", cascade="all, delete-orphan"
    )
    events = relationship(
        "EventLog", back_populates="login", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_buywander_login_user", "user_id"),)


# ─── Snipes ───────────────────────────────────────────────────────────────────


class Snipe(Base):
    __tablename__ = "snipes"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    login_id = Column(String(36), ForeignKey("buywander_logins.id"), nullable=False)
    url = Column(String(512), nullable=False)
    handle = Column(String(255), nullable=True)
    auction_uuid = Column(String(64), nullable=True)
    title = Column(String(512), nullable=True)
    bid_amount = Column(Float, nullable=False)
    snipe_seconds = Column(Integer, default=5)
    status = Column(String(32), default=SnipeStatus.LOADING)
    current_bid = Column(Float, default=0.0)
    winner_handle = Column(String(100), nullable=True)
    winner_id = Column(String(64), nullable=True)
    bid_count = Column(Integer, default=0)
    my_max_bid = Column(Float, nullable=True)
    final_price = Column(Float, nullable=True)
    bid_placed = Column(Boolean, default=False)
    is_me = Column(Boolean, default=False)
    error_msg = Column(String(512), nullable=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    reminder_sent = Column(Boolean, default=False)
    notify = Column(Boolean, nullable=True)  # None = use global setting
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    fired_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)

    login = relationship("BuyWanderLogin", back_populates="snipes")

    __table_args__ = (
        Index("ix_snipe_login", "login_id"),
        Index("ix_snipe_status", "status"),
    )


# ─── History ──────────────────────────────────────────────────────────────────


class HistoryRecord(Base):
    __tablename__ = "history"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    login_id = Column(String(36), ForeignKey("buywander_logins.id"), nullable=False)
    auction_id = Column(String(64), nullable=True)
    title = Column(String(512), nullable=True)
    url = Column(String(512), nullable=True)
    condition = Column(String(64), nullable=True)
    final_price = Column(Float, nullable=False)
    my_bid = Column(Float, nullable=False)
    store_location_id = Column(String(36), nullable=True)
    won_at = Column(DateTime(timezone=True), default=_utcnow)

    login = relationship("BuyWanderLogin", back_populates="history_records")

    __table_args__ = (Index("ix_history_login", "login_id"),)


# ─── User Config ──────────────────────────────────────────────────────────────


class UserConfig(Base):
    __tablename__ = "user_config"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), unique=True, nullable=False)
    config_json = Column(Text, nullable=False, default="{}")
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user = relationship("User", back_populates="config")


# ─── Event Log ────────────────────────────────────────────────────────────────


class EventLog(Base):
    __tablename__ = "event_log"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    login_id = Column(String(36), ForeignKey("buywander_logins.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    event_type = Column(String(32), nullable=False)
    message = Column(String(512), nullable=False)
    auction_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, index=True)

    login = relationship("BuyWanderLogin", back_populates="events")

    __table_args__ = (
        Index("ix_event_log_user", "user_id"),
        Index("ix_event_log_login", "login_id"),
    )


# ─── Watchlist ────────────────────────────────────────────────────────────────


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    login_id = Column(String(36), ForeignKey("buywander_logins.id"), nullable=True)
    handle = Column(String(255), nullable=False)
    url = Column(String(512), nullable=True)
    title = Column(String(512), nullable=True)
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("ix_watchlist_user", "user_id"),)


# ─── Refresh Token Store ──────────────────────────────────────────────────────


class RefreshToken(Base):
    """Single-use refresh token registry for rotation + revocation."""

    __tablename__ = "refresh_tokens"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    revoked = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    user = relationship("User", back_populates="refresh_tokens")

    __table_args__ = (Index("ix_refresh_token_user", "user_id"),)


# ─── Notification Dead Letter Queue ──────────────────────────────────────────


class NotificationQueue(Base):
    """Dead-letter queue for failed notifications with retry support."""

    __tablename__ = "notification_queue"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    channel = Column(String(32), nullable=False)  # telegram, smtp, pushover, gotify
    subject = Column(String(512), nullable=False)
    body = Column(Text, nullable=False)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    last_error = Column(String(512), nullable=True)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, index=True)

    __table_args__ = (Index("ix_notification_queue_retry", "next_retry_at"),)
