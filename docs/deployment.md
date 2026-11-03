# Deployment (Docker Compose behind Traefik)

The app is one Compose stack (`compose.yaml` in the repo root) with two containers:

| Service | Image | Port | Serves |
|---|---|---|---|
| `backend` | `backend/Dockerfile` (Python 3.12, FastAPI, FFmpeg) | 8000 | `https://DOMAIN/api/*` |
| `frontend` | `frontend/Dockerfile` (static build on nginx) | 8080 | everything else on `https://DOMAIN` |

Your existing Traefik routes the requests by path, so the frontend and the API share one origin. The `session` cookie (`Secure`, `HttpOnly`, `SameSite=Lax`) depends on that, so don't split them onto separate hosts. Neither container publishes ports. They are reachable only through Traefik.

Uploads, converted files and the SQLite database live in the `konwus_data` volume (`/data` in the backend).

## Requirements on the server

- Docker with Compose v2.
- Traefik v2 or v3 with the Docker provider, attached to an existing Docker network (default name `traefik`).
- An HTTPS entrypoint and a certificate resolver. Their names go into `.env`.
- **Upload timeout:** Traefik v3 closes requests whose body takes longer than 60 s to arrive (`respondingTimeouts.readTimeout`, default `60s`). One upload can be up to 2 × 250 MB, so on a slow connection it would fail. Raise it on the HTTPS entrypoint in Traefik's static config, e.g. `--entrypoints.websecure.transport.respondingTimeouts.readTimeout=15m` (`0` = no limit). Traefik v2 has no limit by default.
- An SMTP account for sending login codes. Production refuses to start without one.

## First deployment

```bash
git clone https://github.com/Szymek887/IO2026-FileConverter.git konwus
cd konwus
cp .env.example .env
# edit .env: DOMAIN, TRAEFIK_*, SECRET_KEY (openssl rand -hex 32), SMTP_*
docker compose up -d --build
docker compose ps        # both services "healthy"
```

Then open `https://DOMAIN`. Traefik only routes to a container once its health check passes, so allow about 20 s after a start.

Check that the server's FFmpeg build can do every conversion:

```bash
docker compose exec backend python scripts/check_media_tools.py
```

## Updating

```bash
git pull
docker compose up -d --build
```

Jobs that were queued or running when the backend stopped are picked up again on start. Converted files and sessions survive restarts, since they live in the volume.

## Operations

| Task | Command |
|---|---|
| Logs | `docker compose logs -f backend` |
| Status / health | `docker compose ps`; `curl https://DOMAIN/api/health` |
| Backup | `docker run --rm -v konwus_data:/data -v "$PWD":/backup alpine tar czf /backup/konwus-data.tgz -C /data .` |
| Remove everything incl. data | `docker compose down -v` |

`/api/health` returns `503 degraded` when the volume has less than 1 GB free or FFmpeg is missing. The container's health check deliberately still reports "healthy" in that case, so the site stays up. Watch the endpoint or the logs instead.

## Things not to change

- **Don't scale the backend** (`--scale`, `replicas`, uvicorn `--workers`). Conversions run in a thread pool inside the single process, and the database is SQLite. Use `WORKER_COUNT` for more parallel conversions.
- **Keep the settings `compose.yaml` enforces in production:** `ENV=prod`, `COOKIE_SECURE=true`, `EMAIL_BACKEND=smtp`. The backend refuses to start with a default or short `SECRET_KEY`, console e-mail or insecure cookies.

Any other backend setting from `backend/.env.example` (limits, retention, timeouts) can be added under `backend.environment` in `compose.yaml`.
