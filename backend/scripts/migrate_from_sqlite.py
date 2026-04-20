#!/usr/bin/env python3
"""
Automated migration script from SQLite to PostgreSQL.
Usage: docker compose run --rm db-migration
       python migrate_from_sqlite.py --sqlite-db /path/to/app.db --target-db postgresql://...
"""

import os
import sys
import json
import shutil
import argparse
from datetime import datetime, timezone
from sqlalchemy import create_engine, MetaData, Table, select, inspect
from sqlalchemy.orm import sessionmaker
from alembic.config import Config
from alembic import command

# Default Configuration
DEFAULT_SQLITE_PATH = "/app/backend/data/app.db"
DEFAULT_SQLITE_BACKUP_PATH = "/app/backend/data/app.db.backup"
DEFAULT_POSTGRES_URL = os.getenv("DATABASE_URL", "postgresql://bwsniper:bwsniper@postgres:5432/bwsniper")

def get_sqlite_engine(sqlite_path):
    if not os.path.exists(sqlite_path):
        print(f"❌ SQLite database not found at {sqlite_path}")
        print("✅ No migration needed (fresh install).")
        return None
    
    print(f"✅ Found SQLite database at {sqlite_path}")
    return create_engine(f"sqlite:///{sqlite_path}")

def get_postgres_engine(postgres_url):
    print(f"🔗 Connecting to PostgreSQL...")
    engine = create_engine(postgres_url)
    try:
        with engine.connect() as conn:
            conn.execute(select(1))
        print("✅ Connected to PostgreSQL successfully")
        return engine
    except Exception as e:
        print(f"❌ Failed to connect to PostgreSQL: {e}")
        sys.exit(1)

def backup_sqlite(sqlite_path, backup_path):
    if os.path.exists(sqlite_path):
        # Ensure backup directory exists
        backup_dir = os.path.dirname(backup_path)
        if backup_dir:
            os.makedirs(backup_dir, exist_ok=True)
        shutil.copy2(sqlite_path, backup_path)
        print(f"💾 Backed up SQLite DB to {backup_path}")

def run_alembic_upgrade(pg_engine, postgres_url, alembic_ini_path="/backend/alembic.ini"):
    print("⚙️  Running Alembic migrations on PostgreSQL...")
    
    # Handle case where alembic.ini doesn't exist (local testing)
    if not os.path.exists(alembic_ini_path):
        print("ℹ️  Alembic config not found at {alembic_ini_path}, skipping migrations")
        print("🔧 Try running: docker compose run --rm backend alembic upgrade head")
        return
    
    alembic_cfg = Config(alembic_ini_path)
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
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
            try:
                pg_table = Table(table_name, pg_metadata, autoload_with=pg_engine)
            except Exception as e:
                print(f"    ⚠️  Table {table_name} doesn't exist in target yet, skipping (run migrations first)")
                continue
            
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

def mark_migration_complete(marker_path="/app/backend/data/.migration_complete"):
    marker_file = marker_path
    os.makedirs(os.path.dirname(marker_file), exist_ok=True)
    with open(marker_file, 'w') as f:
        f.write(datetime.now(timezone.utc).isoformat())
    print(f"✅ Migration marker created at {marker_file}")

def main():
    parser = argparse.ArgumentParser(description="Migrate BwSniper data from SQLite to PostgreSQL")
    parser.add_argument("--sqlite-db", type=str, default=DEFAULT_SQLITE_PATH,
                        help=f"Path to SQLite database (default: {DEFAULT_SQLITE_PATH})")
    parser.add_argument("--target-db", type=str, default=DEFAULT_POSTGRES_URL,
                        help=f"PostgreSQL connection URL (default: {DEFAULT_POSTGRES_URL})")
    parser.add_argument("--backup-path", type=str, default=DEFAULT_SQLITE_BACKUP_PATH,
                        help=f"Path for SQLite backup (default: {DEFAULT_SQLITE_BACKUP_PATH})")
    parser.add_argument("--alembic-ini", type=str, default="/app/backend/alembic.ini",
                        help="Path to alembic.ini file")
    parser.add_argument("--marker-path", type=str, default="/app/backend/data/.migration_complete",
                        help="Path for migration completion marker")
    parser.add_argument("--dry-run", action="store_true",
                        help="Check if migration is needed without performing it")
    
    args = parser.parse_args()
    
    print("🚀 BwSniper SQLite → PostgreSQL Migration Tool")
    print("=" * 50)
    
    sqlite_engine = get_sqlite_engine(args.sqlite_db)
    if not sqlite_engine:
        return 0
    
    if args.dry_run:
        print("ℹ️  Dry run mode - no changes will be made")
        print("✅ Migration would proceed with:")
        print(f"   • SQLite: {args.sqlite_db}")
        print(f"   • PostgreSQL: {args.target_db}")
        return 0
    
    pg_engine = get_postgres_engine(args.target_db)
    
    backup_sqlite(args.sqlite_db, args.backup_path)
    run_alembic_upgrade(pg_engine, args.target_db, args.alembic_ini)
    migrate_data(sqlite_engine, pg_engine)
    mark_migration_complete(args.marker_path)
    
    print("=" * 50)
    print("✅ Migration finished successfully!")
    print("ℹ️  You can now start the full stack with: docker compose up -d")
    return 0

if __name__ == "__main__":
    sys.exit(main())
