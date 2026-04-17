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
