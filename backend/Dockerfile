FROM python:3.14-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /usr/local/bin/uv

WORKDIR /app

# Install deps first (better layer caching). Copy the lock file alongside
# pyproject.toml and pass --locked so the build fails fast if the lock drifts
# — reproducible builds are a hard requirement for government deployments.
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --locked

COPY app ./app
# alembic.ini + the migrations directory are required by the AUTO_MIGRATE
# lifespan hook in app/main.py — without these the container would crash on
# startup when alembic tries to resolve its script_location.
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

ENV PATH="/opt/venv/bin:${PATH}"

EXPOSE 8000

# Honour SIGTERM quickly so Kubernetes / Compose can roll updates.
STOPSIGNAL SIGTERM

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
