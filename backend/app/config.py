"""
backend/app/config.py — Application settings loaded from environment.
"""

import os
import secrets
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent.parent
DATA_DIR    = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'bwsniper.db'}")

# ── Environment ───────────────────────────────────────────────────────────────
ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

# ── Security ─────────────────────────────────────────────────────────────────
# SECRET_KEY persists to disk so JWTs survive restarts.
# Set SECRET_KEY env var to override (e.g. in Docker / prod).
_SECRET_KEY_FILE = DATA_DIR / "secret.key"
_SECRET_KEY_WAS_EXPLICIT = bool(os.getenv("SECRET_KEY"))
SECRET_KEY: str = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    if _SECRET_KEY_FILE.exists():
        SECRET_KEY = _SECRET_KEY_FILE.read_text().strip()
    else:
        SECRET_KEY = secrets.token_urlsafe(48)
        _SECRET_KEY_FILE.write_text(SECRET_KEY)
        try:
            _SECRET_KEY_FILE.chmod(0o600)  # owner-read/write only
        except NotImplementedError:
            pass  # Windows doesn't support chmod; acceptable there

# Guard: refuse to run in production without an explicitly-set SECRET_KEY
if ENVIRONMENT == "production" and not _SECRET_KEY_WAS_EXPLICIT:
    raise RuntimeError(
        "ERROR: ENVIRONMENT is 'production' but SECRET_KEY was not set explicitly.\n"
        "Please set the SECRET_KEY environment variable to a random 48+ character string.\n"
        "Example:  python -c 'import secrets; print(secrets.token_urlsafe(48))'\n"
        "This ensures JWTs survive server restarts and are not auto-generated on each run."
    )

JWT_ALGORITHM       = "HS256"
ACCESS_TOKEN_EXPIRE = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24h
REFRESH_TOKEN_EXPIRE = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

# ── CORS ─────────────────────────────────────────────────────────────────────
# Comma-separated list of allowed origins.  Override via CORS_ORIGINS env var.
CORS_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:3000,http://localhost:8080",
    ).split(",")
    if o.strip()
]

# Fernet key for encrypting BuyWander credentials at rest.
# If not set, generates one on first run and writes to DATA_DIR/fernet.key
# IMPORTANT: You MUST back up this key file or set FERNET_KEY env var in production.
# If the key is lost, all encrypted credentials become unrecoverable.
_FERNET_KEY_FILE = DATA_DIR / "fernet.key"
FERNET_KEY: str = os.getenv("FERNET_KEY", "")
if not FERNET_KEY:
    if _FERNET_KEY_FILE.exists():
        FERNET_KEY = _FERNET_KEY_FILE.read_text().strip()
    else:
        from cryptography.fernet import Fernet
        FERNET_KEY = Fernet.generate_key().decode()
        _FERNET_KEY_FILE.write_text(FERNET_KEY)
        try:
            _FERNET_KEY_FILE.chmod(0o600)  # owner-read/write only
        except NotImplementedError:
            pass  # Windows doesn't support chmod; acceptable there

# Guard: fail loudly if FERNET_KEY is missing and no existing key file found
# This prevents accidental data loss in ephemeral environments (e.g., containers)
if not FERNET_KEY and not _FERNET_KEY_FILE.exists():
    raise RuntimeError(
        "ERROR: FERNET_KEY is not set and no existing key file was found.\n"
        "Please set the FERNET_KEY environment variable or ensure the data/ directory is persisted.\n"
        "Losing the Fernet key will make all encrypted credentials unrecoverable.\n"
        "To generate a new key: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
    )

# ── Cleanup intervals (seconds) ───────────────────────────────────────────────
CLEANUP_INTERVAL_SEC = int(os.getenv("CLEANUP_INTERVAL_SEC", "60"))
TOKEN_PURGE_INTERVAL_ITER = int(os.getenv("TOKEN_PURGE_INTERVAL_ITER", "5"))  # iterations before purge
SESSION_REFRESH_INTERVAL_ITER = int(os.getenv("SESSION_REFRESH_INTERVAL_ITER", "1200"))  # ~20 hours

# ── BuyWander upstream ───────────────────────────────────────────────────────
BW_API_BASE  = os.getenv("BW_API_BASE", "https://api.buywander.com")
BW_SITE_BASE = os.getenv("BW_SITE_BASE", "https://www.buywander.com")
BW_SESSION_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Origin":       BW_SITE_BASE,
    "Referer":      BW_SITE_BASE + "/",
    "Accept":       "application/json",
    "Content-Type": "application/json",
}

# ── Price comparison (Serper.dev Google Shopping) ────────────────────────────
# Get a free key at https://serper.dev (2,500 searches/month free tier)
SERPER_API_KEY: str = os.getenv("SERPER_API_KEY", "")

# ── Stripe ────────────────────────────────────────────────────────────────────
# BuyWander's Stripe publishable key — required to confirm Payment Intents when
# a saved payment method is on file (i.e. complete the checkout server-side).
# Find it by inspecting the BuyWander website's network traffic or JS bundle;
# it starts with "pk_live_".
STRIPE_PUBLISHABLE_KEY: str = os.getenv("STRIPE_PUBLISHABLE_KEY", "")

# ── Auction browse defaults ──────────────────────────────────────────────────
BROWSE_PAGE_SIZE = 24

# ── Condition map (for display) ──────────────────────────────────────────────
COND_MAP = {
    "New": "New", "AppearsNew": "Appears New",
    "UsedGood": "Good", "UsedFair": "Fair",
    "Damaged": "Damaged", "GentlyUsed": "Gently Used",
    "Used": "Used", "EasyFix": "Easy Fix",
    "HeavyUse": "Heavy Use", "MajorFix": "Major Fix",
    "MixedCondition": "Mixed",
}
