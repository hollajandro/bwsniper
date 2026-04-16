# BwSniper

A self-hosted web application for automated auction sniping on [BuyWander](https://www.buywander.com). Browse live auctions, queue snipe bids that fire automatically at a configurable number of seconds before an auction ends, and manage your cart — all from a single dashboard.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Quick Start — Docker](#quick-start--docker)
- [Development Setup](#development-setup)
- [Configuration](#configuration)
- [Usage Guide](#usage-guide)
- [API Reference](#api-reference)
- [Snipe Lifecycle](#snipe-lifecycle)
- [Data & Security](#data--security)
- [Troubleshooting](#troubleshooting)

---

## Features

### Sniping
- **Automated snipe bids** — a background worker thread monitors each auction and fires your bid at a precise number of seconds before it ends
- **Live status updates** — real-time WebSocket push; status badges, countdown timers, and the current winning bid all update without polling
- **Per-snipe timing control** — set snipe timing from 1–120 seconds independently for each bid
- **Live bid editing** — change your max bid or timing on a running snipe and the worker picks it up immediately (thread-safe)
- **Win/loss notifications** — in-app toast on win; optional email notifications configurable per-snipe or globally

### Browse
- **Full auction browser** — browse all active BuyWander auctions with server-side pagination and infinite scroll
- **Filters** — location (multi-select), condition (multi-select), retail price range, keyword search with `"quoted phrase"` exact matching
- **Sort options** — ending soonest/latest, new arrivals, price ascending/descending, retail ascending/descending, bids ascending/descending
- **Quick filters** — Sniped, Watched, No Bids Yet, $3 or Less, Ends Today, Ends Tomorrow, 90%+ Off
- **Auction detail modal** — full description, seller notes, image gallery with fullscreen lightbox, bid history table, and live Google Shopping price comparison
- **Snipe from Browse** — click any card to open the detail modal and snipe directly; pre-filled with current bid + $1 and 35% of retail as a suggested maximum
- **Bulk snipe** — select multiple auctions with checkboxes and queue them all at once
- **Condition badges** — color-coded by condition (New → Damaged) with bid-count heat indicators
- **Ended auction cache** — auctions that expire while you're browsing are preserved in a 7-day local cache under an "Ended" tab
- **Recently viewed** — a "Recent" tab tracks the last 50 auctions you opened

### Dashboard
- **Active snipes table** — live countdown, current bid, your bid, leading bidder, snipe-at timing
- **Past snipes** — won/lost/ended history with final prices
- **Session statistics** — win rate, total wins/losses, dollars saved, average discount
- **Win toast** — animated notification when you win an auction
- **Edit/cancel** — modify any active snipe or cancel it from the table

### Cart
- **Full cart view** — paid items awaiting pickup, pending-payment items, reserved auctions
- **Location selector** — defaults to the location set in Settings; remembers your choice
- **Removal allowance banner** — shows how many free item removals remain (color-coded: green → yellow at 70% used → red at zero); confirms remaining count before each removal
- **Expiry warnings** — items expiring within 48 hours are highlighted with a countdown
- **Pickup appointments** — schedule, reschedule, or cancel pickup appointments with a time-slot picker
- **One-click checkout** — pay your pending cart items directly from the UI

### History
- **Won auction log** — searchable, filterable table of all your BuyWander wins
- **Detail modal** — same full modal as Browse (images, price comparison, bid history)
- **Refresh from BuyWander** — pull the latest won-auction data on demand
- **CSV export** — download your full history as a spreadsheet

### Settings
- **BuyWander account management** — add, remove, and toggle multiple BuyWander logins
- **Default location** — set a default store location applied across Browse and Cart
- **Default snipe timing** — pre-fill the snipe-at seconds when adding new snipes
- **Notification preferences** — toggle won/lost email notifications globally; configure notification email address

### Price Comparison
- Powered by [Serper.dev](https://serper.dev) Google Shopping API (free tier: 2,500 searches/month)
- Smart query building: `brand + model` → `brand + title` → `title` alone
- Results are cached per auction for the lifetime of the browser session

---

## Architecture

```
┌─────────────────────┐        ┌──────────────────────────────────────┐
│   Browser (React)   │◄──────►│  nginx (port 80)                     │
│                     │  HTTP  │  • serves static Vite build           │
│  React 18 + Router  │  WS    │  • proxies /api/* → backend:8000     │
│  Tailwind CSS       │        │  • proxies /ws   → backend:8000      │
│  Context + hooks    │        └──────────────────────────────────────┘
└─────────────────────┘                        │
                                               ▼
                               ┌──────────────────────────────────────┐
                               │  FastAPI (uvicorn, port 8000)        │
                               │                                      │
                               │  REST API  (/api/*)                  │
                               │  WebSocket (/ws)                     │
                               │  Auth: JWT + refresh-token rotation  │
                               │  Rate limiting: slowapi              │
                               │                                      │
                               │  AuctionWorker threads (one/snipe)   │
                               │  • polls BuyWander API               │
                               │  • fires bid at snipe_seconds        │
                               │  • broadcasts status via WS          │
                               └──────────────┬───────────────────────┘
                                              │
                               ┌──────────────▼───────────────────────┐
                               │  SQLite (WAL mode)                   │
                               │  /backend/data/bwsniper.db           │
                               │                                      │
                               │  users · buywander_logins · snipes   │
                               │  history · event_log · user_config   │
                               │  watchlist · refresh_tokens          │
                               └──────────────────────────────────────┘
```

### Key design decisions

| Concern | Approach |
|---|---|
| Real-time updates | WebSocket with first-message JWT auth; background threads use `run_coroutine_threadsafe` to schedule sends on the async event loop |
| BW credential storage | Fernet symmetric encryption at rest; key auto-generated and stored in the data volume |
| Token security | Short-lived JWTs (24h); single-use refresh tokens with rotation — old token revoked on each refresh |
| Thread safety | Each `AuctionWorker` has a `threading.Lock` protecting live `bid_amount`/`snipe_seconds` updates |
| SQLite concurrency | WAL journal mode + `busy_timeout=5000` + `synchronous=NORMAL` |
| Cart API speed | Three independent BuyWander requests (`cart`, `reserved`, `payment methods`) run in parallel via `ThreadPoolExecutor` |

---

## Quick Start — Docker

**Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker + Docker Compose v2)

```bash
# 1. Clone the repo
git clone https://github.com/youruser/bwsniper.git
cd bwsniper

# 2. Create your environment file
cp .env.example .env

# 3. Generate a SECRET_KEY and paste it into .env
python -c "import secrets; print(secrets.token_urlsafe(48))"

# 4. (Recommended) Generate a FERNET_KEY and paste it into .env
#    Without this, the key is auto-generated inside the container and
#    will be lost if the container image is ever recreated.
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 5. Build and start
docker compose up -d --build

# 6. Open the app
open http://localhost        # macOS
start http://localhost       # Windows
xdg-open http://localhost    # Linux
```

Register an account on the login screen, then go to **Settings → BuyWander Accounts** to add your BuyWander credentials.

### Useful Docker commands

```bash
# View logs
docker compose logs -f

# View backend logs only
docker compose logs -f backend

# Stop everything
docker compose down

# Stop and remove the data volume (wipes the database)
docker compose down -v

# Rebuild after a code change
docker compose up -d --build
```

### Changing the port

The app defaults to port **80**. To use a different port:

```bash
# In .env:
WEB_PORT=8080

# Then restart
docker compose up -d
```

---

## Development Setup

Running outside Docker is useful during active development.

### Backend

**Requirements:** Python 3.11+

```bash
cd backend

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the dev server (auto-reload on file change)
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Frontend

**Requirements:** Node.js 20+

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server with HMR
npm run dev
```

The app will be at `http://localhost:3000`. The Vite dev server proxies `/api` and `/ws` to `localhost:8000` automatically.

### Running both at once

Open two terminals, start the backend in one and the frontend in the other. Changes to either are reflected immediately without a rebuild.

---

## Configuration

All settings are controlled through environment variables. Copy `.env.example` to `.env` and fill in your values before starting.

### Required

| Variable | Description |
|---|---|
| `SECRET_KEY` | JWT signing secret. **Must be set in production.** Generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"` |

### Strongly recommended

| Variable | Default | Description |
|---|---|---|
| `FERNET_KEY` | *(auto-generated)* | Fernet key for encrypting stored BuyWander passwords. If left blank, one is generated on first start and written to `/backend/data/fernet.key`. **Back this up**, or set it explicitly so it survives container recreations. Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

### Optional

| Variable | Default | Description |
|---|---|---|
| `SERPER_API_KEY` | *(empty)* | [Serper.dev](https://serper.dev) API key for Google Shopping price comparison. Free tier: 2,500 searches/month. Price comparison is silently disabled when not set. |
| `CORS_ORIGINS` | `http://localhost` | Comma-separated list of allowed CORS origins. Set to the URL your browser uses to reach the frontend (e.g. `https://sniper.example.com`). |
| `WEB_PORT` | `80` | External port for the nginx frontend container. |
| `WEB_CONCURRENCY` | `2` | Number of Uvicorn worker processes. Rule of thumb: `2 × CPU cores + 1`. Don't set above 4 for SQLite. |
| `DATABASE_URL` | *(SQLite in data volume)* | SQLAlchemy database URL. Defaults to `sqlite:///./data/bwsniper.db`. Set to a PostgreSQL URL for production scale. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | JWT access token lifetime (24 hours). |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Refresh token lifetime. |

---

## Usage Guide

### 1. Register and add a BuyWander account

1. Open the app and click **Register**
2. Create a BwSniper account (this is local — it doesn't create a BuyWander account)
3. Go to **Settings** → **BuyWander Accounts** → **Add Account**
4. Enter your BuyWander email and password
5. BwSniper will authenticate with BuyWander and store your encrypted session cookies

You can add multiple BuyWander accounts. Each snipe, cart view, and history lookup is scoped to the account you select.

### 2. Browse and snipe

**From Browse:**
1. Navigate to **Browse**
2. Use the location checkboxes, condition filters, and price range to narrow results
3. Click any auction card to open the detail modal
4. Review the description, bid history, and Google Shopping price comparison
5. Click **Snipe This** and enter your maximum bid and snipe timing
6. Click **Add Snipe** — the worker starts immediately

**From the Dashboard:**
1. Navigate to **Dashboard**
2. Paste a BuyWander auction URL into the **Add New Snipe** form
3. Enter your max bid, snipe timing, and select which BuyWander account to use
4. Click **+ Snipe**

### 3. Monitor snipes

The **Dashboard** shows all your active and past snipes with live status. The **Status** column updates in real time via WebSocket:

| Status | Meaning |
|---|---|
| Loading | Worker is fetching the initial auction state |
| Watching | Monitoring the auction; waiting for the snipe window |
| Sniped | Bid has been submitted |
| Won | You won the auction |
| Lost | Auction ended; another bidder won |
| Ended | Auction ended without your bid being placed (no one bid above your threshold) |
| Error | Something went wrong (hover for details) |

### 4. Manage your cart

1. Go to **Cart**
2. Select your BuyWander account and store location
3. The cart shows paid items awaiting pickup, pending payment items, and reserved auctions
4. Use **Remove** to remove pending items (the app shows how many free removals you have left)
5. Use the **Pickup Appointment** section to schedule or reschedule a pickup time

### 5. Price comparison

Price comparison appears automatically in the detail modal on Browse, Dashboard, and History. It searches Google Shopping using:
- `brand + model number` (most specific)
- `brand + title` (if no model)
- `title` alone (fallback)

Results are cached in memory per session so reopening the same auction doesn't fire a new API request.

---

## API Reference

The backend exposes a REST API at `/api` and a WebSocket endpoint at `/ws`. Interactive documentation is available at `http://localhost:8000/docs` when the backend is running.

### Authentication

All endpoints except `/api/auth/register` and `/api/auth/login` require a Bearer token:

```
Authorization: Bearer <access_token>
```

#### Auth endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Create a new account |
| `POST` | `/api/auth/login` | Authenticate and receive token pair |
| `POST` | `/api/auth/refresh` | Exchange a refresh token for a new token pair |
| `POST` | `/api/auth/logout` | Revoke the refresh token |

#### Snipes

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/snipes` | List all snipes (optional `?login_id=`) |
| `POST` | `/api/snipes` | Create a new snipe and start its worker |
| `GET` | `/api/snipes/{id}` | Get snipe details |
| `PUT` | `/api/snipes/{id}` | Update bid amount or snipe timing |
| `DELETE` | `/api/snipes/{id}` | Cancel and delete a snipe |

#### Auctions

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/auctions/search` | Browse active auctions (filters, sort, pagination) |
| `GET` | `/api/auctions/{id}` | Get full auction detail from BuyWander |
| `GET` | `/api/auctions/locations/list` | List store locations |

#### Cart

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/cart/{login_id}` | Fetch cart, paid items, and payment methods |
| `GET` | `/api/cart/{login_id}/removal-status` | Check free removal allowance |
| `DELETE` | `/api/cart/{login_id}/items` | Remove an item from the cart |
| `POST` | `/api/cart/{login_id}/pay` | Pay pending cart items |
| `POST` | `/api/cart/{login_id}/appointments` | Schedule a pickup appointment |
| `PUT` | `/api/cart/{login_id}/appointments/{id}` | Reschedule an appointment |
| `DELETE` | `/api/cart/{login_id}/appointments/{id}` | Cancel an appointment |

#### Other

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/history` | List won auctions |
| `POST` | `/api/history/refresh` | Refresh won-auction history from BuyWander |
| `GET` | `/api/settings` | Get user settings |
| `PUT` | `/api/settings` | Update user settings |
| `GET` | `/api/logins` | List BuyWander logins |
| `POST` | `/api/logins` | Add a BuyWander login |
| `PUT` | `/api/logins/{id}` | Update a login (enable/disable) |
| `DELETE` | `/api/logins/{id}` | Remove a login |
| `GET` | `/api/price-compare?q=` | Google Shopping price lookup (rate-limited: 30/min) |
| `GET` | `/api/events/{login_id}` | Event log for a login |
| `GET` | `/health` | Health check (returns worker and WS connection counts) |

### WebSocket

Connect to `/ws` and immediately send an auth message:

```json
{ "type": "auth", "token": "<access_token>" }
```

The server responds with `{ "type": "auth_ok" }`. After that you'll receive push events:

```json
{ "type": "snipe.status_changed", "data": { "snipe_id": "...", "status": "Won", "final_price": 12.50 } }
{ "type": "snipe.won",            "data": { "snipe_id": "...", "title": "...", "final_price": 12.50 } }
{ "type": "snipe.fired",          "data": { "snipe_id": "...", "bid_amount": 25.00, "title": "..." } }
{ "type": "log.event",            "data": { "message": "...", "event_type": "bid", "snipe_id": "..." } }
```

Send `{ "type": "ping" }` periodically to keep the connection alive through proxies.

---

## Snipe Lifecycle

```
URL submitted
      │
      ▼
  [Loading]  ── worker fetches initial auction state
      │
      ▼
  [Watching] ── poll loop running
      │             │
      │       secs_left > 120   → poll every 60s
      │       secs_left ≤ 120   → poll every 5s
      │       secs_left ≤ snipe_seconds + 5  → poll every 0.5s
      │
      ├── secs_left ≤ snipe_seconds ──► bid submitted
      │                                      │
      │                               [Sniped]
      │                                      │
      │                               auction ends
      │                                   /   \
      │                               [Won]   [Lost]
      │
      └── auction ends before snipe window ──► [Ended]

Any unrecoverable error ──► [Error]
User cancels             ──► [Deleted]
```

The worker fires the bid exactly once. After firing, it continues polling until the auction ends to determine Won/Lost.

---

## Data & Security

### What is stored locally

| Data | Storage | Protection |
|---|---|---|
| BwSniper passwords | SQLite (bcrypt hash, cost 12) | Never stored in plaintext |
| BuyWander passwords | SQLite (`encrypted_password` column) | Fernet symmetric encryption |
| BuyWander session cookies | SQLite (`encrypted_cookies` column) | Fernet symmetric encryption |
| JWT signing key | `/backend/data/secret.key` | `chmod 600` on creation |
| Fernet encryption key | `/backend/data/fernet.key` | `chmod 600` on creation |
| Auction/snipe data | SQLite | Unencrypted (not sensitive) |

### Security measures

- **Bcrypt** with cost factor 12 for all BwSniper account passwords
- **Timing-safe login** — bcrypt is always run (with a dummy hash when the user doesn't exist) to prevent email enumeration via response timing
- **JWT access tokens** expire after 24 hours; **refresh tokens** are single-use with rotation — the old token is revoked when a new one is issued
- **Expired and revoked refresh tokens** are automatically purged from the database every 5 minutes
- **Rate limiting** on auth endpoints (register: 10/min, login: 20/min, price-compare: 30/min) via slowapi
- **CORS** restricted to configured origins
- **Input validation** — sort_by allowlist, page_size cap (max 100), password minimum length (8 chars), display name max length
- **Error messages** — internal exceptions are logged server-side but not returned to clients; generic 502 messages are sent instead

### Backing up your data

The entire database and encryption keys live in the Docker volume `bwsniper_backend-data` (mounted at `/backend/data`). Back it up with:

```bash
# Create a tar archive of the volume
docker run --rm \
  -v bwsniper_backend-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/bwsniper-backup-$(date +%Y%m%d).tar.gz -C /data .
```

**Important:** If you lose `fernet.key`, stored BuyWander passwords and cookies become unreadable. Always back up the data volume or set `FERNET_KEY` explicitly in your `.env`.

---

## Troubleshooting

### The app shows "BuyWander login not found"
Your BW session cookies may have expired. Go to **Settings → BuyWander Accounts**, remove the account, and re-add it to refresh the session.

### Snipes are stuck in "Loading"
The worker couldn't reach the BuyWander API. Check the **Log** page for the specific error. Common causes: the auction URL is invalid, the auction has already ended, or your BW session has expired.

### Price comparison shows "Add a serper.dev API key"
Set `SERPER_API_KEY` in your `.env` file and restart the backend container. Free API keys are available at [serper.dev](https://serper.dev).

### The frontend can't reach the backend (CORS errors in browser console)
Set `CORS_ORIGINS` to the URL your browser uses to access the app. For example, if you're accessing it at `http://192.168.1.100`, set `CORS_ORIGINS=http://192.168.1.100`.

### I get "Card auth required" on a snipe
BuyWander is asking you to re-verify your payment method. Open the auction in your browser, log in, and complete the card verification prompt.

### Appointments or cart operations fail with 502
BuyWander's appointment and cart APIs can be finicky. Check the backend logs (`docker compose logs backend`) for the raw error from BuyWander. Session expiry is the most common cause — re-add your BW login in Settings.

### The database is locked / "unable to open database file"
Ensure the data volume is correctly mounted and the container has write permission. If running multiple backend instances (high `WEB_CONCURRENCY`), SQLite's WAL mode handles concurrent reads well but intensive write bursts may cause contention. Consider switching to PostgreSQL for high-volume use.

---

## Project Structure

```
bwsniper/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routers (auth, snipes, auctions, cart, …)
│   │   ├── db/             # SQLAlchemy models, schemas, session factory
│   │   ├── services/       # Business logic (snipe_service, auction_worker, buywander_api, …)
│   │   ├── utils/          # JWT, Fernet crypto, retry decorator
│   │   ├── websocket/      # ConnectionManager
│   │   ├── config.py       # Settings from environment
│   │   └── main.py         # FastAPI app, lifespan, CORS, rate limiting
│   ├── Dockerfile
│   ├── .dockerignore
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── context/        # AuthContext (global auth state)
│   │   ├── hooks/          # useApi, useWebSocket
│   │   ├── pages/          # Dashboard, Browse, History, Cart, Settings, Log, Login
│   │   ├── utils/          # images.js (shared image helper)
│   │   └── App.jsx         # Router + ProtectedRoute
│   ├── nginx.conf          # Production nginx site config
│   ├── Dockerfile
│   ├── .dockerignore
│   └── package.json
├── docker-compose.yml
├── .env.example
└── README.md
```
