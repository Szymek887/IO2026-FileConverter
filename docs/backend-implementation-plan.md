# Backend Implementation Plan – Multimedia File Converter

Source: `Dokumentacja_IW_IO.pdf` (requirements engineering documentation).
Deadline: **04.11.2026**. Plan start: 28.10.2026 (≈ 6 working days).

---

## 1. Scope summary (from requirements)

| Area | Requirement |
|---|---|
| App type | Public web app (external hosting), Polish UI, ≤ 10 concurrent users |
| Auth | E-mail + one-time password (OTP), persisted session |
| Formats | Audio: `flac`, `mp3`, `wav` · Video: `gif`, `mp4`, `mov` · Image: `jpg`, `png`, `heic` |
| Rules | Max 250 MB per file, 1–2 files per batch, target format ≠ source format and in the **same category** |
| Parameters | Chosen automatically by the system (best possible quality; lossless where both formats allow it) |
| Output | Converted files to download + status message in Polish (`success` / `error`) |
| Stack | Python backend (FastAPI), FFmpeg for audio/video, Pillow + pillow-heif for images |

Out of scope for backend: drag & drop UI, Polish UI copy (except API error/status messages).

---

## 2. Technical decisions

| Topic | Decision | Rationale |
|---|---|---|
| Framework | **FastAPI** + Uvicorn | Async uploads, auto OpenAPI docs for the frontend team |
| Persistence | **SQLite** via SQLAlchemy (or SQLModel) | 10 users – no need for a DB server |
| Job execution | In-process worker: `asyncio` queue + bounded `ThreadPoolExecutor` (2–4 workers) running FFmpeg/Pillow | No Redis/Celery to deploy within one week; FFmpeg does the heavy lifting in a subprocess |
| File storage | Local disk: `data/uploads/{job_id}/`, `data/outputs/{job_id}/` | Simple; cleaned up by a periodic task |
| E-mail | SMTP (`aiosmtplib`), config via env vars; console backend in dev | OTP delivery |
| Sessions | Random token (`secrets.token_urlsafe`) in an `HttpOnly; Secure; SameSite=Lax` cookie, hashed in DB | "Zapisujemy sesje" |
| Deployment | Docker image (python-slim + ffmpeg + libheif) behind Nginx/Caddy with HTTPS | Public hosting; reverse proxy must allow ~520 MB request bodies |
| Tests | `pytest` + `httpx`/`TestClient`; test media generated with FFmpeg in fixtures | Both devs have testing competence |

### Data model (follows section 3 of the documentation)

```
User      (email PK, otp_hash, otp_expires, otp_attempts, session_token_hash, session_expires, last_seen)
Job       (id uuid PK, timestamp, user_email FK, target_format, status[queued|processing|done|error], message)
InputFile (id uuid PK, job_id FK, name, extension, category, size, path)
Result    (job_id FK, timestamp, output_files[] -> URLs, status[success|error], message PL)
```

---

## 3. API contract (agree on Day 1 – both devs code against it)

All errors share one shape: `{"status": "error", "code": "FILE_TOO_LARGE", "message": "<Polish text>"}`.

| Method & path | Auth | Description | Owner |
|---|---|---|---|
| `POST /api/auth/request-otp` `{email}` | – | Generate 6-digit OTP, store hash + expiry (10 min), send e-mail. Always `202` | A |
| `POST /api/auth/verify-otp` `{email, code}` | – | Verify OTP, create session, set cookie. `401` on bad/expired code, `429` after 5 attempts, `503` if 10 users already active | A |
| `POST /api/auth/logout` | ✓ | Invalidate session | A |
| `GET /api/auth/me` | ✓ | `{email, session_expires}` | A |
| `GET /api/formats` | ✓ | Supported formats per category + allowed targets per source format | B |
| `POST /api/jobs` multipart `files[]` (1–2), `target_format` | ✓ | Validate, store, enqueue. `202 {job_id, status: "queued"}` | B |
| `GET /api/jobs/{id}` | ✓ (owner) | Job status + Result (`output_files`, `message`) – polled by frontend | B |
| `GET /api/jobs/{id}/files/{n}` | ✓ (owner) | Download converted file (`Content-Disposition: attachment`) | B |
| `GET /api/jobs` | ✓ | User's recent jobs (nice-to-have) | B |
| `GET /api/health` | – | Liveness + FFmpeg availability | A |

---

## 4. Work split

The split follows the two big backend concerns from the architecture diagram: **input/access (auth, platform)** and **processing (validation, conversion, output)**. The only shared surface is the `get_current_user` dependency and the error format, both fixed on Day 1.

