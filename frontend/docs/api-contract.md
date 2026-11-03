# API Contract – Multimedia File Converter

Version: **1.0** (28.10.2026) · Machine-readable spec: [`openapi.yaml`](openapi.yaml)

This is the agreed interface between frontend and backend. Both sides code against it from day 1.
**Any change must be made in a PR that updates both this file and `openapi.yaml`, reviewed by one frontend and one backend developer.**

---

## 1. General rules

| Topic | Rule |
|---|---|
| Base path | `/api` (same origin as the frontend in production) |
| Format | JSON (`application/json; charset=utf-8`), except file upload (`multipart/form-data`) and download (binary) |
| Auth | Session cookie `session` (`HttpOnly`, `Secure`, `SameSite=Lax`), set by `POST /api/auth/verify-otp`. Frontend must send requests with `credentials: "include"` |
| Timestamps | Unix epoch **seconds** (integer), as in the requirements' data format |
| IDs | UUID v4 strings |
| Sizes | Bytes (integer). 250 MB = **262 144 000** bytes (250 × 1024 × 1024) |
| Language | All `message` fields are in **Polish** and ready to display to the user as-is |
| Unauthenticated | Every endpoint marked 🔒 returns `401 UNAUTHENTICATED` without a valid session → frontend redirects to login |

### Local development
- Backend runs on `http://localhost:8000`, frontend dev server (e.g. Vite) on `http://localhost:5173`.
- **Recommended:** proxy `/api` from the frontend dev server to `http://localhost:8000` (no CORS issues, cookies just work).
- Backend also allows CORS from `http://localhost:5173` with credentials, as a fallback.
- Interactive docs from the running backend: `http://localhost:8000/docs`.
- **Mock server before the backend is ready:**
  ```bash
  npx @stoplight/prism-cli mock docs/openapi.yaml
  # serves http://127.0.0.1:4010/api/... with the example responses
  ```
  For 🔒 endpoints the mock expects a `session` cookie to be present (any value).

---

## 2. Error format

Every non-2xx response (except downloads returning `404`/`410`, which also use it) has the same body:

```json
{
  "status": "error",
  "code": "FILE_TOO_LARGE",
  "message": "Plik „film.mov” przekracza maksymalny rozmiar 250 MB.",
  "details": { "file": "film.mov" }
}
```

| Field | Type | Notes |
|---|---|---|
| `status` | `"error"` | always |
| `code` | string | stable, machine-readable – use it for logic, never parse `message` |
| `message` | string | Polish, show to the user |
| `details` | object \| null | optional extra data (`file`, `retry_after_seconds`, `fields`) |

### Error codes

| HTTP | `code` | When | Example `message` |
|---|---|---|---|
| 400 | `VALIDATION_ERROR` | Malformed request body / missing field | `Nieprawidłowe dane żądania.` |
| 400 | `INVALID_EMAIL` | E-mail has invalid format | `Podaj poprawny adres e-mail.` |
| 401 | `UNAUTHENTICATED` | No / expired session | `Sesja wygasła. Zaloguj się ponownie.` |
| 401 | `INVALID_OTP` | Wrong code | `Nieprawidłowy kod logowania.` |
| 401 | `OTP_EXPIRED` | Code expired or already used | `Kod logowania wygasł. Poproś o nowy kod.` |
| 429 | `OTP_RATE_LIMITED` | New code requested < 60 s after previous one (`details.retry_after_seconds`) | `Nowy kod możesz wysłać za 42 s.` |
| 429 | `TOO_MANY_ATTEMPTS` | 5 wrong codes in a row – code invalidated | `Przekroczono liczbę prób. Poproś o nowy kod.` |
| 503 | `USER_LIMIT_REACHED` | 10 users already active | `Osiągnięto limit 10 jednocześnie zalogowanych użytkowników. Spróbuj ponownie później.` |
| 400 | `NO_FILES` | No file in upload | `Nie wybrano żadnego pliku.` |
| 400 | `TOO_MANY_FILES` | More than 2 files | `Możesz przesłać maksymalnie 2 pliki naraz.` |
| 413 | `FILE_TOO_LARGE` | File > 250 MB (`details.file`) | `Plik „film.mov” przekracza maksymalny rozmiar 250 MB.` |
| 415 | `UNSUPPORTED_FORMAT` | Extension not on the list (`details.file`) | `Format pliku „dokument.pdf” nie jest obsługiwany.` |
| 422 | `CORRUPTED_FILE` | Content doesn't match extension / unreadable (`details.file`) | `Plik „zdjecie.png” jest uszkodzony lub nie jest prawidłowym obrazem.` |
| 400 | `INVALID_TARGET` | Target unknown, equal to source, or from another category (`details.file`) | `Nie można przekonwertować pliku „nagranie.wav” do formatu PNG.` |
| 403 | `FORBIDDEN` | Job belongs to another user | `Brak dostępu do tego zadania.` |
| 404 | `NOT_FOUND` | Job / file does not exist | `Nie znaleziono zadania.` |
| 410 | `FILE_EXPIRED` | Output removed by retention (24 h) | `Plik wynikowy wygasł. Wykonaj konwersję ponownie.` |
| 500 | `INTERNAL_ERROR` | Unexpected server error | `Wystąpił nieoczekiwany błąd serwera.` |

