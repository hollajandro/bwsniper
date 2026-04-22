"""
backend/app/db/database.py — SQLAlchemy engine, session factory, and init.
"""

from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
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
        cursor.execute("PRAGMA cache_size=-8000")  # 8MB page cache (default is ~2MB)
        cursor.execute(
            "PRAGMA busy_timeout=5000"
        )  # Wait up to 5s on locks instead of failing immediately
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency — yields a DB session and auto-closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _short_database_url():
    return DATABASE_URL[:50] + "..." if len(DATABASE_URL) > 50 else DATABASE_URL


def _get_alembic_revision_state(
    db_engine=None,
    inspector_factory=inspect,
    alembic_config_cls=None,
    script_directory_cls=None,
):
    """Return whether the connected database matches the current Alembic head."""
    if alembic_config_cls is None or script_directory_cls is None:
        from alembic.config import Config as _AlembicConfig
        from alembic.script import ScriptDirectory as _ScriptDirectory

        alembic_config_cls = alembic_config_cls or _AlembicConfig
        script_directory_cls = script_directory_cls or _ScriptDirectory

    db_engine = db_engine or engine
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"

    try:
        with db_engine.connect() as conn:
            inspector = inspector_factory(conn)
            if not inspector.has_table("alembic_version"):
                return "missing", None

            current_versions = {
                row[0]
                for row in conn.execute(text("SELECT version_num FROM alembic_version"))
            }
    except Exception as ex:
        return "unknown", f"Failed to inspect migration state: {ex}"

    if not current_versions:
        return "missing", None

    try:
        alembic_config = alembic_config_cls(str(alembic_ini))
        alembic_config.set_main_option("sqlalchemy.url", DATABASE_URL)
        expected_heads = set(script_directory_cls.from_config(alembic_config).get_heads())
    except Exception as ex:
        return "unknown", f"Failed to load Alembic heads: {ex}"

    if current_versions == expected_heads:
        return "current", None

    return (
        "outdated",
        "Database revision(s) %s do not match Alembic head(s) %s."
        % (sorted(current_versions), sorted(expected_heads)),
    )


def _log_non_sqlite_migration_status():
    state, detail = _get_alembic_revision_state()
    database_url = _short_database_url()

    if state == "current":
        _logger.debug(
            "Alembic schema is current for non-SQLite database %s.",
            database_url,
        )
        return

    if state == "missing":
        _logger.warning(
            "No alembic_version table was found for non-SQLite database %s. "
            "Run 'alembic upgrade head' to apply migrations and stamp the schema.",
            database_url,
        )
        return

    if state == "outdated":
        _logger.warning(
            "Non-SQLite database %s is behind the current Alembic revision. %s "
            "Run 'alembic upgrade head' to update the schema.",
            database_url,
            detail,
        )
        return

    _logger.warning(
        "Could not verify Alembic migration status for non-SQLite database %s. %s",
        database_url,
        detail or "Run 'alembic upgrade head' if the schema may be stale.",
    )


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
        _log_non_sqlite_migration_status()