Suggested assignment based on the competence matrix (backend skills: Nikodem, Jakub, Kacper; DevOps: Nikodem, Jakub). Since Nikodem is one of the two frontend-capable members, backend falls naturally to **Jakub** and **Kacper**:

- **Developer A – Jakub Szymczak**: platform, auth, sessions, deployment (DevOps experience).
- **Developer B – Kacper Tomczyk**: validation, conversion engine, jobs, downloads.

### Developer A – Platform & Authentication

1. **Project skeleton** (Day 1, blocking for B)
   - Repo layout (see §6), `pyproject.toml`/`requirements.txt`, `ruff` + `pytest` config.
   - `config.py` (pydantic-settings): paths, limits, SMTP, session TTL, `MAX_ACTIVE_USERS=10`.
   - DB engine/session, base models, `create_all` on startup.
   - Shared error handling: `AppError(code, message, http_status)` + exception handler → unified JSON.
   - `messages.py` – catalogue of Polish messages (B adds conversion-related entries).
2. **OTP login**
   - Generate 6-digit code with `secrets`, store **hash** (e.g. `hashlib.sha256` + pepper or `passlib`), expiry 10 min, single use.
   - Rate limits: max 5 verification attempts per code, max 1 OTP request per 60 s per e-mail.
   - E-mail sending service with SMTP + dev console backend; Polish e-mail template.
   - Basic e-mail format validation (`pydantic.EmailStr`).
3. **Sessions**
   - Token generation, hashed storage, cookie settings, sliding expiry (e.g. 24 h), logout.
   - `get_current_user` FastAPI dependency (stub available on Day 1 so B is unblocked).
   - **≤ 10 concurrent users**: count users with a valid session and `last_seen` within the last 15 min; refuse new logins above the limit with a Polish message.
4. **Infrastructure**
   - `Dockerfile` (ffmpeg, libheif), `docker-compose.yml` (app + reverse proxy), `.env.example`.
   - Reverse proxy config: HTTPS, `client_max_body_size 520m`, longer timeouts for uploads.
   - CORS config for the frontend dev server; `GET /api/health`.
   - CI (GitHub Actions): lint + tests on push.
   - Deployment to the chosen host + short `README` run instructions.
5. **Tests**: OTP happy path, expired/reused/wrong code, rate limiting, session expiry, user limit, protected endpoint without cookie.

### Developer B – Validation, Conversion & Results

1. **Format registry** (`formats.py`)
   - Enum of formats → category; allowed targets = same category minus source.
   - `GET /api/formats`.
