"""Smoke test of `scripts/load_test.py` + `scripts/load_test_server.py` with tiny files, so
the load-test tooling keeps working as the API changes."""

import asyncio
import importlib.util
import shutil
import sys
from pathlib import Path

import httpx

from app.conversion.worker import ThreadedJobRunner

SCRIPTS = Path(__file__).parents[2] / "scripts"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"scripts_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look the module up
    spec.loader.exec_module(module)
    return module


def test_load_test_against_the_app(media, tmp_path, monkeypatch):
    server = load_script("load_test_server")
    load_test = load_script("load_test")
    monkeypatch.setattr(load_test, "POLL_SECONDS", 0.05)
    shutil.copy(media / "alpha.png", tmp_path / "img.png")
    scenarios = [load_test.Scenario("png-jpg", "img.png", "jpg")]

    app = server.build_app()
    runner = ThreadedJobRunner(1)
    runner.start()
    app.state.job_runner = runner  # no lifespan with ASGITransport

    async def go():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            results = await load_test.run(
                client, 3, tmp_path, scenarios, user_header=server.USER_HEADER
            )
            stats = (await client.get("/load-test/stats")).json()
        return results, stats

    try:
        results, stats = asyncio.run(go())
    finally:
        runner.stop()

    assert [r.status for r in results] == ["done"] * 3, [r.errors for r in results]
    assert {r.user for r in results} == {"user0", "user1", "user2"}
    for r in results:
        assert r.message == "Konwersja zakończona pomyślnie."
        assert r.downloaded_bytes > 0
        assert None not in (r.upload_s, r.queue_wait_s, r.conversion_s, r.download_s)
    assert set(stats) >= {"peak_memory_bytes", "peak_data_dir_bytes", "cpu_count"}
    assert "3/3 jobs done" in load_test.report(results, 1.0, stats)


def test_users_without_auth_fail_cleanly(media, tmp_path):
    """Against the real app (login stub) every user gets a 401, reported per user."""
    load_test = load_script("load_test")
    shutil.copy(media / "alpha.png", tmp_path / "img.png")
    scenarios = [load_test.Scenario("png-jpg", "img.png", "jpg")]
    from app.main import create_app

    async def go():
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await load_test.run(client, 2, tmp_path, scenarios, sessions=["x", "y"])

    results = asyncio.run(go())
    assert [r.status for r in results] == ["HTTP 401", "HTTP 401"]
