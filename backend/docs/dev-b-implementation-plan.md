# Developer B – Implementation Plan (Validation, Conversion, Jobs & Downloads)

Owner: **Developer B** (Kacper Tomczyk) · Period: 28.10 – 04.11.2026
Based on: [`../../docs/backend-implementation-plan.md`](../../docs/backend-implementation-plan.md), [`../../docs/api-contract.md`](../../docs/api-contract.md), [`../../docs/openapi.yaml`](../../docs/openapi.yaml), `Dokumentacja_IW_IO.pdf`
Counterpart: [`dev-a-implementation-plan.md`](dev-a-implementation-plan.md)

Developer B delivers the **processing** half of the system (architecture diagram, "Przetwarzanie" + "Koniec – wyjście"): format registry, upload streaming and validation (the component the requirements call *critical*), the conversion engine with automatic parameter selection, the job queue/worker, results, downloads and retention. Everything sits in `app/conversion/` and plugs into Developer A's skeleton.

---

## 0. Decisions specific to this part

| Topic | Decision | Why |
|---|---|---|
| Upload parsing | **Own streaming parser** on `request.stream()` using `python_multipart.MultipartParser` (already a dependency). No `UploadFile`/`Form` params on `POST /api/jobs` | FastAPI's `UploadFile` spools the whole body before the handler runs, so "abort as soon as 250 MB is exceeded" is impossible with it |
| Early errors | First error wins; the rest of the request body is **drained (read and discarded, not written)** before the JSON error is returned, capped at `MAX_FILES × MAX_FILE_SIZE + 10 MB` | Returning while the browser is still uploading resets the connection and XHR shows a network error instead of our Polish message |
| Content verification | `ffprobe` with a **forced demuxer** per extension (`-f wav`, `-f mov`, …) for audio/video; `Image.open(path, formats=[...])` + `verify()` for images | Proves content matches the extension, and stops FFmpeg from auto-detecting dangerous inputs (HLS/concat playlists renamed to `.mp4` → SSRF / local file reads) |
| FFmpeg hardening | Every call: `-nostdin -hide_banner -loglevel error -protocol_whitelist file`, list-form `subprocess.run` (no shell), timeout | Untrusted input files |
| Job execution | `queue.Queue` of job IDs + `WORKER_COUNT` (default 2) daemon threads; **DB is the source of truth**, the queue only holds IDs | Work is blocking (FFmpeg/Pillow) so plain threads are simpler than asyncio + executor; restart recovery reads state from DB |
| Runner abstraction | `JobRunner` protocol (`submit(job_id)`) stored on `app.state`; tests swap in a `ManualRunner` | Lets tests assert the `queued` state and run `process_job()` synchronously |
| FFmpeg threads | `-threads max(1, cpu_count // WORKER_COUNT)` | Two parallel jobs don't oversubscribe the 2-vCPU host |
| Job semantics | One target format per job, files processed **sequentially**, **all-or-nothing** (contract §5) | Contract; keeps `output_files[i]` ↔ `files[i]` |
| Storage | `DATA_DIR/uploads/{job_id}/{file_id}.{ext}`, `DATA_DIR/outputs/{job_id}/{index}.{ext}`; written as `*.part` then renamed | Original names never touch the filesystem; partial files never served |
| Inputs lifetime | Deleted as soon as the job finishes (success or error) | Disk: worst case 10 users × 2 × 250 MB in flight |
| Outputs lifetime | `expires_at = finished_at + OUTPUT_RETENTION_SECONDS` (24 h), removed by a periodic cleanup | Contract `410 FILE_EXPIRED` |
| Presets | All codec/quality parameters in `converters/presets.py` only | Quality can be tuned on Day 5 without touching logic |
| Images | Pillow + **pillow-heif** (`register_heif_opener()`), `Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS` (100 MP) | 48 MP iPhone photos pass, decompression bombs don't |
| Blocking work in handlers | `ffprobe`/Pillow checks run via `run_in_threadpool`; upload chunk writes are plain sync writes (64 KB chunks) | Keeps the event loop responsive while polls continue; sync chunk writes are negligible for 10 users |

---

## 1. Target structure (Developer B's files marked **B**, A's files B touches marked *A+B*)

