# Backend: FastAPI + FFmpeg. Build context: backend/
#
# Runs as ONE process on purpose: conversion jobs run in a thread pool inside it and the
# database is SQLite in /data. Do not add uvicorn workers or container replicas.

FROM ghcr.io/astral-sh/uv:0.11.8 AS uv

# --- Dependencies into /app/.venv ---------------------------------------------------------
FROM python:3.12-slim-trixie AS build
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY scripts/check_media_tools.py scripts/docker_healthcheck.py ./scripts/
# COPY keeps the modes of the checkout; with a strict umask (e.g. 077) the files would be
# unreadable for the unprivileged runtime user. Make them world-readable explicitly.
RUN chmod -R a+rX /app/app /app/scripts

# --- Runtime -------------------------------------------------------------------------------
FROM python:3.12-slim-trixie
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --system --uid 10001 --no-create-home --home-dir /app app \
    && mkdir /data && chown app:app /data

COPY --from=build /app /app
WORKDIR /app
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    ENV=prod \
    DATA_DIR=/data
USER app
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "scripts/docker_healthcheck.py"]

# --proxy-headers: Traefik in front sets X-Forwarded-*; only Traefik can reach this port.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--timeout-graceful-shutdown", "30"]
