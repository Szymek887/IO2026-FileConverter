"""Load test (B18): N users upload 2 large files each at the same time, then poll and download.

    # 1. sample files of ~240 MB (needs FFmpeg; takes a few minutes)
    uv run python scripts/load_test.py generate --out ../loadtest-samples

    # 2. run against a server
    uv run python scripts/load_test.py run --base-url http://localhost:8000 \
        --samples ../loadtest-samples --users 10 --user-header X-Load-Test-User

Authentication: `--user-header` sends one e-mail per user in that header (only for
`scripts/load_test_server.py`, a local stand-in while real login is missing), or
`--sessions FILE` with one session cookie value per line (real login, one line per user).

Users get the scenarios round-robin. Measured per user: upload time, queue wait (accepted ->
processing), conversion time (processing -> done), download time. Queue and conversion
times come from polling every `POLL_SECONDS`, like the frontend does.
"""

import argparse
import asyncio
import contextlib
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx

POLL_SECONDS = 1.0
TARGET_SIZE = 240_000_000  # bytes per sample, just under the 250 MiB limit
SESSION_COOKIE = "session"


@dataclass(frozen=True)
class Scenario:
    name: str
    sample: str
    target: str


SCENARIOS = [
    Scenario("mov-remux", "h264_pcm.mov", "mp4"),  # copy video, PCM -> AAC
    Scenario("mp4-gif", "h264.mp4", "gif"),  # decode everything, > 60 s -> 10 fps, 480 px
    Scenario("flac-mp3", "noise.flac", "mp3"),
    Scenario("prores-transcode", "prores.mov", "mp4"),  # full x264 transcode
]


@dataclass
class UserResult:
    user: str
    scenario: str
    status: str = "not started"
    message: str = ""
    upload_s: float | None = None
    queue_wait_s: float | None = None
    conversion_s: float | None = None
    download_s: float | None = None
    downloaded_bytes: int = 0
    errors: list[str] = field(default_factory=list)


# --- samples ---------------------------------------------------------------------------


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *args], check=True)