```
backend/
  pyproject.toml                  A+B  B adds: pillow, pillow-heif
  app/
    core/config.py                A+B  B adds conversion settings (see B3)
    core/messages.py              A+B  B adds conversion texts / variants
    conversion/
      __init__.py                 B    exports router, startup(app), shutdown(app)
      formats.py                  B    Format/Category enums, registry, aliases, MIME types
      models.py                   B    Job, InputFile, Result, OutputFile
      schemas.py                  B    pydantic response models (FormatsResponse, Job, …)
      storage.py                  B    paths, display-name sanitizing, output names
      upload.py                   B    streaming multipart parser → staged files
      probe.py                    B    ffprobe wrapper + image inspection → MediaInfo
      validation.py               B    validation rules → AppError
      converters/
        __init__.py               B    convert() dispatch, ConversionError
        presets.py                B    all quality parameters
        ffmpeg.py                 B    run_ffmpeg() / run_ffprobe() helpers
        audio.py  video.py  image.py   B
      jobs.py                     B    service: create, load-for-owner, serialize
      worker.py                   B    JobRunner, ThreadedJobRunner, process_job(), recovery
      cleanup.py                  B    retention loop
      router.py                   B    /api/formats, /api/jobs*
  tests/conversion/
    conftest.py                   B    generated media fixtures, ManualRunner, small limits
    test_formats.py  test_upload.py  test_validation.py  test_converters.py
    test_jobs_api.py  test_worker.py  test_downloads.py  test_cleanup.py
```

---

## 2. Data model (`conversion/models.py`)

Follows section 3 of the requirements; column names follow the API contract.

| Table | Columns |
|---|---|
| `Job` | `id` (uuid str, PK) · `user_email` (FK `users.email`, indexed) · `created_at` (epoch) · `target_format` · `status` (`queued`/`processing`/`done`/`error`) · `started_at` (nullable) |
| `InputFile` | `id` (uuid, PK) · `job_id` (FK, indexed) · `position` (0/1) · `name` (sanitized display name) · `extension` · `category` · `size` · `path` (relative to `DATA_DIR`, nulled after deletion) |
| `Result` | `job_id` (PK + FK) · `finished_at` · `status` (`success`/`error`) · `message` (PL) · `expires_at` (nullable) · `purged` (bool) |
| `OutputFile` | `job_id` + `index` (composite PK) · `name` · `size` · `path` |

Relationships: `Job.files` ordered by `position`, `Job.result` (one-to-one, nullable), `Result.outputs` ordered by `index`; `lazy="selectin"` so serialization doesn't do N+1 queries. `app.conversion.models` must be imported before `create_all` (A's `init_db` imports it, or `conversion/__init__.py` imports it and `main.py` imports the package).

---

## 3. Validation rules (`upload.py` + `validation.py`)

Applied in this order; **the first failure is returned** (with `details.file` where a file is involved):

| # | When | Check | Error |
|---|---|---|---|
| 1 | Request start | `Content-Type` is `multipart/form-data` with boundary | `400 VALIDATION_ERROR` |
| 2 | Part header of a `files` part | 3rd file part appears | `400 TOO_MANY_FILES` |
| 3 | Part header | Extension (from filename, lowercased, aliases `jpeg→jpg`, `heif→heic`) is one of the 9 formats | `415 UNSUPPORTED_FORMAT` |
| 4 | While streaming | Bytes written for this part > `MAX_FILE_SIZE` (262 144 000) | `413 FILE_TOO_LARGE` |
| 5 | End of body | No file part (or only parts with empty filename) | `400 NO_FILES` |
| 6 | End of body | `target_format` field missing / longer than 32 bytes | `400 VALIDATION_ERROR` (`details.fields`) |
| 7 | End of body, per file in order | `target_format` is a known format, ≠ source, same category | `400 INVALID_TARGET` |
| 8 | End of body, per file in order | Content probe succeeds and matches extension (below) | `422 CORRUPTED_FILE` |

