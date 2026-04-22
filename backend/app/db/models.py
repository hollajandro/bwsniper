"""
backend/app/db/models.py - SQLAlchemy ORM models.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SnipeStatus(str, Enum):
    """Canonical snipe lifecycle states."""

    LOADING = "Loading"
    WATCHING = "Watching"
    SNIPED = "Sniped"
    WON = "Won"
    LOST = "Lost"
    ENDED = "Ended"
    ERROR = "Error"
    DELETED = "Deleted"

    @classmethod
    def terminal(cls) -> frozenset["SnipeStatus"]:
        return frozenset({cls.WON, cls.LOST, cls.ENDED, cls.ERROR, cls.DELETED})

    @classmethod
    def active(cls) -> frozenset["SnipeStatus"]:
        return frozenset({cls.LOADING, cls.WATCHING, cls.SNIPED})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(_uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    logins: Mapped[list["BuyWanderLogin"]] = relationship(
        "BuyWanderLogin", back_populates="user", cascade="all, delete-orphan"
    )
    config: Mapped["UserConfig | None"] = relationship(
        "UserConfig", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )


class BuyWanderLogin(Base):
    __tablename__ = "buywander_logins"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    bw_email: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_password: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_cookies: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    user: Mapped["User"] = relationship("User", back_populates="logins")
    snipes: Mapped[list["Snipe"]] = relationship(
        "Snipe", back_populates="login", cascade="all, delete-orphan"
    )
    history_records: Mapped[list["HistoryRecord"]] = relationship(
        "HistoryRecord", back_populates="login", cascade="all, delete-orphan"
    )
    events: Mapped[list["EventLog"]] = relationship(
        "EventLog", back_populates="login", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_buywander_login_user", "user_id"),)


class Snipe(Base):
    __tablename__ = "snipes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    login_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("buywander_logins.id"), nullable=False
    )
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    handle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auction_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    bid_amount: Mapped[float] = mapped_column(Float, nullable=False)
    snipe_seconds: Mapped[int] = mapped_column(Integer, default=5)
    status: Mapped[str] = mapped_column(String(32), default=SnipeStatus.LOADING)
    current_bid: Mapped[float] = mapped_column(Float, default=0.0)
    winner_handle: Mapped[str | None] = mapped_column(String(100), nullable=True)
    winner_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bid_count: Mapped[int] = mapped_column(Integer, default=0)
    my_max_bid: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    bid_placed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_me: Mapped[bool] = mapped_column(Boolean, default=False)
    error_msg: Mapped[str | None] = mapped_column(String(512), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    notify: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    fired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    login: Mapped["BuyWanderLogin"] = relationship(
        "BuyWanderLogin", back_populates="snipes"
    )

    __table_args__ = (
        Index("ix_snipe_login", "login_id"),
        Index("ix_snipe_status", "status"),
    )


class HistoryRecord(Base):
    __tablename__ = "history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    login_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("buywander_logins.id"), nullable=False
    )
    auction_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    condition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    final_price: Mapped[float] = mapped_column(Float, nullable=False)
    my_bid: Mapped[float] = mapped_column(Float, nullable=False)
    store_location_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    won_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    login: Mapped["BuyWanderLogin"] = relationship(
        "BuyWanderLogin", back_populates="history_records"
    )

    __table_args__ = (Index("ix_history_login", "login_id"),)


class UserConfig(Base):
    __tablename__ = "user_config"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), unique=True, nullable=False
    )
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    user: Mapped["User"] = relationship("User", back_populates="config")


class EventLog(Base):
    __tablename__ = "event_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    login_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("buywander_logins.id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(String(512), nullable=False)
    auction_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )

    login: Mapped["BuyWanderLogin"] = relationship(
        "BuyWanderLogin", back_populates="events"
    )

    __table_args__ = (
        Index("ix_event_log_user", "user_id"),
        Index("ix_event_log_login", "login_id"),
    )


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    login_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("buywander_logins.id"), nullable=True
    )
    handle: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    __table_args__ = (Index("ix_watchlist_user", "user_id"),)


class RefreshToken(Base):
    """Single-use refresh token registry for rotation and revocation."""

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")

    __table_args__ = (Index("ix_refresh_token_user", "user_id"),)


class NotificationQueue(Base):
    """Dead-letter queue for failed notifications with retry support."""

    __tablename__ = "notification_queue"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )

    __table_args__ = (Index("ix_notification_queue_retry", "next_retry_at"),)
