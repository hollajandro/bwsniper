"""
backend/app/db/schemas.py — Pydantic models for request/response validation.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, EmailStr, Field, field_validator


# ─── Auth ─────────────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: Optional[str] = Field(default=None, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    display_name: Optional[str] = None
    is_admin: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str


# ─── BuyWander Login ──────────────────────────────────────────────────────────


class BWLoginCreate(BaseModel):
    bw_email: EmailStr
    bw_password: str


class BWLoginResponse(BaseModel):
    id: str
    bw_email: str
    customer_id: Optional[str] = None
    display_name: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class BWLoginUpdate(BaseModel):
    is_active: Optional[bool] = None
    bw_email: Optional[EmailStr] = None
    bw_password: Optional[str] = None


# ─── Snipes ───────────────────────────────────────────────────────────────────

_ALLOWED_SNIPE_DOMAINS = frozenset({"buywander.com", "www.buywander.com"})
_MAX_BID = 50_000.0  # sanity ceiling; adjust as needed


def _validate_buywander_url(v: str) -> str:
    """Validate that a URL points to a buywander.com auction."""
    try:
        parsed = urlparse(v)
        domain = parsed.netloc.lower()
        if not domain:
            raise ValueError("URL must include a domain.")
        if domain not in _ALLOWED_SNIPE_DOMAINS:
            raise ValueError(f"URL must be a buywander.com auction URL, got: {domain}")
    except ValueError:
        raise
    except Exception:
        raise ValueError("Invalid URL format.")
    return v


class SnipeCreate(BaseModel):
    login_id: str
    url: str
    bid_amount: float = Field(gt=0, lt=_MAX_BID)
    snipe_seconds: int = Field(default=5, ge=1, le=120)
    notify: Optional[bool] = None

    @field_validator("url")
    @classmethod
    def validate_bw_url(cls, v: str) -> str:
        return _validate_buywander_url(v)


class SnipeUpdate(BaseModel):
    bid_amount: Optional[float] = Field(default=None, gt=0, lt=_MAX_BID)
    snipe_seconds: Optional[int] = Field(default=None, ge=1, le=120)
    notify: Optional[bool] = None


class SnipeResponse(BaseModel):
    id: str
    login_id: str
    url: str
    handle: Optional[str] = None
    auction_uuid: Optional[str] = None
    title: Optional[str] = None
    bid_amount: float
    snipe_seconds: int
    status: str
    current_bid: float
    winner_handle: Optional[str] = None
    winner_id: Optional[str] = None
    bid_count: int
    my_max_bid: Optional[float] = None
    final_price: Optional[float] = None
    bid_placed: bool
    is_me: bool
    error_msg: Optional[str] = None
    end_time: Optional[datetime] = None
    reminder_sent: bool
    notify: Optional[bool] = None
    created_at: datetime
    updated_at: datetime
    fired_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ─── History ──────────────────────────────────────────────────────────────────


class HistoryResponse(BaseModel):
    id: str
    login_id: str
    auction_id: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None
    condition: Optional[str] = None
    final_price: float
    my_bid: float
    store_location_id: Optional[str] = None
    won_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ─── Auctions (pass-through from BuyWander) ──────────────────────────────────

_ALLOWED_SORT = frozenset(
    {
        "EndingSoonest",
        "NewArrivals",
        "LowestBid",
        "HighestBid",
        "MostBids",
        "HighestRetail",
        "LowestRetail",
    }
)
_SORT_ALIASES = {"NewlyListed": "NewArrivals"}


class AuctionSearchParams(BaseModel):
    login_id: str
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=24, ge=1, le=100)
    sort_by: str = "EndingSoonest"
    search: str = Field(default="", max_length=500)
    conditions: list[str] = Field(default_factory=list)
    auction_filters: list[str] = Field(default_factory=list)
    store_location_ids: list[str] = Field(default_factory=list)
    min_retail_price: Optional[float] = None
    max_retail_price: Optional[float] = None

    @field_validator("sort_by")
    @classmethod
    def validate_sort_by(cls, v: str) -> str:
        v = _SORT_ALIASES.get(v, v)
        if v not in _ALLOWED_SORT:
            raise ValueError(
                f"sort_by must be one of: {', '.join(sorted(_ALLOWED_SORT))}"
            )
        return v


# ─── Cart ─────────────────────────────────────────────────────────────────────


class PayRequest(BaseModel):
    store_location_id: str


class AppointmentCreate(BaseModel):
    location_id: str
    visit_date_iso: str


class AppointmentReschedule(BaseModel):
    new_date_iso: str


class CartRemoveItem(BaseModel):
    auction_id: str
    reason: str = "ChangedMind"
    notes: str = "No reason provided"


# ─── Watchlist ────────────────────────────────────────────────────────────────


class WatchlistCreate(BaseModel):
    login_id: Optional[str] = None
    url: str
    title: Optional[str] = None
    notes: Optional[str] = None
    auction_id: Optional[str] = None
    snapshot: Optional[dict] = None

    @field_validator("url")
    @classmethod
    def validate_bw_url(cls, v: str) -> str:
        return _validate_buywander_url(v)


class WatchlistResponse(BaseModel):
    id: str
    user_id: str
    login_id: Optional[str] = None
    handle: Optional[str] = None
    auction_id: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    snapshot: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Settings ─────────────────────────────────────────────────────────────────


class DefaultSettings(BaseModel):
    snipe_seconds: int = Field(default=5, ge=1, le=120)
    default_location_id: Optional[str] = None


class TelegramSettings(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""


class SmtpSettings(BaseModel):
    enabled: bool = False
    host: str = "smtp.gmail.com"
    port: int = Field(default=587, ge=1, le=65535)
    username: str = ""
    password: str = ""
    from_addr: str = ""
    to_addr: str = ""
    use_tls: bool = True


class PushoverSettings(BaseModel):
    enabled: bool = False
    user_key: str = ""
    app_token: str = ""


class GotifySettings(BaseModel):
    enabled: bool = False
    url: str = ""
    token: str = ""
    priority: int = Field(default=5, ge=0, le=10)


class NotificationSettings(BaseModel):
    remind_before_seconds: int = Field(default=300, ge=0)
    notify_on_won: bool = True
    notify_on_lost: bool = True
    keyword_watches: list[str] = Field(default_factory=list)
    keyword_watch_locations: dict = Field(
        default_factory=dict
    )  # {keyword: [location_id, ...]}
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    smtp: SmtpSettings = Field(default_factory=SmtpSettings)
    pushover: PushoverSettings = Field(default_factory=PushoverSettings)
    gotify: GotifySettings = Field(default_factory=GotifySettings)


class SettingsResponse(BaseModel):
    defaults: DefaultSettings = Field(default_factory=DefaultSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    serper_api_key: str = ""
    updated_at: Optional[datetime] = None


class SettingsUpdate(BaseModel):
    defaults: Optional[DefaultSettings] = None
    notifications: Optional[NotificationSettings] = None
    serper_api_key: Optional[str] = None
    version: Optional[str] = None  # client's last-known updated_at (ISO string)


# ─── Admin ───────────────────────────────────────────────────────────────────


class AdminUserView(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    is_admin: bool
    remote_redundancy_enabled: bool = False
    remote_agent_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: Optional[str] = Field(default=None, max_length=100)
    is_admin: bool = False
    remote_redundancy_enabled: bool = False
    remote_agent_id: Optional[str] = None


class AdminUserUpdate(BaseModel):
    is_admin: Optional[bool] = None
    display_name: Optional[str] = Field(default=None, max_length=100)
    remote_redundancy_enabled: Optional[bool] = None
    remote_agent_id: Optional[str] = None


class AdminPasswordReset(BaseModel):
    new_password: str = Field(min_length=8)


class RemoteAgentView(BaseModel):
    id: str
    name: str
    region: Optional[str] = None
    enabled: bool
    last_seen_at: Optional[datetime] = None
    last_error: Optional[str] = None
    clock_offset_ms: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RemoteAgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    region: Optional[str] = Field(default=None, max_length=100)
    enabled: bool = True


class RemoteAgentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    region: Optional[str] = Field(default=None, max_length=100)
    enabled: Optional[bool] = None
    rotate_api_key: bool = False


class RemoteAgentProvisionResponse(RemoteAgentView):
    api_key: Optional[str] = None


class RemoteAgentWorkerReport(BaseModel):
    snipe_id: str
    status: str
    error_msg: Optional[str] = None
    fired_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    payload_hash: Optional[str] = None


class RemoteAgentSyncRequest(BaseModel):
    agent_version: str = ""
    observed_at: Optional[datetime] = None
    clock_offset_ms: Optional[int] = None
    workers: list[RemoteAgentWorkerReport] = Field(default_factory=list)


class RemoteAgentDesiredSnipe(BaseModel):
    snipe_id: str
    login_id: str
    user_id: str
    url: str
    handle: str
    bid_amount: float
    snipe_seconds: int
    customer_id: str
    bw_email: str
    encrypted_password: str
    encrypted_cookies: Optional[str] = None
    payload_hash: str


class RemoteAgentSyncResponse(BaseModel):
    agent_id: str
    enabled: bool
    poll_interval_ms: int
    server_time: datetime
    snipes: list[RemoteAgentDesiredSnipe] = Field(default_factory=list)


class RemoteAgentEventCreate(BaseModel):
    snipe_id: str
    event_type: str = Field(default="info", max_length=32)
    message: str = Field(min_length=1, max_length=512)
    status: Optional[str] = Field(default=None, max_length=32)
    error_msg: Optional[str] = Field(default=None, max_length=512)
    fired_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    encrypted_cookies: Optional[str] = None


# ─── WebSocket events ────────────────────────────────────────────────────────


class WSMessage(BaseModel):
    type: str
    data: dict = Field(default_factory=dict)
