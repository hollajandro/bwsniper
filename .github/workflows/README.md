# Build & Publish Docker Images to GHCR

This repository uses GitHub Actions to automatically build and publish Docker images to the GitHub Container Registry (GHCR).

## Images

- **Backend**: `ghcr.io/<owner>/bwsniper-backend`
  - FastAPI backend with SQLite/PostgreSQL support
  - Includes Prometheus metrics and OpenTelemetry tracing
  - Multi-platform: `linux/amd64`, `linux/arm64`

## Automatic Builds

Images are built and pushed automatically on:

1. **Push to `main`/`master`**: Latest image with SHA tag
2. **Version tags** (`v1.2.3`): Semantic version tags
3. **Pull requests**: Build only (no push) for validation

## Image Tags

- `latest` - Latest build from main branch
- `sha-<commit>` - Specific commit SHA
- `v1.2.3` - Semantic version (on git tags)
- `v1.2` - Major.minor version

## Usage

### Pull the image

```bash
docker pull ghcr.io/<owner>/bwsniper-backend:latest
```

### Run with Docker

```bash
docker run -d \
  --name bwsniper \
  -p 8000:8000 \
  -e SECRET_KEY="your-secret-key" \
  -e CORS_ORIGINS="http://localhost" \
  -v bwsniper-data:/backend/data \
  ghcr.io/<owner>/bwsniper-backend:latest
```

### Docker Compose

```yaml
services:
  backend:
    image: ghcr.io/<owner>/bwsniper-backend:latest
    environment:
      SECRET_KEY: ${SECRET_KEY}
      FERNET_KEY: ${FERNET_KEY}
      CORS_ORIGINS: ${CORS_ORIGINS}
    volumes:
      - backend-data:/backend/data
    ports:
      - "8000:8000"

volumes:
  backend-data:
```

## Security Scanning

All images are automatically scanned with [Trivy](https://github.com/aquasecurity/trivy) for vulnerabilities. Results are uploaded to the GitHub Security tab.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | ✅ | JWT signing secret (generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`) |
| `FERNET_KEY` | ⚠️ | Encryption key for stored credentials (auto-generated if not set, but should be persisted) |
| `CORS_ORIGINS` | ✅ | Comma-separated list of allowed origins |
| `DATABASE_URL` | ❌ | Database URL (default: SQLite in `/backend/data`) |
| `WEB_CONCURRENCY` | ❌ | Number of Uvicorn workers (default: 2) |
| `SERPER_API_KEY` | ❌ | Serper.dev API key for price comparison |

## Manual Build & Push

If you need to manually build and push:

```bash
# Login to GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u <username> --password-stdin

# Build
docker build -t ghcr.io/<owner>/bwsniper-backend:latest ./backend

# Push
docker push ghcr.io/<owner>/bwsniper-backend:latest
```

## Package Settings

Ensure your GitHub repository has Packages permission enabled:

1. Go to **Settings** → **Actions** → **General**
2. Under **Workflow permissions**, select **Read and write permissions**
3. Enable **Allow GitHub Actions to create and approve pull requests**

For private repositories, users pulling images need at least `read` access to the package.
