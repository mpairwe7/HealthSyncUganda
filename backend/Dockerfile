FROM python:3.12-slim AS base

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

# Run as an unprivileged user. Created after deps + app are in place so the
# venv and app tree can be chown'd to it.
RUN useradd --system --create-home --uid 1001 appuser \
    && chown -R appuser:appuser /app /opt/venv
USER appuser

EXPOSE 8000

# Honour SIGTERM quickly so Kubernetes / Compose can roll updates.
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"

# X-Forwarded-* headers are trusted only from these source IPs
# (uvicorn --forwarded-allow-ips). Defaults to "*" to preserve single-proxy
# PaaS behaviour, but that lets a client spoof X-Forwarded-For (evading the
# IP-keyed rate limiter and forging logged client IPs). In production set
# FORWARDED_ALLOW_IPS to the ingress IP/CIDR so forwarded IPs can be trusted.
ENV FORWARDED_ALLOW_IPS=*
CMD ["/bin/sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"$FORWARDED_ALLOW_IPS\""]
