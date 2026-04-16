"""
backend/app/services/notification_service.py — Multi-channel notification dispatch.

Sends notifications via Telegram, SMTP, Pushover, and Gotify.
All sends run via a bounded thread pool so they never block the worker
and cannot exhaust system threads.

Extracted from the original bw/notifications.py.
"""

import logging
import smtplib
import ssl
import threading
from concurrent.futures import ThreadPoolExecutor
from email.mime.text import MIMEText
from ipaddress import ip_address
from socket import getaddrinfo, AF_INET, AF_INET6
from typing import Callable
from urllib.parse import urlparse

import requests

from ..services.notification_encryption import decrypt_notifications

log = logging.getLogger(__name__)

# Bounded pool prevents thread exhaustion from notification floods
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="notif")


def any_enabled(cfg: dict) -> bool:
    """True if at least one notification channel is enabled."""
    notif = cfg.get("notifications", {})
    return any(notif.get(ch, {}).get("enabled") for ch in _CHANNEL_MAP)


def notify_reminder(cfg: dict, title: str, secs_left: float,
                    bid_amount: float, log_fn: Callable = None):
    """Pre-snipe reminder: 'Auction X ends in N minutes, your bid is $Y'."""
    mins = max(1, int(secs_left / 60))
    subject = f"Snipe reminder: {title[:50]}"
    body    = (f"Auction \"{title}\" ends in ~{mins} minute(s).\n"
               f"Your bid: ${bid_amount:.2f}\n"
               f"Time left: {int(secs_left)}s")
    _dispatch(cfg, subject, body, log_fn)


def notify_outcome(cfg: dict, title: str, status: str,
                   bid_amount: float, final_price: float,
                   log_fn: Callable = None):
    """Post-snipe result: Won / Lost / Ended / Error."""
    subject = f"Snipe {status}: {title[:50]}"
    body    = (f"Auction: {title}\n"
               f"Result:  {status}\n"
               f"Your bid: ${bid_amount:.2f}\n"
               f"Final price: ${final_price:.2f}")
    _dispatch(cfg, subject, body, log_fn)


def notify_keyword_match(cfg: dict, keyword: str, title: str,
                         cur_bid: float, url: str):
    """Keyword watch: a new auction matching a keyword was found."""
    subject = f"New auction: {keyword}"
    body = (f"Keyword: \"{keyword}\"\n"
            f"Title: {title}\n"
            f"Current bid: ${cur_bid:.2f}\n"
            f"{url}")
    _dispatch(cfg, subject, body)


def send_test(channel: str, ch_cfg: dict, subject: str, body: str):
    """Send a single test notification synchronously. Raises on failure.

    ch_cfg values may be encrypted — decrypt them before passing to senders.
    """
    fn = _CHANNEL_MAP.get(channel)
    if not fn:
        raise ValueError(f"Unknown channel: {channel}")
    # Decrypt credential fields in the channel config
    ch_cfg = decrypt_notifications({"notifications": {channel: ch_cfg}})
    ch_cfg = ch_cfg.get("notifications", {}).get(channel, {})
    fn(ch_cfg, subject, body)


# ── Internal ─────────────────────────────────────────────────────────────────

_CHANNEL_MAP = {
    "telegram": None,  # assigned after function defs below
    "smtp":     None,
    "pushover": None,
    "gotify":   None,
}


def _dispatch(cfg: dict, subject: str, body: str, log_fn: Callable = None):
    """Fire all enabled channels via the bounded thread pool.

    Credentials stored in cfg may be encrypted — decrypt them before use.
    """
    # Decrypt any encrypted credential fields so senders receive plain text
    cfg = decrypt_notifications(cfg)
    notif = cfg.get("notifications", {})
    for name, fn in _CHANNEL_MAP.items():
        ch_cfg = notif.get(name, {})
        if ch_cfg.get("enabled"):
            _pool.submit(_safe_send, fn, ch_cfg, subject, body, log_fn, name)


def _safe_send(fn, ch_cfg, subject, body, log_fn, name):
    try:
        fn(ch_cfg, subject, body)
        if log_fn:
            log_fn(f"Notification sent via {name}")
    except Exception as ex:
        log.warning("Notification failed (%s): %s", name, ex)
        if log_fn:
            log_fn(f"Notification failed ({name}): {ex}")


def _safe_int(val, default: int) -> int:
    """Parse an int, falling back to default on any error."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _is_private_host(hostname: str) -> bool:
    """Check if a hostname resolves to a private/loopback/link-local IP."""
    try:
        for family, _, _, _, sockaddr in getaddrinfo(hostname, None, 0):
            addr = ip_address(sockaddr[0])
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                return True
    except Exception:
        pass
    return False


def _validate_url(url: str, *, allow_private: bool = False) -> str:
    """Validate that a URL uses http(s) and optionally block private hosts."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL must use http or https, got: {parsed.scheme!r}")
    if not parsed.hostname:
        raise ValueError("URL has no hostname")
    if not allow_private and _is_private_host(parsed.hostname):
        raise ValueError(f"URL resolves to a private/internal address: {parsed.hostname}")
    return url


# ── Channel senders ──────────────────────────────────────────────────────────

def _send_telegram(cfg: dict, subject: str, body: str):
    token   = cfg.get("bot_token", "")
    chat_id = cfg.get("chat_id", "")
    if not token or not chat_id:
        return
    text = f"*{subject}*\n{body}"
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=10,
    )


def _send_smtp(cfg: dict, subject: str, body: str):
    host      = cfg.get("host", "smtp.gmail.com")
    port      = _safe_int(cfg.get("port", 587), 587)
    username  = cfg.get("username", "")
    password  = cfg.get("password", "")
    from_addr = cfg.get("from_addr", username)
    to_addr   = cfg.get("to_addr", "")
    use_tls   = cfg.get("use_tls", True)
    if not to_addr:
        return
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = to_addr
    needs_auth = bool(username and password and username.lower() not in ("", "none"))
    with smtplib.SMTP(host, port, timeout=15) as s:
        if use_tls:
            ctx = ssl.create_default_context()
            s.starttls(context=ctx)
        if needs_auth:
            try:
                s.login(username, password)
            except smtplib.SMTPNotSupportedError:
                log.warning("SMTP server %s does not support AUTH — sending unauthenticated", host)
        s.send_message(msg)


def _send_pushover(cfg: dict, subject: str, body: str):
    user_key  = cfg.get("user_key", "")
    app_token = cfg.get("app_token", "")
    if not user_key or not app_token:
        return
    requests.post(
        "https://api.pushover.net/1/messages.json",
        data={"token": app_token, "user": user_key,
              "title": subject, "message": body},
        timeout=10,
    )


def _send_gotify(cfg: dict, subject: str, body: str):
    url      = cfg.get("url", "").rstrip("/")
    token    = cfg.get("token", "")
    priority = _safe_int(cfg.get("priority", 5), 5)
    if not url or not token:
        return
    _validate_url(url)
    requests.post(
        f"{url}/message",
        params={"token": token},
        json={"title": subject, "message": body, "priority": priority},
        timeout=10,
    )


# Wire up channel map after function definitions
_CHANNEL_MAP["telegram"] = _send_telegram
_CHANNEL_MAP["smtp"]     = _send_smtp
_CHANNEL_MAP["pushover"] = _send_pushover
_CHANNEL_MAP["gotify"]   = _send_gotify
