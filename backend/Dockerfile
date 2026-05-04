FROM python:3.11.15-slim-bookworm

# --- system deps -----------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# --- non-root user ---------------------------------------------------------
RUN useradd --create-home --shell /bin/bash app

WORKDIR /backend

# --- Python deps (own layer for cache efficiency) --------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# --- application code ------------------------------------------------------
COPY . .

# Data directory is typically a mounted volume; create it so the container
# still starts even without a volume attached.
RUN mkdir -p data && chown -R app:app /backend

USER app

EXPOSE 8000

# Two uvicorn workers is a safe default for a container on a typical host.
# Set WEB_CONCURRENCY env var to override (e.g. WEB_CONCURRENCY=4).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-2}"]
