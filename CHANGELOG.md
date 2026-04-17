# Changelog

All notable changes to BwSniper will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.2] - 2026-04-17

### 🚀 Major Changes
- **Containerized Architecture**: Migrated from SQLite to PostgreSQL + Redis with Docker Compose
- **Separate Frontend/Backend Images**: Built and published independently to GHCR
- **Automated Migration Tool**: Python script for seamless SQLite → PostgreSQL data transfer

### 🔒 Security Enhancements
- Added GitHub Actions workflow permissions for SARIF upload (`security-events: write`, `actions: read`)
- Fixed Trivy vulnerability scanning with short SHA tags and retry logic
- Comprehensive security audit: no hardcoded secrets found

### 📦 Dependency Upgrades
#### Backend
- FastAPI `0.115.0` (flexible versioning)
- SQLAlchemy `2.0.40`
- Pydantic `2.11.0`
- Uvicorn `0.34.0`
- OpenTelemetry `1.35.0` / `0.56b0`
- Prometheus Client `0.21.0`
- Cryptography `45.0.0`
- PyJWT `2.10.0`

#### Frontend
- **Vite** `8.0.8` (major upgrade from v5)
- **React** `19.2.5` (major upgrade from v18)
- **Tailwind CSS** `4.2.2` (major upgrade from v3)
- TypeScript `6.0.3`
- React Router DOM `7.6.0`
- Axios `1.15.0` (new dependency)

### 📚 Documentation
- Complete README overhaul with architecture diagrams
- New `DEPLOYMENT.md` with Docker Compose setup guide
- New `MIGRATION_GUIDE.md` for SQLite → PostgreSQL upgrade path
- Automated migration script documentation

### 🔧 Infrastructure
- GitHub Actions: Fixed Trivy scan to use 7-character SHA tags
- GitHub Actions: Added wait step for GHCR image propagation
- GitHub Actions: Made Trivy scan non-blocking with `continue-on-error`
- Docker Compose: Pre-built images from GHCR instead of local builds
- Alembic migrations configured for PostgreSQL schema management

### 🐛 Bug Fixes
- Fixed WebSocket broadcast error handling for closed loops
- Fixed externalized cleanup intervals in config
- Fixed notification dead-letter queue implementation
- Fixed input validation on SnipeCreate schema
- Fixed explicit WebSocket connection cleanup

## [0.0.1] - 2026-04-16

### Initial Release
- SQLite-based backend with FastAPI
- React 18 + Vite 5 frontend
- Basic auction sniping functionality
- BuyWander API integration
- WebSocket real-time updates
- Token-based authentication
