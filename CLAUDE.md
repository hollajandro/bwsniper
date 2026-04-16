# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BwSniper is a self-hosted auction sniping tool for BuyWander. It consists of three components:
- **Backend** — FastAPI + SQLite, runs auction workers as background threads
- **Frontend** — React 18 + Vite + Tailwind CSS SPA
- **CLI** — Textual TUI (separate Python package, less actively developed)

## Development Commands

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# or
python run.py
```

### Frontend
```bash
cd frontend
npm install
npm run dev        # dev server on :3000, proxies /api → :8000
npm run build      # production build to dist/
npm run preview    # preview production build
```

### Docker (full stack)
```bash
cp .env.example .env   # set SECRET_KEY and FERNET_KEY at minimum
docker compose up -d
# App runs on :80; backend API on :8000 internally
```

## Architecture

### Backend — `backend/app/`

**Request flow**: `main.py` → `api/router.py` → individual route modules → services/db

**Key services:**
- `services/auction_worker.py` — each `AuctionWorker` is a `threading.Thread` that polls BuyWander for an auction's state and fires a bid at the configured `snipe_seconds` before end. Workers use `run_coroutine_threadsafe` to push WebSocket events onto the main event loop.
- `services/worker_pool.py` — manages the pool; workers are restarted on app startup for active snipes.
- `services/buywander_api.py` — all HTTP calls to BuyWander's API. BW credentials are decrypted per-request via Fernet.
- `services/keyword_watcher.py` — background thread scanning new auctions against user keyword lists every 5 minutes.
- `websocket/manager.py` — `ConnectionManager` tracks per-user WebSocket connections; broadcasts typed messages (`snipe.status_changed`, `snipe.won`, `log.event`).

**Auth**: JWT access tokens (24h) + single-use rotating refresh tokens (30d). `dependencies.py` provides `get_current_user` FastAPI dependency. Admin endpoints use a separate `get_admin_user` dependency.

**Encryption**: BuyWander passwords are encrypted with Fernet before storage. The key is auto-generated to `backend/data/fernet.key` on first run if `FERNET_KEY` env var is not set.

**Database**: SQLite with WAL mode. Schema is in `db/models.py`; Pydantic schemas in `db/schemas.py`. `init_db()` runs migrations inline (ALTER TABLE guards with try/except).

### Frontend — `frontend/src/`

**Auth flow**: `AuthContext.jsx` stores JWTs in `localStorage` (`bw_access_token`, `bw_refresh_token`). `useApi.js` wraps all fetch calls — on 401, it transparently refreshes the token (module-level `refreshInProgress` lock prevents concurrent refresh races) and retries.

**Real-time updates**: `useWebSocket.js` maintains a WebSocket to `/api/ws?token=<access_token>` with exponential backoff reconnect. Consumers pass a callback via `useWebSocket(handler)`.

**Error display**: Use the exported `fmtApiError(err, fallback)` from `useApi.js` to format FastAPI error responses (`{ detail: string | array | object }`). Never use `err.detail` directly.

**Design system** (defined in `tailwind.config.js` + `src/styles/globals.css`):
- Color tokens: `bw-blue` (#7c6ff7), `bw-green` (#4ade80), `bw-red` (#f87171), `bw-yellow` (#fbbf24); the gray palette is purple-tinted
- Component classes: `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-ghost`, `.btn-danger`, `.field`, `.card`, `.card-elevated`, `.mat-table`, `.badge`
- Always use design tokens — never raw Tailwind color classes like `text-blue-400`, `bg-green-600`
- Custom animations: `.animate-bounce-once`, `.animate-pulse-once` are defined in globals.css

**Page → API mapping:**
| Page | Primary endpoints |
|------|------------------|
| Dashboard | `GET/POST/PUT/DELETE /snipes`, WebSocket |
| Browse | `GET /auctions`, `GET /auctions/{id}`, `POST /watchlist` |
| Cart | `GET/POST /cart`, `POST /cart/pay`, `GET/POST /cart/appointments` |
| History | `GET/POST /history` |
| Settings | `GET/PUT /settings`, `GET/POST/DELETE /logins` |
| Log | `GET /events`, WebSocket |
| Admin | `GET/POST/PATCH/DELETE /admin/users` |

## Configuration

Copy `backend/.env.example` to `backend/.env`. Key variables:
- `DATABASE_URL` — defaults to `sqlite:///./data/bwsniper.db`
- `SECRET_KEY` — JWT signing key (required, min 32 chars)
- `FERNET_KEY` — Fernet key for BW credential encryption (auto-generated if omitted)
- `SERPER_API_KEY` — optional, enables Google Shopping price comparison

The frontend Vite dev server proxies `/api` to `http://localhost:8000` (configured in `vite.config.js`).
