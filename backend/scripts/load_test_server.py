"""The real app, prepared for `scripts/load_test.py` on a local machine. NEVER DEPLOY THIS.

Until real login exists (A12) every API request would be `401`, so here requests are
authenticated by the `X-Load-Test-User` header (any e-mail; the user is created on first
use). It also serves `GET /load-test/stats`: peak memory of the container (cgroup v2) and
peak size of `DATA_DIR`, sampled every second.

`--cpus N` makes the app see N CPUs. FFmpeg's thread count is derived from it (see
`ffmpeg_threads()`), and inside a container `os.cpu_count()` reports all host CPUs – pin
the container to the same N cores (`docker run --cpuset-cpus`) to simulate a small host:

    docker run --cpuset-cpus 0,1 --memory 4g ... uv run python scripts/load_test_server.py --cpus 2
"""

import argparse
import contextlib
import os
import sys
import threading
import time
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, Header
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# `python scripts/load_test_server.py` puts only `scripts/` on the path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth.deps import get_current_user  # noqa: E402
from app.auth.models import User  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.db import get_db  # noqa: E402
from app.main import create_app  # noqa: E402

USER_HEADER = "X-Load-Test-User"
CGROUP = Path("/sys/fs/cgroup")
SAMPLE_INTERVAL_SECONDS = 1.0


def header_user(
    db: Annotated[Session, Depends(get_db)],
    x_load_test_user: Annotated[str, Header()],
) -> User:
    user = db.get(User, x_load_test_user)
    if user is None:
        try:
            user = User(email=x_load_test_user)
            db.add(user)
            db.commit()
        except IntegrityError:  # created by a parallel request
            db.rollback()
            user = db.get(User, x_load_test_user)
    return user


class Sampler:
    """Peak memory (cgroup v2, whole container) and peak `DATA_DIR` size.

    `peak_memory` includes the page cache (uploads just written), which the kernel frees
    under pressure; `peak_anon_memory` is what the processes (Python, FFmpeg) really use.
    """

    def __init__(self) -> None:
        self.peak_memory: int | None = None
        self.peak_anon_memory: int | None = None
        self.peak_data_dir = 0
        self.samples = 0

    def start(self) -> None:
        threading.Thread(target=self._run, name="load-test-sampler", daemon=True).start()

    def _run(self) -> None:
        while True:
            self.sample()
            time.sleep(SAMPLE_INTERVAL_SECONDS)

    def sample(self) -> None:
        memory = _read_int(CGROUP / "memory.peak") or _read_int(CGROUP / "memory.current")
        if memory is not None:
            self.peak_memory = max(self.peak_memory or 0, memory)
        anon = _memory_stat("anon")
        if anon is not None:
            self.peak_anon_memory = max(self.peak_anon_memory or 0, anon)
        self.peak_data_dir = max(self.peak_data_dir, _tree_size(settings.data_dir))
        self.samples += 1

    def stats(self) -> dict:
        return {
            "peak_memory_bytes": self.peak_memory,
            "peak_anon_memory_bytes": self.peak_anon_memory,
            "memory_limit_bytes": _read_int(CGROUP / "memory.max"),
            "peak_data_dir_bytes": self.peak_data_dir,
            "cpu_count": os.cpu_count(),
            "samples": self.samples,
        }


def _read_int(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):  # missing, or "max"
        return None


def _memory_stat(key: str) -> int | None:
    try:
        lines = (CGROUP / "memory.stat").read_text().splitlines()
    except OSError:
        return None
    return next((int(line.split()[1]) for line in lines if line.startswith(f"{key} ")), None)


def _tree_size(root: Path) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            with contextlib.suppress(OSError):  # deleted meanwhile
                total += os.stat(os.path.join(dirpath, name)).st_size
    return total


def build_app(sampler: Sampler | None = None) -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_current_user] = header_user
    sampler = sampler or Sampler()

    @app.get("/load-test/stats", include_in_schema=False)
    def stats() -> dict:
        return sampler.stats()

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--cpus", type=int, help="CPU count the app should see")
    args = parser.parse_args()

    if args.cpus:
        os.cpu_count = lambda: args.cpus  # FFmpeg threads per job follow from this
    sampler = Sampler()
    sampler.start()
    uvicorn.run(build_app(sampler), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
