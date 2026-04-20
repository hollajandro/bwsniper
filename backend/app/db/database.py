"""
backend/app/db/database.py — SQLAlchemy engine, session factory, and init.
"""

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from ..config import DATABASE_URL

import logging as _logging

_logger = _logging.getLogger(__name__)

# SQLite needs check_same_thread=False for FastAPI multi-thread access
connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False,
    pool_pre_ping=True,
)

# Enable WAL mode and foreign keys for SQLite
if "sqlite" in DATABASE_URL:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")  # Safe with WAL, much faster writes
        cursor.execute("PRAGMA cache_size=-8000")     # 8MB page cache (default is ~2MB)
        cursor.execute("PRAGMA busy_timeout=5000")    # Wait up to 5s on locks instead of failing immediately
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency — yields a DB session and auto-closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables (safe to call multiple times)."""
    from .models import Base
    Base.metadata.create_all(bind=engine)
    # Add columns to existing SQLite databases that predate them.
    # Each ALTER TABLE is wrapped individually so one failure doesn't block the rest.
    if "sqlite" in DATABASE_URL:
        migrations = [
            "ALTER TABLE users  ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0",
            "ALTER TABLE snipes ADD COLUMN notify  BOOLEAN",
        ]
        with engine.connect() as conn:
            for sql in migrations:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception:
                    pass  # Column already exists
    else:
        # PostgreSQL (or other non-SQLite DB): Alembic or manual migrations
        # are required.  Log a warning so operators don't miss this.
        _logger.warning(
            "Running on a non-SQLite database (%s). "
            "Alembic migrations are not applied automatically. "
            "Run 'alembic upgrade head' or apply migrations manually to "
            "ensure schema is up to date.",
            DATABASE_URL[:50] + "..." if len(DATABASE_URL) > 50 else DATABASE_URL,
        )
