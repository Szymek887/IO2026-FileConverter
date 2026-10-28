# File Converter – Backend

FastAPI backend of the multimedia file converter. API contract: [`../docs/api-contract.md`](../docs/api-contract.md).

## Requirements

- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 automatically)
- FFmpeg (`winget install Gyan.FFmpeg` / `brew install ffmpeg` / `apt install ffmpeg`) – needed for conversions and their tests. HEIC support comes from the `pillow-heif` wheel, no system packages needed.

Check that your machine can do every conversion we need:

```bash
uv run python scripts/check_media_tools.py   # prints OK/FAIL per tool, exit code 1 on failure
```

## Setup

```bash
cd backend
uv sync                # creates .venv with Python 3.12 + all dependencies
```

## Common commands

```bash
uv run uvicorn app.main:app --reload   # dev server on http://localhost:8000 (docs at /docs)
uv run pytest                          # tests
uv run ruff check .                    # lint
uv run ruff format .                   # format
```

Add a dependency: `uv add <package>` (dev-only: `uv add --dev <package>`). Commit `pyproject.toml` and `uv.lock` together.

## Project structure

```
app/
  core/         # config, db, errors, messages, clock        (Developer A)
  auth/         # OTP login, sessions, get_current_user        (Developer A)
  health/       # /api/health                                  (Developer A)
  conversion/   # formats, validation, converters, jobs        (Developer B)
tests/
  auth/         # Developer A
  conversion/   # Developer B
docs/           # backend-internal plans
```

## Workflow

- Branch per task: `feat/a-<name>` / `feat/b-<name>`, PR to `main`, reviewed by the other backend developer.
- Before pushing: `uv run ruff check . && uv run ruff format --check . && uv run pytest`.
