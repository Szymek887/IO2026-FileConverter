"""`GET /api/jobs`: the current user's jobs from the last 24 h."""

import pytest

from app.auth.models import User
from app.conversion.formats import Category, Format
from app.conversion.models import InputFile, Job
from app.conversion.worker import process_job

RETENTION = 86400


@pytest.fixture
def create_job(auth_client, media, clock):
    """POST `alpha.png` -> jpg, return the 202 body."""

    def create(name="zdjęcie.png") -> dict:
        response = auth_client.post(
            "/api/jobs",
            files=[("files", (name, (media / "alpha.png").read_bytes()))],
            data={"target_format": "jpg"},
        )
        assert response.status_code == 202, response.text
        return response.json()

    return create


def ids(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [job["id"] for job in response.json()["items"]]


def test_no_jobs(auth_client):
    response = auth_client.get("/api/jobs")
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_newest_first(auth_client, create_job, clock):
    first = create_job()["id"]
    clock.advance(10)
    second = create_job()["id"]
    clock.advance(10)
    third = create_job()["id"]
    assert ids(auth_client.get("/api/jobs")) == [third, second, first]


def test_items_are_job_objects(auth_client, create_job):
    queued = create_job()
    done = create_job("inne.png")
    process_job(done["id"])

    items = {job["id"]: job for job in auth_client.get("/api/jobs").json()["items"]}
    assert items[queued["id"]] == queued  # same object as POST / GET /api/jobs/{id}
    assert items[done["id"]] == auth_client.get(f"/api/jobs/{done['id']}").json()
    assert items[done["id"]]["result"]["output_files"][0]["name"] == "inne.jpg"


def test_only_the_last_24_hours(auth_client, create_job, clock):
    old = create_job()["id"]
    clock.advance(1)
    recent = create_job()["id"]

    clock.advance(RETENTION - 2)  # `old` is 1 s short of 24 h
    assert ids(auth_client.get("/api/jobs")) == [recent, old]
    clock.advance(1)  # `old` is exactly 24 h old
    assert ids(auth_client.get("/api/jobs")) == [recent]
    clock.advance(1)
    assert ids(auth_client.get("/api/jobs")) == []


def test_only_the_current_users_jobs(auth_client, create_job, db):
    mine = create_job()["id"]
    db.add(User(email="someone@example.com"))
    other = Job(user_email="someone@example.com", target_format=Format.JPG)
    other.files = [
        InputFile(position=0, name="a.png", extension=Format.PNG, category=Category.IMAGE, size=1)
    ]
    db.add(other)
    db.commit()

    assert ids(auth_client.get("/api/jobs")) == [mine]


def test_requires_login(client):
    response = client.get("/api/jobs")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
