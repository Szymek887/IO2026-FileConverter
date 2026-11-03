import pytest
from fastapi.testclient import TestClient

from app.core.config import settings


@pytest.fixture(autouse=True)
def insecure_cookies(monkeypatch):
    """TestClient talks plain http://testserver and wouldn't send back Secure cookies."""
    monkeypatch.setattr(settings, "cookie_secure", False)


def login(client: TestClient, outbox, email: str):
    """Request a code and verify it; returns the verify-otp response."""
    assert client.post("/api/auth/request-otp", json={"email": email}).status_code == 202
    code = outbox.last_code(email)
    return client.post("/api/auth/verify-otp", json={"email": email, "code": code})