def _inputs(seconds: float) -> list[str]:
    """1080p30 test pattern + sine; with `NOISE` (an output option) hard to compress, like
    real video."""
    return ["-f", "lavfi", "-i", f"testsrc2=size=1920x1080:rate=30:duration={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]  # fmt: skip


NOISE = ["-vf", "noise=alls=12:allf=t"]


def _sized(path: Path, make, probe_seconds: float = 4.0) -> None:
    """Run `make(path, seconds)` long enough for the file to reach ~TARGET_SIZE."""
    make(path, probe_seconds)
    seconds = probe_seconds * TARGET_SIZE / path.stat().st_size
    make(path, round(seconds, 1))


def generate(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    h264 = ["-c:v", "libx264", "-preset", "veryfast", "-b:v", "18M", "-maxrate", "18M",
            "-bufsize", "18M", "-pix_fmt", "yuv420p"]  # fmt: skip

    def mov(path, s):
        _ffmpeg(*_inputs(s), *NOISE, *h264, "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2",
                "-shortest", str(path))  # fmt: skip

    def mp4(path, s):
        _ffmpeg(*_inputs(s), *NOISE, *h264, "-c:a", "aac", "-b:a", "192k", "-shortest",
                str(path))  # fmt: skip

    def prores(path, s):
        _ffmpeg(*_inputs(s), *NOISE, "-c:v", "prores_ks", "-profile:v", "2",
                "-c:a", "pcm_s16le", "-shortest", str(path))  # fmt: skip

    def flac(path, s):
        _ffmpeg("-f", "lavfi", "-i", f"anoisesrc=color=pink:amplitude=0.3:duration={s}",
                "-ar", "44100", "-ac", "2", "-c:a", "flac", str(path))  # fmt: skip

    for name, make in (("h264_pcm.mov", mov), ("h264.mp4", mp4), ("prores.mov", prores),
                       ("noise.flac", flac)):  # fmt: skip
        path = out / name
        if path.exists() and abs(path.stat().st_size - TARGET_SIZE) < TARGET_SIZE * 0.1:
            print(f"{name}: exists ({path.stat().st_size / 1e6:.0f} MB)")
            continue
        _sized(path, make, probe_seconds=4.0 if make is not flac else 30.0)
        print(f"{name}: {path.stat().st_size / 1e6:.0f} MB")


# --- run -------------------------------------------------------------------------------


def auth_for(index: int, user_header: str | None, sessions: list[str]) -> dict:
    """Request kwargs authenticating user `index`."""
    if user_header:
        return {"headers": {user_header: f"loadtest{index}@example.com"}}
    return {"headers": {"Cookie": f"{SESSION_COOKIE}={sessions[index]}"}}


async def run_user(
    client: httpx.AsyncClient, index: int, scenario: Scenario, samples: Path, auth: dict
) -> UserResult:
    result = UserResult(user=f"user{index}", scenario=scenario.name)
    path = samples / scenario.sample
    extension = path.suffix
    try:
        start = time.monotonic()
        with path.open("rb") as first, path.open("rb") as second:
            response = await client.post(
                "/api/jobs",
                files=[("files", (f"a{extension}", first)), ("files", (f"b{extension}", second))],
                data={"target_format": scenario.target},
                **auth,
            )
        accepted = time.monotonic()
        result.upload_s = accepted - start
        if response.status_code != 202:
            result.status = f"HTTP {response.status_code}"
            result.message = response.text[:200]
            return result
        job_id = response.json()["id"]

        processing_at = None
        while True:
            job = (await client.get(f"/api/jobs/{job_id}", **auth)).json()
            if job["status"] != "queued" and processing_at is None:
                processing_at = time.monotonic()
                result.queue_wait_s = processing_at - accepted
            if job["status"] in ("done", "error"):
                result.conversion_s = time.monotonic() - (processing_at or accepted)
                break
            await asyncio.sleep(POLL_SECONDS)

        result.status = job["status"]
        result.message = job["result"]["message"]
        if job["status"] == "done":
            start = time.monotonic()
            for output in job["result"]["output_files"]:
                async with client.stream("GET", output["url"], **auth) as download:
                    if download.status_code != 200:
                        result.errors.append(f"download {output['index']}: {download.status_code}")
                    async for chunk in download.aiter_bytes():
                        result.downloaded_bytes += len(chunk)
            result.download_s = time.monotonic() - start
    except Exception as exc:  # report and keep the other users going
        result.status = "exception"
        result.errors.append(f"{type(exc).__name__}: {exc}")
    return result


async def run(
    client: httpx.AsyncClient,
    users: int,
    samples: Path,
    scenarios: list[Scenario],
    user_header: str | None = None,
    sessions: list[str] | None = None,
) -> list[UserResult]:
    """All users start at the same moment."""
    return list(
        await asyncio.gather(
            *(
                run_user(
                    client,
                    i,
                    scenarios[i % len(scenarios)],
                    samples,
                    auth_for(i, user_header, sessions or []),
                )
                for i in range(users)
            )
        )
    )


def _fmt(seconds: float | None) -> str:
    return "-" if seconds is None else f"{seconds:7.1f}"


def report(results: list[UserResult], wall_s: float, stats: dict | None) -> str:
    lines = [
        f"{'user':8} {'scenario':17} {'status':7} {'upload':>7} {'queue':>7} {'convert':>7} "
        f"{'download':>8}  message"
    ]
    for r in results:
        lines.append(
            f"{r.user:8} {r.scenario:17} {r.status:7} {_fmt(r.upload_s)} {_fmt(r.queue_wait_s)} "
            f"{_fmt(r.conversion_s)} {_fmt(r.download_s):>8}  {r.message} {' '.join(r.errors)}"
        )
    done = sum(r.status == "done" for r in results)
    lines.append(f"\n{done}/{len(results)} jobs done, wall time {wall_s:.0f} s")
    for label, values in (
        ("upload", [r.upload_s for r in results]),
        ("queue wait", [r.queue_wait_s for r in results]),
        ("conversion", [r.conversion_s for r in results]),
    ):
        known = [v for v in values if v is not None]
        if known:
            lines.append(f"max {label}: {max(known):.1f} s")
    by_scenario: dict[str, list[float]] = {}
    for r in results:
        if r.conversion_s is not None and r.status == "done":
            by_scenario.setdefault(r.scenario, []).append(r.conversion_s)
    for name, values in by_scenario.items():
        lines.append(f"  {name}: conversion {min(values):.0f}-{max(values):.0f} s (2 files)")
    if stats:
        if stats.get("peak_anon_memory_bytes"):
            lines.append(
                f"peak process memory: {stats['peak_anon_memory_bytes'] / 2**20:.0f} MiB "
                f"(with page cache: {stats['peak_memory_bytes'] / 2**20:.0f} MiB)"
            )
        lines.append(f"peak DATA_DIR: {stats['peak_data_dir_bytes'] / 2**20:.0f} MiB")
    return "\n".join(lines)


async def _main_run(args: argparse.Namespace) -> int:
    sessions = args.sessions.read_text().split() if args.sessions else None
    if not args.user_header and (sessions is None or len(sessions) < args.users):
        sys.exit("give --user-header, or --sessions with one session cookie per user")
    timeout = httpx.Timeout(60.0, read=None, write=None)  # uploads/downloads take a while
    async with httpx.AsyncClient(base_url=args.base_url, timeout=timeout) as client:
        start = time.monotonic()
        results = await run(client, args.users, args.samples, SCENARIOS, args.user_header, sessions)
        wall = time.monotonic() - start
        stats = None
        with contextlib.suppress(httpx.HTTPError, ValueError):  # only load_test_server.py
            stats_response = await client.get("/load-test/stats")
            if stats_response.status_code == 200:
                stats = stats_response.json()

    print(report(results, wall, stats))
    if args.json:
        payload = {"results": [asdict(r) for r in results], "wall_s": wall, "stats": stats}
        args.json.write_text(json.dumps(payload, indent=2))
    return 0 if all(r.status == "done" for r in results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    gen = commands.add_parser("generate", help="create ~240 MB sample files")
    gen.add_argument("--out", type=Path, required=True)
    run_cmd = commands.add_parser("run", help="run the load test")
    run_cmd.add_argument("--base-url", default="http://localhost:8000")
    run_cmd.add_argument("--samples", type=Path, required=True)
    run_cmd.add_argument("--users", type=int, default=10)
    run_cmd.add_argument("--user-header", help="header carrying the user's e-mail (local only)")
    run_cmd.add_argument("--sessions", type=Path, help="file with one session cookie per user")
    run_cmd.add_argument("--json", type=Path, help="also write raw results here")
    args = parser.parse_args()

    if args.command == "generate":
        generate(args.out)
    else:
        sys.exit(asyncio.run(_main_run(args)))


if __name__ == "__main__":
    main()
