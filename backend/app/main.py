"""
backend/app/main.py — FastAPI application factory.

Startup:
    1. Initialize OpenTelemetry tracing and Prometheus metrics
    2. Create database tables via Alembic migrations
    3. Restart workers for any non-terminal snipes
    4. Include all routers

Shutdown:
    1. Stop all auction workers gracefully
    2. Shutdown telemetry
"""

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# OpenTelemetry instrumentation
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Prometheus metrics
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from .api.auth import limiter
from .db.database import init_db, SessionLocal
from .api.router import api_router, ws_router
from .config import (
    CORS_ORIGINS,
    CLEANUP_INTERVAL_SEC,
    TOKEN_PURGE_INTERVAL_ITER,
    SESSION_REFRESH_INTERVAL_ITER,
)
from .services.snipe_service import restart_active_snipes
from .services.worker_pool import pool
from .services import keyword_watcher
from .services.notification_service import _retry_queued_notifications
from .websocket.manager import ws_manager

# ── Metrics & Tracing Globals ────────────────────────────────────────────────
SNIPES_FIRED = Counter("bwsniper_snipes_fired_total", "Total number of snipes fired")
SNIPES_WON = Counter("bwsniper_snipes_won_total", "Total number of snipes won")
SNIPES_LOST = Counter("bwsniper_snipes_lost_total", "Total number of snipes lost")
BID_LATENCY = Histogram("bwsniper_bid_latency_seconds", "Bid submission latency")

tracer = None
meter = None


def init_telemetry():
    """Initialize OpenTelemetry tracing if OTEL_EXPORTER_ENDPOINT is set."""
    global tracer, meter

    resource = Resource.create({"service.name": "bwsniper-backend"})

    # Tracing
    trace.set_tracer_provider(TracerProvider(resource=resource))
    otel_endpoint = os.getenv("OTEL_EXPORTER_ENDPOINT")
    if otel_endpoint:
        span_processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=otel_endpoint))
        trace.get_tracer_provider().add_span_processor(span_processor)

    tracer = trace.get_tracer(__name__)

    # Metrics
    metrics.set_meter_provider(MeterProvider(resource=resource))
    meter = metrics.get_meter(__name__)


async def _cleanup_loop():
    """Periodically remove finished AuctionWorker threads from the pool,
    purge expired/revoked refresh tokens, proactively refresh BW sessions,
    and retry queued notifications."""
    import asyncio as _asyncio
    import logging as _logging
    from datetime import datetime, timezone
    from .db.models import RefreshToken, BuyWanderLogin
    from .services.auth_service import reauth_bw_login

    _logger = _logging.getLogger(__name__)
    _purge_counter = 0
    _session_refresh_counter = 0
    _notif_retry_counter = 0

    while True:
        await _asyncio.sleep(CLEANUP_INTERVAL_SEC)
        pool.cleanup_dead()
        _purge_counter += 1
        _session_refresh_counter += 1
        _notif_retry_counter += 1

        if _purge_counter >= TOKEN_PURGE_INTERVAL_ITER:
            _purge_counter = 0
            try:
                db = SessionLocal()
                now = datetime.now(timezone.utc)
                db.query(RefreshToken).filter(
                    (RefreshToken.expires_at < now) | (RefreshToken.revoked == True)  # noqa: E712
                ).delete(synchronize_session=False)
                db.commit()
            except Exception:
                pass
            finally:
                db.close()

        if _session_refresh_counter >= SESSION_REFRESH_INTERVAL_ITER:
            _session_refresh_counter = 0
            db = SessionLocal()
            try:
                logins = (
                    db.query(BuyWanderLogin)
                    .filter(
                        BuyWanderLogin.is_active == True  # noqa: E712
                    )
                    .all()
                )
            except Exception as ex:
                _logger.warning("Failed to query logins for session refresh: %s", ex)
                logins = []
            finally:
                db.close()

            # Refresh each login independently — one failure doesn't affect others.
            for login in logins:
                db = SessionLocal()
                try:
                    reauth_bw_login(login, db)
                    _logger.info("Session refreshed for %s", login.bw_email)
                except Exception as ex:
                    _logger.warning(
                        "Proactive session refresh failed for %s: %s",
                        login.bw_email,
                        ex,
                    )
                finally:
                    db.close()

        # Retry queued notifications every cleanup cycle
        if _notif_retry_counter >= 1:
            _notif_retry_counter = 0
            try:
                _retry_queued_notifications()
            except Exception as ex:
                _logger.warning("Notification queue retry failed: %s", ex)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio as _asyncio

    # ── Startup ──────────────────────────────────────────────────────────────
    init_telemetry()
    init_db()

    # Give the WebSocket manager a reference to the running event loop so that
    # background AuctionWorker threads can safely schedule WS broadcasts.
    ws_manager.set_loop(_asyncio.get_running_loop())

    # Restart workers for any snipes that were active before shutdown
    db = SessionLocal()
    try:
        restart_active_snipes(db, ws_manager=ws_manager)
    finally:
        db.close()

    # Background task: prune dead worker threads from the pool every 60s
    cleanup_task = _asyncio.create_task(_cleanup_loop())

    # Start keyword watch scanner
    keyword_watcher.start()

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    cleanup_task.cancel()
    keyword_watcher.stop()
    stopped = pool.stop_all()
    if stopped:
        print(f"Stopped {stopped} auction worker(s).")


app = FastAPI(
    title="BuyWander Sniper API",
    version="2.0.0",
    lifespan=lifespan,
)

# Instrument FastAPI with OpenTelemetry (auto-traces all requests)
FastAPIInstrumentor.instrument_app(app)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)

# CORS — controlled via CORS_ORIGINS env var (see config.py)
if "*" in CORS_ORIGINS:
    raise ValueError(
        "CORS_ORIGINS contains '*' (wildcard). "
        "Wildcard origins are incompatible with allow_credentials=True. "
        "Set explicit origins in CORS_ORIGINS instead."
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ws_router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "active_workers": pool.active_count(),
        "ws_connections": ws_manager.connection_count(),
    }


@app.get("/metrics")
def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
