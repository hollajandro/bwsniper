# SQLite to PostgreSQL Migration Guide

This guide explains how to migrate your existing BwSniper installation from SQLite to the new PostgreSQL + Redis architecture.

## Overview

The new Docker Compose setup includes:
- **PostgreSQL 16** - Primary database (replaces SQLite)
- **Redis 7** - Caching and job queue
- **Automated migration tool** - Transfers your data automatically

## Prerequisites

- Docker and Docker Compose installed
- Your existing `backend/data/app.db` SQLite file
- Your existing `backend/data/fernet.key` encryption key (critical!)

## Migration Steps

### Step 1: Backup Your Data

Before starting, create backups of your existing files:

```bash
cd /path/to/your/bwsniper
cp backend/data/app.db backend/data/app.db.backup
cp backend/data/fernet.key backend/data/fernet.key.backup
```

⚠️ **IMPORTANT**: Keep `fernet.key` safe! Without it, you cannot decrypt your stored BuyWander credentials.

### Step 2: Prepare the Environment

Create your `.env` file with required secrets:

```bash
cp .env.example .env

# Generate SECRET_KEY
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))" >> .env

# Copy your existing FERNET_KEY (or generate new if fresh install)
echo "FERNET_KEY=$(cat backend/data/fernet.key)" >> .env

# Set secure PostgreSQL password
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(32))" >> .env
```

Edit `.env` to add your BuyWander credentials if needed:
```bash
BW_USERNAME=your_username
BW_PASSWORD=your_password
```

### Step 3: Start Database Services Only

Start only PostgreSQL and Redis first:

```bash
docker compose up -d db redis
```

Wait for them to be healthy (about 15-30 seconds):

```bash
docker compose ps
# Both db and redis should show "healthy"
```

### Step 4: Run the Migration

**Option A: If you have the old SQLite files on the host machine**

Mount your old data directory and run the migration:

```bash
docker compose run --rm \
  -v /path/to/your/OLD/backend/data:/mnt/sqlite:ro \
  db-migration
```

Replace `/path/to/your/OLD/backend/data` with the actual path to your existing SQLite database directory.

**Option B: If you've already copied files to the volume**

If you previously copied your SQLite DB and fernet.key to the `backend-data` volume:

```bash
docker compose run --rm db-migration
```

### Step 5: Verify Migration

The migration script will output progress like:

```
🚀 BwSniper SQLite → PostgreSQL Migration Tool
==================================================
✅ Found SQLite database at /app/backend/data/app.db
🔗 Connecting to PostgreSQL...
✅ Connected to PostgreSQL successfully
💾 Backed up SQLite DB to /app/backend/data/app.db.backup
⚙️  Running Alembic migrations on PostgreSQL...
✅ Alembic migrations completed
🔄 Starting data migration...
  • Migrating table: users...
    ✅ Migrated 1 rows
  • Migrating table: buywander_logins...
    ✅ Migrated 2 rows
  • Migrating table: snipes...
    ✅ Migrated 5 rows
🎉 Migration complete! Total rows migrated: 8
✅ Migration marker created at /app/backend/data/.migration_complete
==================================================
✅ Migration finished successfully!
ℹ️  You can now start the full stack with: docker compose up -d
```

### Step 6: Start Full Stack

Once migration completes successfully:

```bash
docker compose up -d
```

This starts all services (db, redis, backend, frontend).

### Step 7: Verify Everything Works

Check service status:

```bash
docker compose ps
```

All services should show "Up" and "healthy".

View logs:

```bash
docker compose logs -f backend
```

Access the application:
- **Frontend**: http://localhost
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## Troubleshooting

### Migration fails with "database is locked"

Ensure no other process is using the SQLite file:
```bash
lsof /path/to/app.db
# Kill any processes using it
```

### Migration fails with "connection refused" to PostgreSQL

Wait longer for PostgreSQL to start:
```bash
docker compose logs db
# Wait until you see "database system is ready to accept connections"
```

### Lost fernet.key

If you lost your `fernet.key`, you cannot decrypt existing BuyWander credentials. You'll need to:
1. Re-enter your BuyWander username/password in the UI
2. The system will encrypt them with the new key

### Check what was migrated

Connect to PostgreSQL and inspect:
```bash
docker compose exec db psql -U bwsniper -d bwsniper -c "SELECT * FROM users;"
docker compose exec db psql -U bwsniper -d bwsniper -c "SELECT COUNT(*) FROM snipes;"
```

## Rollback (if needed)

If something goes wrong, you can rollback to SQLite:

1. Stop all containers:
   ```bash
   docker compose down
   ```

2. Restore your backup:
   ```bash
   cp backend/data/app.db.backup backend/data/app.db
   ```

3. Use the old single-container setup (if you have it backed up)

## Post-Migration Cleanup

After confirming everything works:

1. Your old SQLite file is preserved at `backend-data/app.db.backup` inside the volume
2. You can remove the migration service from `docker-compose.yml` if desired
3. Consider backing up the new PostgreSQL volume periodically

## Architecture Changes

| Component | Before | After |
|-----------|--------|-------|
| Database | SQLite file | PostgreSQL 16 |
| Cache | None | Redis 7 |
| Workers | In-process threads | Redis-backed queue (future) |
| Scaling | Single container | Multi-container, horizontally scalable |

## Next Steps

- Set up automated PostgreSQL backups
- Configure monitoring (Prometheus metrics available at `/metrics`)
- Enable OpenTelemetry tracing if desired
- Review security settings in `.env`

---

**Need help?** Check the logs:
```bash
docker compose logs db-migration
docker compose logs backend
```