Content probe (`probe.py`):
- **Audio** (`flac`/`mp3`/`wav`): `ffprobe -f <flac|mp3|wav> -show_format -show_streams -of json`; must succeed, have ≥ 1 audio stream, `duration > 0`. Cover-art "video" streams in mp3/flac are allowed.
- **Video** (`mp4`/`mov`/`gif`): `-f mov` for both mp4 and mov (same demuxer family – a `.mov` that is really ISO-MP4 or vice versa is accepted), `-f gif` for gif; must have ≥ 1 real video stream (not `attached_pic`).
- **Image**: `Image.open(path, formats=["JPEG"|"PNG"|"HEIF"])` then `verify()`; re-open to read size/mode (verify invalidates the image). `DecompressionBombError` → `CORRUPTED_FILE`.
- Empty file (0 bytes) → `CORRUPTED_FILE`.
- The probe result (`MediaInfo`: codecs, sample rate, bit depth, channels, fps, width/height, duration, has_alpha) is not stored. The worker probes again before converting. A probe is cheap, and this keeps probe data out of the DB and still works after a restart.

Filenames: take the part after the last `/` or `\`, strip control characters, NFC-normalize, cut to 200 chars; empty stem → `plik`. Stored only in DB, never used as a path.

On any failure the job's upload directory is removed and nothing is written to the DB.

---

## 4. Conversion presets (`converters/presets.py`)

"Bez utraty jakości" = lossless where both formats allow it, otherwise the highest sensible quality (requirements, §2 note). Common to all FFmpeg calls: `-map_metadata 0`, forced input demuxer, hardening flags from §0.

| Conversion | Command / strategy |
|---|---|
| → `wav` | `-map 0:a:0 -c:a pcm_s16le`; `pcm_s24le` if source bit depth > 16 (24-bit FLAC). Keep sample rate & channels |
| → `flac` | `-map 0:a:0 -c:a flac -compression_level 8`; `-sample_fmt s16` for ≤ 16-bit or lossy sources, `-sample_fmt s32 -bits_per_raw_sample 24` above |
| → `mp3` | `-map 0:a:0 -c:a libmp3lame -q:a 0` (VBR V0); sample rate mapped to an MP3-valid one (88.2/176.4 kHz → 44.1 kHz, other > 48 kHz → 48 kHz, odd low rates → next valid); `-ac 2` if > 2 channels; `-id3v2_version 3` |
| `mov` → `mp4` | **Remux** `-map 0:v:0 -map 0:a? -c copy -movflags +faststart` if video ∈ {h264, hevc, av1, mpeg4} (hevc: `-tag:v hvc1`) and audio ∈ {aac, mp3, alac, ac3, eac3}. Incompatible audio only (e.g. PCM) → copy video, `-c:a aac -b:a 256k`. Incompatible video (e.g. ProRes) → full transcode |
| `mp4` → `mov` | Remux `-c copy` (mov accepts everything mp4 holds); on non-zero exit → retry with full transcode |
| Full transcode | `-c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -vf scale=trunc(iw/2)*2:trunc(ih/2)*2` + `-c:a aac -b:a 256k`; `+faststart` for mp4 |
| `gif` → `mp4`/`mov` | Full transcode video settings, `-an` |
| → `gif` | Single pass: `fps=F,scale=W:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a`, `-loop 0`. `F = min(source fps, 15)`, `W = min(source width, 640)`; if duration > 60 s → `F = 10`, `W = min(width, 480)` (keeps output size sane) |
| all images | `ImageOps.exif_transpose()` first (orientation tag reset to 1); first frame only for multi-image HEIC (primary image) |
| → `png` | Lossless; keep alpha and mode where PNG supports it (CMYK/YCbCr → RGB); keep ICC + EXIF; `compress_level=6` |
| → `jpg` | `quality=95, subsampling=0`; alpha flattened onto white; any mode → RGB; keep ICC + EXIF |
| → `heic` | pillow-heif `quality=90`, grid tiles of 2048 px (large photos stay decodable); mode → RGB/RGBA (8-bit); keep ICC + EXIF |

After every conversion: output must exist and be > 0 bytes, otherwise `ConversionError`. FFmpeg stderr tail goes to logs only, never to the user.

---

## 5. Tasks (in order)

Each task = one branch + PR (`feat/b-<name>`), reviewed by Developer A.

### Day 1 – Wed 28.10 · Foundations (independent of A's skeleton)

**B1. Tooling spike** – *do first, results reported to A for the Dockerfile*
- [x] `uv add pillow pillow-heif`; install FFmpeg locally (`winget install Gyan.FFmpeg` / `brew` / `apt`).
- [x] Verify on Windows **and** in `python:3.12-slim` + `apt install ffmpeg`: HEIC decode + **encode** with the pillow-heif wheel (no system libheif needed?), `libmp3lame` and `libx264` present in the distro FFmpeg, gif palette filter works.
- [x] Write findings (FFmpeg version, extra apt packages) into the PR description.

Findings (28.10, re-check any time with `uv run python scripts/check_media_tools.py`):

| | Windows 11 | Docker `python:3.12-slim` |
|---|---|---|
| Base | – | Debian 13.7 (trixie) |
| FFmpeg | 9.0.2 (`winget install Gyan.FFmpeg`) | 7.1.5 (`apt-get install --no-install-recommends ffmpeg`) |
| `libmp3lame`, `libx264`, `aac`, `flac`, PCM encoders | ✓ | ✓ |
| `mov`/`mp3`/`flac`/`wav`/`gif` demuxers, `palettegen`/`paletteuse` | ✓ | ✓ |
| Pillow 13.0.0 + pillow-heif 1.8.1 (libheif 1.23.6, x265 encoder, libde265 decoder) | ✓ | ✓ |
| HEIC encode + decode | ✓ | ✓ – **also in a bare image without any apt packages** |

→ Dockerfile needs **only** `apt-get install -y --no-install-recommends ffmpeg`; no `libheif`, no extra codecs (wheel bundles libheif + x265 + libde265). Dev/CI FFmpeg versions differ (9.x vs 7.1) – every flag used in §4 exists in both.

**B2. Format registry** – `formats.py`
- [x] `Category` and `Format` `StrEnum`s, `CATEGORY_FORMATS`, `CATEGORY_OF`, `EXTENSION_ALIASES`, `MIME_TYPES` (contract §5 download list), `CATEGORY_LABELS` (`Audio`, `Wideo`, `Obraz`).
- [x] `format_from_filename(filename) -> Format | None`, `parse_format(value)` (also used for `target_format`), `allowed_targets(fmt)` (same category minus source, in registry order), `can_convert(source, target)`.
- [x] `GET /api/formats` (moved here from B7 – unblocks the frontend picker): `FormatsResponse` in `schemas.py`, limits from `settings`, requires login.
- [x] Tests: response equals the contract example 1:1; `.JPEG` → `jpg`; `archive.tar.gz`, no extension, `.txt` → `None`; 18 conversion pairs; `401` without session.

**B3. Settings & messages** (small PR into A's files once the skeleton is merged)
- [x] `config.py`: `WORKER_COUNT=2`, `CONVERSION_TIMEOUT_SECONDS=600`, `PROBE_TIMEOUT_SECONDS=30`, `CLEANUP_INTERVAL_SECONDS=600`, `STALE_UPLOAD_SECONDS=3600`, `MAX_IMAGE_PIXELS=100_000_000`, `FFMPEG_PATH="ffmpeg"`, `FFPROBE_PATH="ffprobe"` (A already has `MAX_FILE_SIZE`, `MAX_FILES_PER_JOB`, `OUTPUT_RETENTION_SECONDS`). Numeric ones are `PositiveInt`; documented in `.env.example`; `/api/health` checks `FFMPEG_PATH`/`FFPROBE_PATH`.
- [x] `messages.py` additions – see §6 (`CORRUPTED_FILE_BY_CATEGORY`, `NOT_FOUND_FILE`, `CONVERSION_*`, `JOB_INTERRUPTED`; `INVALID_TARGET` with `{target}` already existed).

**B4. Converter interface + FFmpeg helpers** – `converters/__init__.py`, `ffmpeg.py`, `probe.py`
- [x] `convert(src: Path, dst: Path, source: Format, target: Format, timeout: int) -> None`, raises `ConversionError(reason, timeout: bool)`. Dispatches via `CONVERTERS[category]` (filled by B9/B10/B12); writes `dst.part`, renames only if non-empty; any converter exception is wrapped.
- [x] `run_ffmpeg(src, src_format, output_args, dst, dst_format, timeout)` / `run_ffprobe(src, src_format, timeout)` with hardening flags, forced demuxer **and muxer** (outputs are `*.part`), `-threads` per worker; failure/timeout/missing binary → `FFmpegError(timeout=bool)`.
- [x] `MediaInfo` (`AudioStream` with bit depth, `VideoStream` with fps, `ImageInfo` with alpha) + `probe(path, fmt)` raising `ProbeError`. Images are fully decoded (catches truncated JPEGs); `MAX_IMAGE_PIXELS` enforced.
- [x] Tests: `tests/conversion/conftest.py` generates sample media per session; renamed/mismatched/truncated/empty files, audio-only mp4, unicode paths, timeout, command hardening.

✅ **Milestone:** `GET /api/formats` logic and converter interface exist; spike results shared with A.

### Day 2 – Thu 29.10 · Upload & validation (critical component)

**B5. Models & storage** – `models.py`, `storage.py`
- [x] Tables from §2; `upload_dir(job_id)`, `output_dir(job_id)`, `display_name(raw)`, `output_names(inputs, target)` – stem + new extension, de-duplicated (`foto.png` + `foto.heic` → `foto.jpg`, `foto (2).jpg`).
  - Enums (`JobStatus`, `ResultStatus`, `Format`, `Category`) stored as their lowercase values; `UNIQUE(job_id, position)`; FK cascades; models registered via `app/conversion/__init__.py`.
  - `storage.py` also: `upload_path` / `output_path`, `to_relative` / `to_absolute` (DB paths relative to `DATA_DIR`, refuses `..`), `remove_uploads` / `remove_outputs`. `display_name` also strips invisible formatting characters (right-to-left override) and trailing dots; de-duplication is case-insensitive.

**B6. Streaming upload** – `upload.py`
- [x] `async def receive_upload(request, job_id) -> UploadResult(files: list[StagedFile], target_format: str | None)`.
- [x] Callbacks: on part header parse `Content-Disposition` (`name`, `filename`, RFC 5987 `filename*` – handled by us, `parse_options_header` drops it), apply rules 2–3 from §3, open the file; on data count bytes and apply rule 4; `target_format` buffered ≤ 32 bytes (last value wins); unknown fields and `files` parts without a filename are ignored without being stored.
  - **Change:** inputs are written straight to `uploads/{job_id}/{file_id}.{ext}` (no `.part` + rename) – uploads are never served, the DB row is written only after validation, and any failure removes the whole job upload dir.
- [x] Error → close/delete files, drain remaining body (cap from §0), raise `AppError`. Also: malformed/truncated body → `VALIDATION_ERROR`; client disconnect → files removed, exception re-raised.
- [x] Tests (fake `request.stream()` with 1-byte to 64 KB chunks, `MAX_FILE_SIZE` = 1000 B, plus real HTTP through `TestClient`): 1 and 2 files OK, 3 files, limit + 1 byte, exactly at limit OK, empty filename part, `filename*` UTF-8 name (`zażółć.png`), wrong content type, draining + cap, disconnect.
- Benchmark: 250 MB parsed and written in ~0.35 s (~700 MB/s) – the network is the only limit.

**B7. Validation & `POST /api/jobs`** – `validation.py`, `jobs.py`, `router.py`
- [x] Rules 5–8 from §3; probes via `run_in_threadpool`. Rule 7 is checked for all files before any file is probed (probing is the expensive part).
- [x] On success: insert `Job(status=queued)` + `InputFile`s in one transaction, commit, then `app.state.job_runner.submit(job_id)`; return `202` + Job object (`result: null`). Any failure removes the job's upload dir.
  - `worker.py` has the `JobRunner` protocol + `ManualRunner` (records IDs); `startup()` installs `ManualRunner` until B8 replaces it.
  - `jobs.job_response()` builds the contract Job object (also for done/error jobs – reused by B11/B15).
- [x] `openapi_extra` with the multipart request schema so `/docs` still documents the endpoint (no `UploadFile` params).
- [x] ~~`GET /api/formats` endpoint~~ – done in B2.
- [x] Tests via `auth_client` + `ManualRunner`: every error code of the endpoint, renamed `.txt` → `.png` → `CORRUPTED_FILE`, `.wav` + `.png` with target `mp3` → `INVALID_TARGET` naming `*.png`, target = source, target from other category, unknown target, unauthenticated → `401` without the body being stored.

✅ **Milestone M1 (B part):** frontend can upload against the real backend; jobs stay `queued`.

### Day 3 – Fri 30.10 · Worker, audio & image converters

**B8. Worker** – `worker.py`, `conversion/__init__.py`
- [x] `ThreadedJobRunner(worker_count)`: `queue.Queue`, daemon threads, `stop()` puts sentinels and joins with timeout. A crash in one job never kills its thread.
- [x] `process_job(job_id)` (own `SessionLocal`): claim with `UPDATE … WHERE status='queued'` (a job submitted twice runs once), mark `processing` + `started_at`; for each file in order: `convert()` → record `OutputFile` → on first `ConversionError` stop, delete outputs, write `Result(status=error, message=...)` (timeout → `CONVERSION_TIMEOUT`), job `error`; on success `Result(success, expires_at)`, job `done`; always delete uploads and null `InputFile.path`. Unexpected exceptions → error with the generic `INTERNAL_ERROR` message + logged traceback.
  - **Change:** no probe in the worker – `convert()` takes no probe result (B4), converters probe themselves when their presets need it.
- [x] `startup(app)`: `recover_jobs()` – jobs in `processing` → `error` with `JOB_INTERRUPTED` (+ delete their files); jobs in `queued` with uploads still on disk → re-submitted oldest first (else → error); start runner (a runner pre-set on `app.state` – tests – is kept). `shutdown(app)`: stop the threads. Cleanup loop is added in B14.
- [x] Tests: lifecycle `queued → processing → done` with `ManualRunner` (conversion tests' `app` fixture pre-sets it) and a fake image converter, failing/timing-out file → `error` + message names the file + no outputs, duplicate output names, double submit, real threads (2 workers, crash survival, app start/stop), recovery on startup.

**B9. Audio converters** – `converters/audio.py`: presets from §4 (bit depth / sample-rate / channel rules).
- [x] `presets.audio_args(stream, target)` (pure, unit-tested) + `convert_audio` (probe → `run_ffmpeg`), registered as `CONVERTERS[Category.AUDIO]` at the bottom of `converters/__init__.py`. `presets.py` imports probe types only under `TYPE_CHECKING` (probe imports the converters package).
- [x] Tests: all 6 pairs (codec, bit depth, rate, channels, duration); WAV↔FLAC bit-exact (decoded PCM MD5); 96 kHz/6 ch → 48 kHz stereo MP3; 88.2 kHz → 44.1 kHz; tags kept (Polish characters); cover art dropped; full job through the worker. Also green in `python:3.12-slim` with FFmpeg 7.1.5.

**B10. Image converters** – `converters/image.py`: presets from §4 (EXIF orientation, alpha flattening, ICC/EXIF carry-over, CMYK, palette and 16-bit modes).
- [x] `convert_image` registered as `CONVERTERS[Category.IMAGE]`; save options in `presets.image_save_options()`. ICC kept only when the colour family is unchanged (rgb→rgb, gray→gray); CMYK → sRGB via `ImageCms` with the embedded profile; 16-bit gray scaled (÷256) to 8-bit for JPG/HEIC, kept for PNG; palette transparency counts as alpha; grayscale JPG/PNG stays grayscale.
- [x] **HEIC grid tiles (`HEIC_GRID_TILE_SIZE = 2048`)** – found while benchmarking: a single HEVC frame of a detailed 24–48 MP photo (≳18 MB) is not decodable by libde265 (our own decoder – the output would not open). Tiled like iPhone HEICs it decodes; 2048 px tiles keep the single-frame speed (512 px: ~3× slower). Worst case (48 MP noise): JPG→HEIC 25 s, HEIC→JPG 3 s, JPG→PNG 5 s.
- [x] Tests (no FFmpeg needed): all 6 pairs, alpha flattening (exact colour), palette transparency, EXIF orientation + other tags, ICC carry-over, CMYK, 16-bit scaling, tiled HEIC, full job through the worker. Also green in `python:3.12-slim`.

**B11. `GET /api/jobs/{job_id}`** – `jobs.py`, `router.py`
- [ ] `job_id` typed `str`; malformed UUID → `404 NOT_FOUND` (not a `400` validation error). Missing → `404`, other user's → `403 FORBIDDEN`.
- [ ] Serialization exactly as the contract Job object; `url = /api/jobs/{id}/files/{index}`.

### Days 4 – Sat 31.10 to Mon 02.11 · Video, downloads, retention

**B12. Video & GIF converters** – `converters/video.py`: remux decision table, remux-fail → transcode fallback, gif palette pipeline with fps/width/duration rules.

**B13. Downloads** – `GET /api/jobs/{job_id}/files/{index}`
- [ ] Order of checks: job exists (`404`) → owner (`403`) → job `done` and `index` in range (`404`, "Nie znaleziono pliku.") → `now() > expires_at` or `purged` or file missing on disk (`410 FILE_EXPIRED`).
- [ ] `FileResponse` with `MIME_TYPES[target]` and `Content-Disposition: attachment; filename="<ascii fallback>"; filename*=UTF-8''<percent-encoded name>`.

**B14. Retention** – `cleanup.py`
- [ ] Asyncio loop every `CLEANUP_INTERVAL_SECONDS` calling `cleanup_once()` in a thread: delete `outputs/{job_id}` where `expires_at < now()`, set `Result.purged = True`; remove upload dirs older than `STALE_UPLOAD_SECONDS` that belong to no `queued`/`processing` job (crashed uploads).
- [ ] Tests with A's `clock` fixture: download works at `expires_at - 1`, `410` after, files gone after `cleanup_once()`.

**B15. `GET /api/jobs`** *(nice-to-have)* – current user's jobs with `created_at > now - 24 h`, newest first, `{"items": [...]}`.

✅ **Milestone M2 (B part):** full flow locally for all three categories: upload → poll → download.

### Day 5 – Tue 03.11 · Hardening & release candidate

**B16. Conversion matrix test** – `test_converters.py`
- [ ] Session-scoped fixtures generated at test time (nothing binary committed): audio via `ffmpeg -f lavfi sine` (16-bit wav, 24-bit flac, stereo mp3), video via `testsrc2` + `sine` (h264/aac mp4, mov with PCM audio, ProRes mov, 2-s gif), images via Pillow (RGBA png, JPEG with EXIF orientation 6 + ICC, HEIC).
- [ ] All **18 pairs** parametrized: output probes as the target format, duration within ±0.2 s (audio/video), image dimensions preserved (after orientation), PNG→JPG has no alpha, WAV→FLAC is bit-exact (compare decoded PCM hash).
- [ ] Marked `ffmpeg`; skipped with a clear reason if FFmpeg is missing (CI installs it – A17).

**B17. Messages & contract pass**
- [ ] Every error from `POST /api/jobs` and downloads compared against `openapi.yaml` examples (codes, HTTP statuses, `details.file`).
- [ ] Polish texts reviewed by a native speaker on the frontend team (quotation marks „…”).

**B18. Performance check**
- [ ] Script (`scripts/load_test.py`, httpx async): 10 users × 2 files of ~250 MB (mov remux, mp4 → gif, flac → mp3) in parallel against the Docker image on the target host. Record: upload time, max queue wait, conversion times, peak disk and RAM.
- [ ] If a 250 MB transcode exceeds ~5 min: switch `preset slow → medium` in `presets.py` (not the CRF).

### Day 6 – Wed 04.11 · Release
- [ ] Fix bugs from joint E2E testing; smoke test one conversion per category on production; update `docs/` if anything in the contract changed.

---

## 6. Polish messages added by B (`core/messages.py`)

| Key | Text |
|---|---|
| `CONVERSION_SUCCESS` | `Konwersja zakończona pomyślnie.` |
| `CONVERSION_FAILED` | `Nie udało się przekonwertować pliku „{file}”.` |
| `CONVERSION_TIMEOUT` | `Konwersja pliku „{file}” trwała zbyt długo i została przerwana.` |
| `JOB_INTERRUPTED` | `Przetwarzanie zostało przerwane. Spróbuj ponownie.` |
| `CORRUPTED_FILE` (variants by category) | `Plik „{file}” jest uszkodzony lub nie jest prawidłowym obrazem / plikiem audio / plikiem wideo.` |
| `INVALID_TARGET` | `Nie można przekonwertować pliku „{file}” do formatu {target}.` (target uppercased) |
| `NOT_FOUND` (file variant) | `Nie znaleziono pliku.` |

---

## 7. What Developer B needs from Developer A (Day 1 skeleton)

```python
from app.core.config import settings
from app.core.db import Base, get_db, SessionLocal   # SessionLocal used by worker threads
from app.core.errors import AppError, error
from app.core.clock import now
from app.auth.deps import get_current_user
from app.auth.models import User                     # FK target users.email
```
- `create_app()` includes `app.conversion.router` and calls `conversion.startup(app)` / `shutdown(app)` from its lifespan.
- **Single uvicorn worker process** (in-process queue) – already in A15.
- Dockerfile: `apt-get install -y --no-install-recommends ffmpeg` is enough (verified in B1: Debian's package has `libmp3lame` + `libx264`; pillow-heif needs no system packages).
- Caddy: `max_size 520MB` and long timeouts on `/api/jobs*` – already in A16.
- CI installs `ffmpeg` so the matrix test runs – already in A17.
- `conftest.py`: `auth_client`, `clock`, temp `DATA_DIR`; B adds conversion fixtures in `tests/conversion/conftest.py`.

Until A's skeleton is merged, B works on pure modules (`formats.py`, `converters/`, `probe.py`) that need nothing from `app.core`.

---

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| HEIC encoding unavailable in the Docker image | ✓ Resolved in B1: the pillow-heif wheel bundles encoder + decoder. Fallback if a future wheel drops x265: build against Debian `libheif-dev` + `libde265`/`x265` |
| Long transcodes block the queue | 2 workers, remux instead of transcode where possible, per-file timeout, preset tuning in B18 |
| Browser shows "network error" instead of 413 | Drain body before responding (§0); frontend also pre-validates size via `GET /api/formats` |
| Malicious media (playlists, decompression bombs) | Forced demuxers, `-protocol_whitelist file`, `MAX_IMAGE_PIXELS`, inputs stored under UUIDs |
| Huge GIFs from long videos | fps/width reduction for > 60 s (§4); see open question 3 |
| Disk fills up | Inputs deleted immediately, outputs after 24 h, stale upload cleanup, A's disk check in `/api/health` |
| Worker crash / restart mid-job | DB is source of truth; startup recovery marks or re-queues jobs |

---

## 9. Definition of Done (Developer B)

- `GET /api/formats`, `POST /api/jobs`, `GET /api/jobs/{id}`, `GET /api/jobs/{id}/files/{n}` match `docs/openapi.yaml` (`GET /api/jobs` if time allows).
- All 18 conversion pairs pass the matrix test in CI.
- Every validation rule from requirements §3 returns its contract error code with a Polish message.
- Uploads over 250 MB are rejected without writing more than 250 MB to disk.
- Inputs deleted after conversion; outputs return `410` after 24 h and are removed from disk.
- `ruff check`, `ruff format --check`, `pytest` green.

---

## 10. Open questions (to settle with the team)

1. **Designs vs. contract – per-file targets and cross-category conversion.** `docs/frontend-design/4new.png` shows "Każdy plik może mieć inny format docelowy" and an `MP4 → MP3` conversion. The contract has one `target_format` per job, and requirements §3 require the same category. Proposal: keep the contract for v1. If per-file targets are wanted, add an optional repeated `target_formats` field (backward compatible, ~½ day for B). Video → audio extraction contradicts the requirements and needs the client's approval.
2. **"Pobierz wszystko (.zip)"** in `5_gotowe.png` is not in the contract. Options: frontend triggers both downloads (no backend work), or add `GET /api/jobs/{id}/archive` (streamed `ZIP_STORED`, ~1 h for B). Either way it needs a contract PR.
3. **GIF from long videos**: are the fps/width reductions in §4 acceptable, or should we cap the GIF duration (e.g. first 60 s) instead?
4. **Per-user fairness**: should one user be limited to e.g. 2 queued/processing jobs at once? That would need a new error code in the contract.
