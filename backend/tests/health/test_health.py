from collections import namedtuple

import pytest

from app.core.config import settings
from app.health import router as health

DiskUsage = namedtuple("DiskUsage", "total used free")


@pytest.fixture(autouse=True)
def clear_ffmpeg_cache():
    health.ffmpeg_available.cache_clear()
    yield
    health.ffmpeg_available.cache_clear()


@pytest.fixture
def tools(monkeypatch):
    """Set of tool names that `shutil.which` will find."""
    available = {"ffmpeg", "ffprobe"}
    monkeypatch.setattr(
        health.shutil, "which", lambda name: f"/usr/bin/{name}" if name in available else None
    )
    return available


@pytest.fixture
def free_disk(monkeypatch):
    """Dict whose "bytes" value is reported as free space in DATA_DIR."""
    state = {"bytes": 10 * 1024**3}
    monkeypatch.setattr(health.shutil, "disk_usage", lambda path: DiskUsage(0, 0, state["bytes"]))
    return state


def test_healthy(client, tools, free_disk):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "ffmpeg": True}


@pytest.mark.parametrize("missing", ["ffmpeg", "ffprobe"])
def test_missing_ffmpeg_tool_is_degraded(client, tools, free_disk, missing):
    tools.discard(missing)
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "ffmpeg": False}


def test_low_disk_space_is_degraded(client, tools, free_disk):
    free_disk["bytes"] = settings.min_free_disk_bytes - 1
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "ffmpeg": True}


def test_no_authentication_required(client, tools, free_disk):
    assert "set-cookie" not in client.get("/api/health").headers


def test_ffmpeg_check_is_cached(client, tools, free_disk):
    client.get("/api/health")
    tools.clear()
    assert client.get("/api/health").json()["ffmpeg"] is True
