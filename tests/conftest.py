import os
import pathlib
import tempfile

_TMP_DB = pathlib.Path(tempfile.gettempdir()) / "face_attendance_test.db"
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DB.as_posix()}")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "secret")
os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-bytes-long-000")
os.environ.setdefault("MODEL_VERSION", "arcface-v1")
os.environ.setdefault("EMBEDDING_DIM", "512")
os.environ.setdefault("ENFORCE_SHIFT_WINDOW", "false")
os.environ.setdefault("ENFORCE_SITE_MATCH", "true")
os.environ.setdefault("DEBOUNCE_SECONDS", "180")
os.environ.setdefault("MIN_FACE_SCORE", "0.6")
os.environ.setdefault("MIN_LIVENESS_SCORE", "0.7")
os.environ.setdefault("ENROLLMENT_ENCRYPTION_KEY", "")

from datetime import datetime, timezone  # noqa: E402

import httpx  # noqa: E402
import pytest_asyncio  # noqa: E402

import app.models  # noqa: E402,F401  (register all tables)
from app.core.config import settings  # noqa: E402
from app.core.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.face_service import get_encoder  # noqa: E402

SITE = "SITE01"


@pytest_asyncio.fixture(autouse=True)
async def _db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


@pytest_asyncio.fixture
async def admin_headers(client):
    r = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "secret"}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest_asyncio.fixture
async def device_headers(client, admin_headers):
    r = await client.post(
        "/api/v1/devices",
        json={"name": "kiosk-1", "site_id": SITE},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    prov = r.json()["provisioning_token"]
    r = await client.post("/api/v1/devices/activate", json={"provisioning_token": prov})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def embedding_for(image_bytes: bytes) -> list[float]:
    """The template the server would store for these enrollment bytes; sending
    it back as the probe yields cosine ~1.0 (a clean 1:1 match)."""
    return [float(x) for x in get_encoder().embed(image_bytes).tolist()]


def mismatch_embedding() -> list[float]:
    v = [0.0] * settings.embedding_dim
    v[-1] = 1.0
    return v


async def make_employee(client, admin_headers, emp_id="EMP001", site=SITE):
    r = await client.post(
        "/api/v1/employees",
        json={"id": emp_id, "name": emp_id.lower(), "site_id": site, "timezone": "UTC"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def enroll(client, admin_headers, emp_id, image_bytes):
    r = await client.post(
        f"/api/v1/enrollment/{emp_id}/images",
        files=[("files", ("face.jpg", image_bytes, "image/jpeg"))],
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def event_body(emp_id: str, embedding: list[float], event_id: str, **over):
    body = {
        "event_id": event_id,
        "employee_id": emp_id,
        "embedding": embedding,
        "model_version": settings.model_version,
        "device_captured_at": datetime.now(timezone.utc).isoformat(),
        "quality": {"face_score": 0.98, "liveness_score": 0.97},
    }
    body.update(over)
    return body
