# Developer A – Implementation Plan (Platform & Authentication)

Owner: **Developer A** (Jakub Szymczak) · Period: 28.10 – 04.11.2026
Based on: [`../../docs/backend-implementation-plan.md`](../../docs/backend-implementation-plan.md), [`../../docs/api-contract.md`](../../docs/api-contract.md)

Developer A delivers everything **around** the conversion engine: project skeleton, configuration, database, error handling, OTP login, sessions, the 10-user limit, health check, Docker, deployment and CI. Developer B builds on top of it.

---

## 0. Decisions specific to this part

| Topic | Decision | Why |
|---|---|---|
| Python | **3.12** (pinned in `.python-version` and Docker image) | Stable wheels for Pillow / pillow-heif; local machine has 3.14, `uv` installs 3.12 |
| Tooling | `uv` (deps + venv + lockfile), `ruff` (lint + format), `pytest` | One fast tool, reproducible `uv.lock` |
| DB access | **SQLAlchemy 2.0, synchronous**, SQLite (WAL mode) | B's worker threads also need DB access; sync is simpler and fine for 10 users |
| Migrations | None – `Base.metadata.create_all()` on startup | One-week project, schema owned by 2 people |
| OTP storage | `HMAC-SHA256(SECRET_KEY, email + code)`, compared with `hmac.compare_digest` | 6-digit codes are brute-forceable offline with plain SHA-256; HMAC with a server secret prevents it |
| Session storage | Token `secrets.token_urlsafe(32)` in cookie, `SHA-256(token)` in DB | DB leak doesn't leak usable sessions |
| Sessions per user | One active session per user (fields on `User`, as in the requirements' data model). New login replaces the old session | Matches documentation; keeps the user-limit logic trivial |
| Users | Created automatically on first `request-otp` (no registration in requirements) | Optional `ALLOWED_EMAIL_DOMAINS` setting to restrict access if needed |
| E-mail | `aiosmtplib`, sent **inline** with 10 s timeout. `EMAIL_BACKEND=console` logs the code in dev | User gets an immediate error if SMTP fails (`500 INTERNAL_ERROR` with a Polish message) |
| Time | All "now" calls go through `app/core/clock.py::now()` | Expiry logic testable without sleeping |
| Reverse proxy | **Caddy** (automatic HTTPS, simple config) serving frontend static files + `/api/*` → backend | Same origin in production → no CORS, cookie `SameSite=Lax` works |
| Location | Everything in `backend/`; deployment files in `backend/deploy/`; CI workflow must live in repo-root `.github/workflows/` | Requested folder structure (overrides `deploy/` at repo root from the shared plan) |

---

## 1. Target structure (Developer A's files marked **A**, extension points for B marked *B*)

```
backend/
  .python-version                 A   3.12
  pyproject.toml / uv.lock        A   deps, ruff + pytest config
  .env.example                    A
  README.md                       A   run, test, deploy
  Dockerfile / .dockerignore      A
  app/
    main.py                       A   create_app(): routers, middleware, handlers, lifespan
    core/
      config.py                   A   Settings (pydantic-settings)
      clock.py                    A   now() -> int
      db.py                       A   engine, SessionLocal, Base, get_db dependency
      errors.py                   A   AppError + exception handlers
      messages.py                 A*B Polish message catalogue (B adds conversion messages)
      security.py                 A   hashing helpers (HMAC OTP, token hash)
    auth/
      models.py                   A   User
      schemas.py                  A   request/response pydantic models
      otp.py                      A   generate / verify / rate-limit logic
      sessions.py                 A   create / validate / revoke, active-user count
      email.py                    A   EmailSender (smtp | console)
      deps.py                     A   get_current_user  ← used by B
      router.py                   A   /api/auth/*
    health/router.py              A   /api/health
    conversion/                   B   (A creates empty router + __init__ so app boots)
  tests/
    conftest.py                   A   app, db, client, auth_client, frozen clock fixtures
    auth/                         A
    conversion/                   B
  deploy/
    docker-compose.yml            A   backend + caddy
    Caddyfile                     A
.github/workflows/backend.yml     A   (repo root)
```

---

## 2. Tasks (in order)

Each task = one branch + PR (`feat/a-<name>`), reviewed by Developer B.

### Day 1 – Wed 28.10 · Skeleton (blocks Developer B → merge today)

**A1. Project bootstrap**
- [x] `uv init`, Python 3.12, deps: `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `pydantic-settings`, `email-validator`, `aiosmtplib`, `python-multipart`; dev: `pytest`, `httpx`, `ruff`.
- [x] `ruff` + `pytest` config in `pyproject.toml`.
- [x] `README.md`: `uv sync`, `uv run uvicorn app.main:app --reload`, `uv run pytest`.

**A2. Config & clock** – `core/config.py`, `core/clock.py`
- [x] Settings (env prefix none, `.env` file):
  `ENV` (dev|prod), `SECRET_KEY`, `DATA_DIR=./data`, `DATABASE_URL=sqlite:///./data/app.db`,
  `MAX_FILE_SIZE=262144000`, `MAX_FILES_PER_JOB=2`, `MAX_ACTIVE_USERS=10`, `ACTIVE_WINDOW_SECONDS=900`,
  `OTP_TTL_SECONDS=600`, `OTP_RESEND_SECONDS=60`, `OTP_MAX_ATTEMPTS=5`,
  `SESSION_TTL_SECONDS=86400`, `COOKIE_SECURE=true`, `CORS_ORIGINS=["http://localhost:5173"]`,
  `EMAIL_BACKEND=console|smtp`, `SMTP_HOST/PORT/USER/PASSWORD/FROM`, `ALLOWED_EMAIL_DOMAINS=[]`,
  `OUTPUT_RETENTION_SECONDS=86400` (used by B).
- [x] Fail fast in `prod` when `SECRET_KEY` is default or `EMAIL_BACKEND=console`.
- [x] `.env.example` with all keys documented.

**A3. Database** – `core/db.py`
- [x] Engine with `check_same_thread=False`, `PRAGMA journal_mode=WAL` + `foreign_keys=ON` on connect.
- [x] `Base` (DeclarativeBase), `SessionLocal`, `get_db()` dependency, `init_db()` called in lifespan (creates `DATA_DIR` and tables).

**A4. Errors & messages** – `core/errors.py`, `core/messages.py`
- [x] `class AppError(Exception): code, message, http_status, details=None`; `ErrorCode` StrEnum + `HTTP_STATUS` map (status is fixed per code, as in the contract).
- [x] `messages.py`: dict `code → Polish template` for **all 18 codes** from the contract (B only adjusts texts / adds variants), plus non-error texts.
- [x] Helper `error(code, *, message=None, **details)` → `AppError`; kwargs fill the template and become `details` (e.g. `file=...`).
- [x] Handlers producing `{"status":"error","code","message","details"}`:
  - `AppError` → as defined
  - `RequestValidationError` → `400 VALIDATION_ERROR`, `details.fields = {field: msg}`
  - `StarletteHTTPException` 404/405 → `NOT_FOUND`
  - `Exception` → `500 INTERNAL_ERROR` + log traceback

**A5. App factory** – `main.py`
- [x] `create_app()` with lifespan (`init_db`), CORS (`allow_credentials=True`, origins from config), handlers, routers: auth, health, conversion (empty `APIRouter` placeholder for B).
- [x] `get_current_user` **interface frozen today**: `def get_current_user(...) -> User` raising `UNAUTHENTICATED` (+ `CurrentUser` type alias). Stub that always returns 401 until A12; tests use `auth_client` (`dependency_overrides`).
- [x] `tests/conftest.py`: temp `DATA_DIR`/DB per test, `client`, `auth_client` (overrides `get_current_user` with a test user), `clock` fixture to freeze/advance time.

**A6. Health** – `health/router.py`
- [x] `GET /api/health`: `ffmpeg` = `shutil.which("ffmpeg")` and `ffprobe` present (cached at startup); `degraded` + `503` if missing or free disk on `DATA_DIR` < `MIN_FREE_DISK_BYTES` (1 GB).

✅ **Milestone:** `uv run pytest` green, app boots, `/docs` shows auth + health, Developer B can branch off and register routes/models.

### Day 2 – Thu 29.10 · OTP login

**A7. User model** – `auth/models.py` *(done together with A5 – B's `Job` needs the `users.email` FK target)*
- [x] `User`: `email` (PK, lowercase), `otp_hash`, `otp_expires`, `otp_sent_at`, `otp_attempts`, `session_token_hash` (unique, indexed), `session_expires`, `last_seen`, `created_at`.

**A8. Security helpers** – `core/security.py`
- [x] `generate_otp()` → 6 digits via `secrets.randbelow(10**6)`, zero-padded.
- [x] `hash_otp(email, code)` HMAC-SHA256; `verify_otp(email, code, otp_hash)` with `compare_digest`.
- [x] `new_session_token()`, `hash_token(token)`.

**A9. Email sender** – `auth/email.py`
- [x] `EmailSender` protocol; `ConsoleEmailSender` (logs `OTP for x: 123456`), `SmtpEmailSender` (aiosmtplib, `SMTP_TLS=starttls|tls|none` – `none` rejected in prod, `SMTP_TIMEOUT_SECONDS=10`); failures raise `EmailSendError`.
- [x] Polish e-mail: subject `Twój kod logowania – Konwerter plików`, body with code and validity (10 min), plain text.
- [x] Selected by `EMAIL_BACKEND`; injectable dependency `get_email_sender` – tests use the `outbox` fixture to capture sent codes.

**A10. `POST /api/auth/request-otp`** – `auth/otp.py`, `auth/router.py`
- [ ] Normalize email (`strip().lower()`), validate with `email-validator` (no DNS check) → `400 INVALID_EMAIL`. Email field typed `str` in schema so we return our own code instead of a generic validation error.
- [ ] Optional domain allow-list → `INVALID_EMAIL`.
- [ ] Rate limit: `now - otp_sent_at < OTP_RESEND_SECONDS` → `429 OTP_RATE_LIMITED`, `details.retry_after_seconds`.
- [ ] Upsert user, store hash/expiry, reset attempts, send e-mail; on send failure clear OTP and return `500 INTERNAL_ERROR` ("Nie udało się wysłać kodu. Spróbuj ponownie później.").
- [ ] `202` per contract (`otp_expires`, `resend_available_in`).

**A11. `POST /api/auth/verify-otp`**
- [ ] `code` must match `^\d{6}$` → else `400 VALIDATION_ERROR`.
- [ ] Unknown user / no OTP / expired → `401 OTP_EXPIRED`.
- [ ] `otp_attempts >= OTP_MAX_ATTEMPTS` → `429 TOO_MANY_ATTEMPTS` (and OTP invalidated).
- [ ] Wrong code → increment attempts → `401 INVALID_OTP` (5th wrong attempt → `429` and invalidate).
- [ ] Correct → check user limit (A13) → clear OTP (single use) → create session (A12) → set cookie → `200 {email, session_expires}`.

### Day 3 – Fri 30.10 · Sessions & user limit

**A12. Sessions** – `auth/sessions.py`, `auth/deps.py`
- [ ] `create_session(user)`: new token, store hash, `session_expires = now + TTL`, `last_seen = now`.
- [ ] Cookie: `session`, `HttpOnly`, `Secure=COOKIE_SECURE`, `SameSite=Lax`, `Path=/`, `Max-Age=TTL`.
- [ ] `get_current_user`: read cookie → lookup by hash → missing/expired → `401 UNAUTHENTICATED`. Sliding expiry: update `last_seen` and extend `session_expires` at most once per 60 s (avoid a DB write per poll request).
- [ ] `POST /api/auth/logout` → clear hash in DB, delete cookie, `204`, idempotent (works without valid session).
- [ ] `GET /api/auth/me` → `{email, session_expires}`.

**A13. Concurrent user limit**
- [ ] Active user = `session_expires > now AND last_seen > now - ACTIVE_WINDOW_SECONDS`.
- [ ] On verify: if the logging-in user is **not** already active and active count ≥ `MAX_ACTIVE_USERS` → `503 USER_LIMIT_REACHED`. Check is done after OTP is verified but before it is consumed, so the user can retry with the same code.
- [ ] Logout frees the slot immediately.

**A14. Auth tests** – `tests/auth/`
- [ ] request-otp: valid → code captured by fake sender; invalid email; resend < 60 s → 429 with `retry_after_seconds`; resend after 60 s OK and old code invalid.
- [ ] verify: correct; wrong; expired (advance clock 601 s); reused; 5 wrong → 429 then correct code still rejected.
- [ ] session: `/me` with/without cookie, expiry after TTL, sliding refresh, logout + reuse of old cookie → 401, second login invalidates first session.
- [ ] user limit: 10 active → 11th gets 503; one inactive for 15 min → 11th succeeds; active user re-login allowed.
- [ ] error shape: unknown route → `NOT_FOUND` JSON; malformed JSON → `VALIDATION_ERROR`.

✅ **Milestone M2 (auth part):** real auth works end-to-end locally (frontend can switch from Prism mock to backend for login).

### Days 4 – Sat 31.10 to Mon 02.11 · Infrastructure

**A15. Docker** – `Dockerfile`, `.dockerignore`
- [ ] `python:3.12-slim`, `apt-get install ffmpeg` (+ `libheif` if pillow-heif wheel needs it – coordinate with B's spike), `uv sync --frozen --no-dev`, non-root user, `DATA_DIR=/data` volume, `uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers`.
- [ ] Single uvicorn worker (B's in-process queue requires one process).

**A16. Compose & Caddy** – `deploy/docker-compose.yml`, `deploy/Caddyfile`
- [ ] Services: `backend` (volume `data:/data`, `env_file: .env`), `caddy` (ports 80/443, volumes for certs and frontend `dist/`).
- [ ] Caddyfile: `{$DOMAIN}`, `request_body /api/jobs* { max_size 520MB }`, `reverse_proxy /api/* backend:8000` with long read/write timeouts, `file_server` + SPA fallback (`try_files {path} /index.html`) for the frontend build.
- [ ] Local check: `docker compose up` with `DOMAIN=localhost`.

**A17. CI** – `.github/workflows/backend.yml`
- [ ] On push/PR touching `backend/**`: setup uv → `uv sync` → `ruff check` → `ruff format --check` → `pytest` (install `ffmpeg` via apt for B's tests).
- [ ] Optional: build Docker image to catch Dockerfile breakage.

**A18. First deployment**
- [ ] Provision host (VPS with Docker, ≥ 2 vCPU / 4 GB RAM / 20 GB disk), DNS record, `.env` with real `SECRET_KEY` + SMTP credentials.
- [ ] Deploy, verify HTTPS, real OTP e-mail delivery (check spam folder; set SPF/DKIM if using own domain), upload of a 250 MB file through the proxy.
- [ ] Document deploy steps in `README.md` (`git pull && docker compose up -d --build`).

### Day 5 – Tue 03.11 · Hardening & release candidate

**A19. Integration & security pass**
- [ ] Make sure all of B's endpoints use `get_current_user`; ownership checks present.
- [ ] Verify no stack traces / internal paths leak in error responses.
- [ ] Logging: request log without cookies/OTP codes; OTP printed only by console backend.
- [ ] Check contract conformance: run tests that compare responses against `docs/openapi.yaml` (e.g. `schemathesis` quick run or manual checks of key endpoints).
- [ ] Deploy RC, joint end-to-end test with frontend.

### Day 6 – Wed 04.11 · Release
- [ ] Final deploy, smoke test (login → convert one file per category → download), tag `v1.0.0`.
- [ ] README complete; update `docs/` if anything in the contract changed.

---

## 3. What Developer B can rely on (frozen on Day 1)

```python
from app.core.config import settings                 # limits, DATA_DIR, retention
from app.core.db import Base, get_db, SessionLocal   # models + request DB session; SessionLocal for worker threads
from app.core.errors import ErrorCode, error         # raise error(ErrorCode.UNSUPPORTED_FORMAT, file=name)
from app.core import messages                        # Polish texts; add B's messages here
from app.core.clock import now                       # epoch seconds
from app.auth.deps import CurrentUser, get_current_user  # endpoint param `user: CurrentUser` -> User
from app.auth.models import User                     # FK target: users.email
```
- B registers `app/conversion/router.py` (`router = APIRouter(prefix="/api")`) – already included by `create_app()`.
- B registers startup tasks (worker, cleanup) via `conversion.startup(app)` / `shutdown(app)` in `app/conversion/__init__.py` (plain sync functions, called by A's lifespan inside the running event loop – `asyncio.create_task` works there). Placeholders exist; B replaces them and imports `conversion.models` there.
- Tests: use the `auth_client` fixture for authenticated requests.

---

## 4. Open questions (to settle with the team)

1. **Hosting** – which server/VPS and domain? Needed by Sat 31.10 for A18.
2. **SMTP provider** – which account sends OTP e-mails (university mail, Gmail app password, Brevo/Mailgun free tier)?
3. **Email allow-list** – should login be open to any e-mail or restricted (e.g. to the client's domain)?
4. **Multiple devices** – is "new login replaces the previous session" acceptable? (Otherwise move sessions to a separate table – ~2 h of work.)