Conversion failures are **not** HTTP errors – they are reported inside the job (`result.status = "error"`), see §5.

---

## 3. Authentication

Login flow (sequence diagram, steps 1–5):

```
[email form] --POST /auth/request-otp--> 202 --> [code form] --POST /auth/verify-otp--> 200 + cookie --> [converter]
```

### `POST /api/auth/request-otp`
Sends a 6-digit one-time code to the e-mail. Valid for **10 minutes**, single use.

Request:
```json
{ "email": "jan.kowalski@example.com" }
```
Response `202`:
```json
{
  "status": "ok",
  "message": "Wysłaliśmy kod logowania na adres jan.kowalski@example.com.",
  "otp_expires": 1793103000,
  "resend_available_in": 60
}
```
Errors: `400 INVALID_EMAIL`, `429 OTP_RATE_LIMITED`.

### `POST /api/auth/verify-otp`
Request:
```json
{ "email": "jan.kowalski@example.com", "code": "482913" }
```
Response `200` (+ `Set-Cookie: session=...`):
```json
{ "email": "jan.kowalski@example.com", "session_expires": 1793189400 }
```
Errors: `400 VALIDATION_ERROR` (code not 6 digits), `401 INVALID_OTP`, `401 OTP_EXPIRED`, `429 TOO_MANY_ATTEMPTS`, `503 USER_LIMIT_REACHED`.

### `GET /api/auth/me` 🔒
Use on app start to check whether the user is logged in.

Response `200`:
```json
{ "email": "jan.kowalski@example.com", "session_expires": 1793189400 }
```
Errors: `401 UNAUTHENTICATED`.

### `POST /api/auth/logout` 🔒
Response `204` (no body), cookie cleared. Idempotent – returns `204` even if session already expired.

---

## 4. Formats

### `GET /api/formats` 🔒
Single source of truth for supported formats, limits and allowed conversions. Frontend should use it for client-side pre-validation and to build the target-format picker (step 7 "Pokazuje dostępne formaty").

Response `200`:
```json
{
  "max_file_size": 262144000,
  "max_files_per_job": 2,
  "categories": [
    { "id": "audio", "label": "Audio",  "formats": ["flac", "mp3", "wav"] },
    { "id": "video", "label": "Wideo",  "formats": ["gif", "mp4", "mov"] },
    { "id": "image", "label": "Obraz",  "formats": ["jpg", "png", "heic"] }
  ],
  "conversions": {
    "flac": ["mp3", "wav"],
    "mp3":  ["flac", "wav"],
    "wav":  ["flac", "mp3"],
    "gif":  ["mp4", "mov"],
    "mp4":  ["gif", "mov"],
    "mov":  ["gif", "mp4"],
    "jpg":  ["png", "heic"],
    "png":  ["jpg", "heic"],
    "heic": ["jpg", "png"]
  },
  "extension_aliases": { "jpeg": "jpg", "heif": "heic" }
}
```

Rules for the frontend picker:
- Extension is taken from the filename, **case-insensitive**, aliases normalized (`.JPEG` → `jpg`).
- A batch of 2 files must share at least one target: offered targets = **intersection** of `conversions[...]` of both files. If empty (e.g. `wav` + `png`), show an error and don't allow submitting.

---

## 5. Conversion jobs

### Job object
Returned by all job endpoints.

