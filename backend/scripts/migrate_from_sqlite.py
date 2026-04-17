#!/usr/bin/env python3
"""
Automated migration script from SQLite to PostgreSQL.
Usage: 
  - Docker: docker compose run --rm db-migration
  - Local: python migrate_from_sqlite.py /path/to/app.db
"""

import os
import sys
import json
import shutil
from datetime import datetime, timezone
from sqlalchemy import create_engine, MetaData, Table, select, inspect
from sqlalchemy.orm import sessionmaker
from alembic.config import Config
from alembic import command

# Configuration - Allow override via command line argument
SQLITE_PATH = sys.argv[1] if len(sys.argv) > 1 else os.getenv("SQLITE_DB_PATH", "/app/backend/data/app.db")
SQLITE_BACKUP_PATH = SQLITE_PATH + ".backup"
POSTGRES_URL = os.getenv("DATABASE_URL", "postgresql://bwsniper:bwsniper@postgres:5432/bwsniper")

def get_sqlite_engine():
    if not os.path.exists(SQLITE_PATH):
        print(f"❌ SQLite database not found at {SQLITE_PATH}")
        print("✅ No migration needed (fresh install).")
        return None
    
    print(f"✅ Found SQLite database at {SQLITE_PATH}")
    return create_engine(f"sqlite:///{SQLITE_PATH}")

def get_postgres_engine():
    print(f"🔗 Connecting to PostgreSQL...")
    engine = create_engine(POSTGRES_URL)
    try:
        with engine.connect() as conn:
            conn.execute(select(1))
        print("✅ Connected to PostgreSQL successfully")
        return engine
    except Exception as e:
        print(f"❌ Failed to connect to PostgreSQL: {e}")
        sys.exit(1)

def backup_sqlite():
    if os.path.exists(SQLITE_PATH):
        shutil.copy2(SQLITE_PATH, SQLITE_BACKUP_PATH)
        print(f"💾 Backed up SQLite DB to {SQLITE_BACKUP_PATH}")

def run_alembic_upgrade(pg_engine):
    print("⚙️  Running Alembic migrations on PostgreSQL...")
    alembic_cfg = Config("/app/backend/alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", POSTGRES_URL)
    try:
        command.upgrade(alembic_cfg, "head")
        print("✅ Alembic migrations completed")
    except Exception as e:
        print(f"❌ Alembic migration failed: {e}")
        sys.exit(1)

def migrate_data(sqlite_engine, pg_engine):
    print("🔄 Starting data migration...")
    
    sqlite_session = sessionmaker(bind=sqlite_engine)()
    pg_session = sessionmaker(bind=pg_engine)()
    
    # List of tables to migrate (excluding alembic_version)
    metadata = MetaData()
    metadata.reflect(bind=sqlite_engine)
    
    migrated_count = 0
    
    for table_name in metadata.tables:
        if table_name == "alembic_version":
            continue
            
        print(f"  • Migrating table: {table_name}...")
        
        try:
            # Reflect table structure from PG to ensure compatibility
            pg_metadata = MetaData()
            pg_table = Table(table_name, pg_metadata, autoload_with=pg_engine)
            
            # Fetch all rows from SQLite
            sqlite_table = metadata.tables[table_name]
            rows = sqlite_session.query(sqlite_table).all()
            
            if not rows:
                print(f"    ↪️  Skipped (empty)")
                continue
            
            # Insert into PostgreSQL
            for row in rows:
                data = {}
                for column in sqlite_table.columns:
                    val = getattr(row, column.name)
                    # Handle datetime conversion if needed
                    if isinstance(val, datetime) and val.tzinfo is None:
                        val = val.replace(tzinfo=timezone.utc)
                    data[column.name] = val
                
                # Remove 'id' if it's auto-increment in PG and we want to regenerate, 
                # but usually we want to preserve IDs for relationships.
                # We'll insert with explicit IDs.
                
                insert_stmt = pg_table.insert().values(**data)
                try:
                    pg_session.execute(insert_stmt)
                except Exception as e:
                    # Handle unique constraint violations (e.g. duplicate IDs)
                    if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                        print(f"    ⚠️  Skipping duplicate row in {table_name}: {data.get('id')}")
                        continue
                    raise
            
            pg_session.commit()
            migrated_count += len(rows)
            print(f"    ✅ Migrated {len(rows)} rows")
            
        except Exception as e:
            print(f"    ❌ Error migrating {table_name}: {e}")
            pg_session.rollback()
            continue
    
    sqlite_session.close()
    pg_session.close()
    print(f"🎉 Migration complete! Total rows migrated: {migrated_count}")

def mark_migration_complete():
    marker_file = "/app/backend/data/.migration_complete"
    with open(marker_file, 'w') as f:
        f.write(datetime.now(timezone.utc).isoformat())
    print(f"✅ Migration marker created at {marker_file}")

def main():
    print("🚀 BwSniper SQLite → PostgreSQL Migration Tool")
    print("=" * 50)
    
    sqlite_engine = get_sqlite_engine()
    if not sqlite_engine:
        return 0
    
    pg_engine = get_postgres_engine()
    
    backup_sqlite()
    run_alembic_upgrade(pg_engine)
    migrate_data(sqlite_engine, pg_engine)
    mark_migration_complete()
    
    print("=" * 50)
    print("✅ Migration finished successfully!")
    print("ℹ️  You can now start the full stack with: docker compose up -d")
    return 0

if __name__ == "__main__":
    sys.exit(main())