2. **Upload & validation** (critical component per the documentation)
   - `POST /api/jobs`: 1–2 files, `target_format` valid.
   - Stream uploads to disk in chunks, **abort as soon as 250 MB is exceeded** (don't trust `Content-Length`).
   - Check extension against the list **and** verify content: `ffprobe` for audio/video, `Image.open().verify()` for images; extension must match detected category.
   - Target ≠ source and same category for every file in the batch.
   - Sanitize filenames (store under UUID, keep original name only for display/download name).
   - Polish error messages for each failure (`UNSUPPORTED_FORMAT`, `FILE_TOO_LARGE`, `TOO_MANY_FILES`, `INVALID_TARGET`, `CORRUPTED_FILE`).
3. **Job queue & worker**
   - Persist `Job` + `InputFile`s with status `queued`, push to `asyncio.Queue`.
   - Worker pool (2–4 threads) → `processing` → `done`/`error`; write `Result` with timestamp and Polish message.
   - Per-file timeout on FFmpeg subprocess (e.g. 10 min); a failed file marks the job `error` with a message naming the file.
   - On startup: jobs stuck in `processing` → `error` ("Przetwarzanie przerwane").
4. **Converters** – automatic parameter selection (no user parameters)

   | Conversion | Strategy |
   |---|---|
   | → `wav` | PCM 16-bit (24-bit if source is 24-bit), keep sample rate & channels |
   | → `flac` | `-c:a flac -compression_level 8` (lossless) |
   | → `mp3` | `libmp3lame -q:a 0` (VBR V0), keep sample rate ≤ 48 kHz |
   | `mp4` ↔ `mov` | **Remux with `-c copy`** when codecs are compatible (lossless); otherwise H.264 `-crf 18 -preset slow` + AAC 256k |
   | → `mp4`/`mov` from `gif` | H.264 `-crf 18`, `yuv420p`, scale to even dimensions, `+faststart` |
   | → `gif` | Two-pass `palettegen`/`paletteuse`, fps ≤ 15, width ≤ 640 px (keep aspect) to keep file size sane |
   | → `png` | Lossless, keep alpha, keep ICC profile |
   | → `jpg` | Quality 95, `subsampling=0`, flatten alpha onto white, keep EXIF/ICC |
   | → `heic` | pillow-heif, quality 90, keep EXIF |
   | all images | Apply EXIF orientation (`ImageOps.exif_transpose`) |

   - Common interface: `convert(input_path, output_path, target_format) -> None`, raises `ConversionError`.
   - Presets kept in one module so quality can be tuned without touching logic.
5. **Results & downloads**
   - `GET /api/jobs/{id}`, `GET /api/jobs/{id}/files/{n}` with ownership check (403/404 for other users).
   - Output filename = original base name + new extension.
   - Cleanup task: delete uploads right after conversion, outputs after e.g. 24 h (configurable); mark Result expired.
6. **Tests**: conversion matrix test (every source → every allowed target) on small generated fixtures, validation edge cases (251 MB stream, 3 files, wrong category, renamed `.txt` → `.png`), job lifecycle, download ownership.

### Shared responsibilities
- Day 1: agree on API contract (§3), error codes and DB models together; publish OpenAPI to the frontend team.
- Code review each other's PRs (small PRs, branch per feature, `main` protected).
- Day 5: joint end-to-end testing with the frontend.

---

## 5. Timeline

| Day | Date | Developer A | Developer B |
|---|---|---|---|
| 1 | 28.10 | Skeleton, config, DB, error handling, `get_current_user` stub · **joint: API contract** | Format registry, converter interface, FFmpeg/Pillow spike (verify HEIC & GIF work in Docker image) |
| 2 | 29.10 | OTP request/verify, e-mail service | Upload streaming + validation, `POST /api/jobs` |
| 3 | 30.10 | Sessions, logout, user limit, auth tests | Job queue + worker, audio & image converters |
| 4 | 31.10 – 02.11 | Dockerfile, compose, reverse proxy, CI, first deployment | Video/GIF converters, results & download endpoints, cleanup task |
| 5 | 03.11 | Replace stub with real auth everywhere, security pass, deploy RC | Conversion matrix tests, Polish messages, performance check (10 users × 2 × 250 MB) |
| 6 | 04.11 | **Release** – final deploy, smoke test, documentation | **Release** – bug fixes from E2E tests |

Milestones: **M1 (29.10)** frontend can call the API with stubbed auth · **M2 (31.10)** full flow working locally · **M3 (03.11)** deployed release candidate · **M4 (04.11)** delivery.

---

## 6. Proposed repository layout

```
backend/
  app/
    main.py              # FastAPI app, routers, startup/shutdown        (A)
    config.py            # settings                                       (A)
    db.py, models.py     # engine, ORM models                             (A + B)
    errors.py, messages.py  # AppError, Polish message catalogue          (A, B extends)
    auth/                # otp.py, sessions.py, email.py, router.py, deps.py   (A)
    conversion/
      formats.py         # format registry                                (B)
      validation.py      # upload checks                                  (B)
      converters/        # audio.py, video.py, image.py, presets.py       (B)
      worker.py          # queue + executor                               (B)
      router.py          # /api/formats, /api/jobs                        (B)
      cleanup.py         # retention task                                 (B)
  tests/
    auth/  conversion/  conftest.py
  Dockerfile  requirements.txt  pyproject.toml
deploy/
  docker-compose.yml  nginx.conf (or Caddyfile)  .env.example             (A)
docs/
```

---

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| HEIC encoding/decoding missing in the Docker image | Day-1 spike by B; pin `pillow-heif` wheel that bundles libheif |
| "No quality loss" vs. lossy targets (mp3, jpg, gif) | Documented in requirements: lossless where possible (remux, flac/wav/png), highest-quality presets otherwise |
| Long video conversions block users | Bounded worker pool, async status polling, per-file timeout |
| 250 MB uploads time out at the proxy | Proxy body size & timeout config (A), streaming to disk (B) |
| OTP e-mails land in spam / SMTP unavailable | Use a transactional SMTP provider; dev console backend; test early (Day 2) |
| Disk fills up | Delete inputs after conversion, retention for outputs, disk-usage check in `/api/health` |
| Tight deadline | Nice-to-haves (`GET /api/jobs` history, progress %) dropped first |

---

## 8. Definition of Done

- All endpoints from §3 implemented and documented in OpenAPI.
- Every allowed conversion pair (18 total: 6 per category) passes the matrix test.
- All validation rules from section 3 of the requirements return a Polish error message.
- App deployed publicly over HTTPS; login via real e-mail OTP works.
- CI green; README with local run & deploy instructions.