```json
{
  "id": "7f3a9c2e-4b1d-4e8a-9c3f-2a1b5d6e7f80",
  "created_at": 1793102400,
  "target_format": "mp3",
  "status": "done",
  "files": [
    { "id": "1c2d...", "name": "nagranie.wav", "extension": "wav", "category": "audio", "size": 52428800 },
    { "id": "9e8f...", "name": "muzyka.flac",  "extension": "flac", "category": "audio", "size": 31457280 }
  ],
  "result": {
    "finished_at": 1793102461,
    "status": "success",
    "message": "Konwersja zakończona pomyślnie.",
    "output_files": [
      { "index": 0, "name": "nagranie.mp3", "size": 4812345, "url": "/api/jobs/7f3a9c2e-4b1d-4e8a-9c3f-2a1b5d6e7f80/files/0" },
      { "index": 1, "name": "muzyka.mp3",   "size": 3911002, "url": "/api/jobs/7f3a9c2e-4b1d-4e8a-9c3f-2a1b5d6e7f80/files/1" }
    ],
    "expires_at": 1793188861
  }
}
```

| Field | Notes |
|---|---|
| `status` | `queued` → `processing` → `done` \| `error` |
| `result` | `null` while `queued`/`processing`; always set when `done` or `error` |
| `result.status` | `success` when job `done`, `error` when job `error` |
| `result.message` | Polish; on error names the failing file, e.g. `Nie udało się przekonwertować pliku „film.mov”.` |
| `result.output_files` | Empty array on error. `url` is relative – use directly as `href` |
| `result.expires_at` | After this time downloads return `410 FILE_EXPIRED` |

A job is all-or-nothing: if any file fails, the job is `error` and no outputs are offered.

### `POST /api/jobs` 🔒
Upload 1–2 files and start conversion (step 8 "Konwertuj").

Request: `multipart/form-data`

| Field | Type | Notes |
|---|---|---|
| `files` | file (repeat field for 2 files) | 1–2 files, each ≤ 250 MB |
| `target_format` | string | one of the 9 formats, lowercase |

```js
const form = new FormData();
form.append("files", file1);
form.append("files", file2);       // optional
form.append("target_format", "mp3");
```

Response `202`: Job object with `status: "queued"` and `result: null`.

Errors: `400 NO_FILES`, `400 TOO_MANY_FILES`, `400 VALIDATION_ERROR` (missing `target_format`), `400 INVALID_TARGET`, `413 FILE_TOO_LARGE`, `415 UNSUPPORTED_FORMAT`, `422 CORRUPTED_FILE`.

> Upload progress: `fetch` doesn't report upload progress – use `XMLHttpRequest` (`xhr.upload.onprogress`) or axios `onUploadProgress` for a progress bar on 250 MB files.

### `GET /api/jobs/{job_id}` 🔒
Poll every **1–2 s** while `status` is `queued` or `processing`; stop on `done`/`error`.

Response `200`: Job object. Errors: `403 FORBIDDEN`, `404 NOT_FOUND`.

### `GET /api/jobs/{job_id}/files/{index}` 🔒
Download output file `index` (0-based, order of `output_files`).

Response `200`: binary body with
`Content-Type` matching the format (`audio/mpeg`, `audio/flac`, `audio/wav`, `image/gif`, `video/mp4`, `video/quicktime`, `image/jpeg`, `image/png`, `image/heic`) and
`Content-Disposition: attachment; filename*=UTF-8''nagranie.mp3`.

Errors: `403 FORBIDDEN`, `404 NOT_FOUND` (bad id/index or job not `done`), `410 FILE_EXPIRED`.

### `GET /api/jobs` 🔒 *(nice-to-have, may arrive later)*
Current user's jobs from the last 24 h, newest first.

Response `200`:
```json
{ "items": [ /* Job objects */ ] }
```

---

## 6. Health

### `GET /api/health`
No auth. `200`:
```json
{ "status": "ok", "ffmpeg": true }
```
`503` with `"status": "degraded"` if FFmpeg is unavailable or disk is nearly full.

---

## 7. Frontend checklist (mapping to requirements)

| UI feature | Endpoint(s) |
|---|---|
| Login with e-mail, "send code again" with countdown | `request-otp` (`resend_available_in`) |
| Enter code, error states | `verify-otp` |
| Auto-login on page load | `GET /auth/me` |
| Drag & drop / Import button, pre-validation (format, size, ≤ 2 files) | `GET /formats` (client-side), final check by `POST /jobs` |
| Target format picker | `GET /formats` → `conversions` |
| "Konwertuj" + progress | `POST /jobs` (upload progress) → poll `GET /jobs/{id}` |
| Status message, download links | `result.message`, `result.output_files[].url` |
| Logout | `POST /auth/logout` |
