FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash app

WORKDIR /agent

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r /tmp/requirements.txt

COPY backend/app /agent/app
COPY agent/remote_agent /agent/remote_agent

RUN chown -R app:app /agent

USER app

CMD ["python", "-m", "remote_agent.main"]
