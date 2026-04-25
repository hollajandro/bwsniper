# BwSniper - Docker Deployment Guide

## Quick Start

```bash
# 1. Clone and configure
git clone <your-repo>
cd bwsniper
cp .env.example .env

# 2. Generate secure keys
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))" >> .env
python -c "from cryptography.fernet import Fernet; print('FERNET_KEY=' + Fernet.generate_key().decode())" >> .env

# 3. Start all services
docker compose up -d

# 4. Access the application
# Frontend: http://localhost
# API: http://localhost:8000
# Health check: http://localhost:8000/health
```

## Architecture

The Docker Compose stack includes:

| Service | Image | Purpose | Port |
|---------|-------|---------|------|
| `db` | postgres:16-alpine | PostgreSQL database | Internal |
| `redis` | redis:7-alpine | Cache & job queue | Internal |
| `backend` | Custom build | FastAPI application | 8000 |
| `frontend` | Custom build | React + Nginx | 80 |
| `remote-agent` | Custom build | Optional redundant snipe executor | Internal |

### Data Persistence

Three named volumes ensure data survives container restarts:

- `postgres-data` - PostgreSQL database files
- `redis-data` - Redis persistence (AOF)
- `backend-data` - Fernet key and application data

## Configuration

### Required Environment Variables

Edit `.env` with your values:

```bash
# Security keys (REQUIRED - generate new ones!)
SECRET_KEY=your-secret-key-here
FERNET_KEY=your-fernet-key-here

# Database password
POSTGRES_PASSWORD=bwsniper123
```

### Optional Environment Variables

```bash
# Web UI port (default: 80)
WEB_PORT=80

# CORS origins (comma-separated)
CORS_ORIGINS=http://localhost,https://yourdomain.com

# Uvicorn workers (default: 2)
WEB_CONCURRENCY=2

# Log level
LOG_LEVEL=INFO

# OpenTelemetry exporter
OTEL_EXPORTER_ENDPOINT=http://jaeger:4317

# Serper.dev API key for price comparison
SERPER_API_KEY=your-serper-key

# Optional remote redundancy agent
MAIN_BACKEND_URL=https://your-main-backend.example.com
REMOTE_AGENT_ID=agent-id-from-admin
REMOTE_AGENT_API_KEY=one-time-key-from-admin
REMOTE_AGENT_POLL_INTERVAL_MS=3000
```

## Remote Redundancy Agent

The remote agent is an optional backup bidder that can run in a different location from the main backend. It polls the backend for snipes assigned to its agent ID, attempts the same bid at the scheduled snipe time, and reports success, failures, clock offset, and last-seen health back to the backend.

### Provision an Agent

1. Start the main stack with `docker compose up -d`.
2. Sign in as an admin and open the existing Admin page.
3. In `Remote Agents`, create an agent with a name and region.
4. Copy the one-time API key immediately. The key is never shown again.
5. On the remote host, set `MAIN_BACKEND_URL`, `REMOTE_AGENT_ID`, and `REMOTE_AGENT_API_KEY`.
6. Start the agent with `docker compose --profile redundancy up -d remote-agent`.

If the key is lost or exposed, use `Rotate Key` in Admin, update `REMOTE_AGENT_API_KEY` on the remote host, and restart the agent.

### Assign Users

Remote redundancy is enabled per user, not globally. In Admin, select a remote agent in the user's `Remote Agent` column, then enable the user's `Redundancy` toggle. Disabling redundancy leaves the agent assignment saved so it can be re-enabled quickly later.

### Health and Errors

The Admin page shows each agent's enabled state, `last_seen_at`, `clock_offset_ms`, and `last_error`. Use the manual Refresh button to reload current health. Agent health does not block normal admin user management; if agent loading fails, the user table remains usable.

### Running the Agent Remotely

For a true redundant location, run the `remote-agent` service on separate infrastructure and set `MAIN_BACKEND_URL` to the public HTTPS URL of the main backend. The bundled Compose service is useful for local smoke tests and for hosts that can reach the backend over the Compose network.

```bash
# Build the image locally
docker compose build remote-agent

# Run the optional service
docker compose --profile redundancy up -d remote-agent

# View agent logs
docker compose logs -f remote-agent
```

## Common Operations

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f db
docker compose logs -f redis
```

### Restart Services

```bash
# Restart all
docker compose restart

# Restart specific service
docker compose restart backend
```

### Stop and Remove

```bash
# Stop all services
docker compose down

# Stop and remove volumes (⚠️ deletes all data!)
docker compose down -v
```

### Database Migrations

Migrations run automatically on startup via `alembic upgrade head`. To run manually:

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
```

### Backup Database

```bash
# Create backup
docker compose exec db pg_dump -U bwsniper bwsniper > backup.sql

# Restore from backup
cat backup.sql | docker compose exec -T db psql -U bwsniper bwsniper
```

### Update Application

```bash
# Pull latest changes
git pull origin main

# Rebuild and restart
docker compose build --no-cache
docker compose up -d
```

## Health Checks

All services include health checks:

```bash
# Check status
docker compose ps

# Expected output:
# NAME            STATUS                    PORTS
# bwsniper-api    Up (healthy)              0.0.0.0:8000->8000/tcp
# bwsniper-db     Up (healthy)              
# bwsniper-redis  Up (healthy)              
# bwsniper-web    Up (healthy)              0.0.0.0:80->80/tcp
```

## Troubleshooting

### Backend Won't Start

1. Check logs: `docker compose logs backend`
2. Verify database is healthy: `docker compose ps db`
3. Test DB connection: `docker compose exec db pg_isready -U bwsniper`

### Database Connection Errors

Ensure the database password in `.env` matches what's in `docker-compose.yml`:

```bash
grep POSTGRES_PASSWORD .env
grep POSTGRES_PASSWORD docker-compose.yml
```

### Port Already in Use

Change the web port in `.env`:

```bash
WEB_PORT=8080
```

Then restart: `docker compose up -d`

### Reset Everything

⚠️ **Warning: This deletes all data!**

```bash
docker compose down -v
rm -f .env
cp .env.example .env
# Reconfigure .env with new keys
docker compose up -d
```

## Production Considerations

### Security Hardening

1. **Use strong passwords**: Generate random passwords for `POSTGRES_PASSWORD`
2. **Restrict CORS**: Set `CORS_ORIGINS` to your actual domain
3. **Use HTTPS**: Place a reverse proxy (nginx/traefik) in front for TLS termination
4. **Network isolation**: The default setup already isolates services on internal network

### Scaling

- Increase `WEB_CONCURRENCY` based on CPU cores (rule: 2× cores + 1)
- For high availability, deploy multiple backend instances behind a load balancer
- Consider external managed PostgreSQL (RDS, Cloud SQL) for production

### Monitoring

Enable OpenTelemetry by setting:

```bash
OTEL_EXPORTER_ENDPOINT=http://your-otel-collector:4317
```

Metrics are available at: `http://localhost:8000/metrics`

## GHCR Image Publishing

The GitHub Actions workflow automatically builds and publishes to GHCR:

```bash
# Pull the published image
docker pull ghcr.io/<your-username>/bwsniper:latest

# Run with published image
docker compose -f docker-compose.prod.yml up -d
```

See `.github/workflows/docker-publish.yml` for configuration.

---

**Need help?** Check the main [README.md](../README.md) or open an issue.
