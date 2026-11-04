# Konwuś – multimedia file converter

Konwuś is a web app for converting audio, video and image files. A user logs in with a one-time code sent to their e-mail, uploads up to two files, picks a target format for each, and downloads the results (one by one or as a ZIP). Converted files can be downloaded for 24 hours.

Built for the *Inżynieria oprogramowania* (Software Engineering) course at AGH, 2026. Requirements: [`Dokumentacja_IW_IO.pdf`](Dokumentacja_IW_IO.pdf).

## Features

- **Passwordless login.** A 6-digit code is sent by e-mail. Sessions are kept in an `HttpOnly` cookie. Login can be restricted to selected e-mail domains, and the number of active users is capped (10 by default).
- **Conversions within a category:**

  | Category | Formats |
  |---|---|
  | Audio | FLAC, MP3, WAV |
  | Video | MP4, MOV, GIF |
  | Image | JPG (JPEG), PNG, HEIC (HEIF) |

- **Limits:** up to 2 files per upload, up to 250 MB per file. Uploads are checked with `ffprobe`/Pillow, so corrupted or mislabelled files are rejected.
- **Background processing.** Jobs run in a worker pool and the frontend polls their status. Jobs that were interrupted are resumed after a restart, and expired files are cleaned up automatically.
- **Polish UI** with an animated mascot, drag & drop, upload progress and accessibility support (keyboard navigation, `prefers-reduced-motion`).

## Architecture

```
            ┌──────────────────────── one origin (https://DOMAIN) ─────────────────────────┐
browser ──▶ │ Traefik ── /api/* ──▶ backend  (FastAPI, FFmpeg, Pillow, SQLite in /data)   │
            │         └─ else ───▶ frontend (React static build on nginx)                  │
            └──────────────────────────────────────────────────────────────────────────────┘
```

| Part | Stack | Docs |
|---|---|---|
| [`backend/`](backend) | Python 3.12, FastAPI, SQLAlchemy + SQLite, FFmpeg, Pillow + pillow-heif, uv, pytest, ruff | [`backend/README.md`](backend/README.md) |
| [`frontend/`](frontend) | React 19, TypeScript, Vite, MSW (API mock), Vitest, Playwright, oxlint | [`frontend/README.md`](frontend/README.md) |
| [`docs/`](docs) | API contract, OpenAPI spec, deployment guide, UI mockups | see below |

The frontend and the API must share one origin, because the session cookie depends on it. In development the Vite dev server proxies `/api` to the backend. In production Traefik routes by path.

The backend runs as **a single process**: conversions run in a thread pool inside it and the database is SQLite. Don't run multiple uvicorn workers or replicas. To run more conversions in parallel, raise `WORKER_COUNT`.

### Documentation

- [`docs/api-contract.md`](docs/api-contract.md) – the frontend–backend contract (endpoints, error codes, job lifecycle)
- [`docs/openapi.yaml`](docs/openapi.yaml) – machine-readable spec. A running backend also serves interactive docs at `/docs`.
- [`docs/deployment.md`](docs/deployment.md) – production deployment with Docker Compose behind Traefik
- [`docs/frontend-design/`](docs/frontend-design) – UI mockups

## Running locally

### Requirements

- [Node.js](https://nodejs.org/) 24 with npm
- [uv](https://docs.astral.sh/uv/), which installs Python 3.12 by itself
- FFmpeg with `ffprobe` on `PATH`: `brew install ffmpeg` / `apt install ffmpeg` / `winget install Gyan.FFmpeg`

### Option A: frontend only, with a mocked API

This is the fastest way to click through the UI. You don't need the backend, Python or FFmpeg.

```bash
cd frontend
npm install
npm run dev:mock
```

Open <http://localhost:5173>. Log in with any e-mail address and the code **`123456`**. The mock has test cases built in: a file whose name contains `uszkodzony` is rejected as corrupted, and one whose name contains `blad` fails during conversion.

### Option B: full stack (real backend and frontend)

**1. Backend** (terminal 1):

```bash
cd backend
uv sync                                       # creates .venv with all dependencies
cp .env.example .env                          # dev defaults: console e-mail, COOKIE_SECURE=false
uv run python scripts/check_media_tools.py    # optional: checks that FFmpeg can do every conversion
uv run uvicorn app.main:app --reload          # http://localhost:8000, API docs at /docs
```

Uploads, results and the SQLite database go to `backend/data/` (git-ignored).

**2. Frontend** (terminal 2):

```bash
cd frontend
npm install
npm run dev                                   # http://localhost:5173, proxies /api to :8000
```

**3. Try it out.** Open <http://localhost:5173> and enter any e-mail address. With `EMAIL_BACKEND=console` (the dev default) no e-mail is sent. The code is printed in the backend terminal instead:

```
INFO:     app.auth.email - Login code for you@example.com: 123456 (EMAIL_BACKEND=console, no e-mail sent)
```

Enter the code, upload a file (e.g. a PNG), choose a target format and download the result.

Notes:

- Keep `COOKIE_SECURE=false` in `backend/.env` when you work over plain `http://`. Safari drops `Secure` cookies on `http://localhost`, so the login wouldn't stick.
- If the backend runs somewhere other than `:8000`, start the frontend with `API_PROXY_TARGET=http://host:port npm run dev`.
- To test real e-mail delivery, set `EMAIL_BACKEND=smtp` and the `SMTP_*` values in `backend/.env`. A local catcher such as [Mailpit](https://mailpit.axllent.org/) works with `SMTP_HOST=localhost`, `SMTP_PORT=1025` and `SMTP_TLS=none`.
- Every backend setting is documented in [`backend/.env.example`](backend/.env.example).

### Running the tests

```bash
# backend
cd backend
uv run pytest                                  # unit + API tests (conversion tests need FFmpeg)
uv run ruff check . && uv run ruff format --check .

# frontend
cd frontend
npm test                                       # Vitest unit and component tests
npm run lint                                   # oxlint
npm run build                                  # type check + production build
npx playwright install chromium                # once, before the first E2E run
npm run test:e2e                               # Playwright E2E against the mocked API
```

To run the E2E suite against the full stack from Option B, use `E2E_BASE_URL=http://localhost:5173 npm run test:e2e`.

## Production deployment

The repository includes Dockerfiles for both parts and a Compose stack ([`compose.yaml`](compose.yaml)) meant to run behind an existing Traefik with HTTPS. In short:

```bash
cp .env.example .env      # DOMAIN, Traefik names, SECRET_KEY (openssl rand -hex 32), SMTP_*
docker compose up -d --build
docker compose ps         # wait until both services are "healthy"
```

In production the backend refuses to start without a strong `SECRET_KEY`, real SMTP and secure cookies. See [`docs/deployment.md`](docs/deployment.md) for requirements, updates, backups and operations.

## Contributing

- Create one branch per task (`feat/<name>`) and open a PR to `main`.
- Changes to the API must update both `docs/api-contract.md` and `docs/openapi.yaml` in the same PR.
- Before pushing, run the linters and tests listed above.
