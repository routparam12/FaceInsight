import pytest
from conftest import embedding_for, enroll, event_body, make_employee

from app.core.config import settings

IMG = b"reference-face-bytes-rules"


@pytest.fixture
def no_debounce(monkeypatch):
    monkeypatch.setattr(settings, "debounce_seconds", 0)


async def test_direction_toggles_in_out_in(
    client, admin_headers, device_headers, no_debounce
):
    await make_employee(client, admin_headers, "EMP001")
    await enroll(client, admin_headers, "EMP001", IMG)
    emb = embedding_for(IMG)

    outcomes = []
    for i in range(3):
        r = await client.post(
            "/api/v1/attendance/events",
            json=event_body("EMP001", emb, f"evt-dir-{i:04d}"),
            headers=device_headers,
        )
        outcomes.append((r.json()["outcome"], r.json()["direction"]))

    assert outcomes == [
        ("marked", "check_in"),
        ("marked", "check_out"),
        ("marked", "check_in"),
    ]


async def test_wrong_site_is_flagged(client, admin_headers, device_headers):
    # device is at SITE01 (fixture); put the employee somewhere else.
    await make_employee(client, admin_headers, "EMP009", site="SITE99")
    await enroll(client, admin_headers, "EMP009", IMG)

    r = await client.post(
        "/api/v1/attendance/events",
        json=event_body("EMP009", embedding_for(IMG), "evt-site-0001"),
        headers=device_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] == "wrong_site"


async def test_low_liveness_is_rejected(client, admin_headers, device_headers):
    await make_employee(client, admin_headers, "EMP001")
    await enroll(client, admin_headers, "EMP001", IMG)

    body = event_body("EMP001", embedding_for(IMG), "evt-live-0001")
    body["quality"]["liveness_score"] = 0.05
    r = await client.post(
        "/api/v1/attendance/events", json=body, headers=device_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] == "rejected_liveness"


async def test_summary_reflects_first_in_last_out(
    client, admin_headers, device_headers, no_debounce
):
    await make_employee(client, admin_headers, "EMP001")
    await enroll(client, admin_headers, "EMP001", IMG)
    emb = embedding_for(IMG)

    for i in range(2):  # check_in then check_out
        await client.post(
            "/api/v1/attendance/events",
            json=event_body("EMP001", emb, f"evt-sum-{i:04d}"),
            headers=device_headers,
        )

    rows = await client.get(
        "/api/v1/attendance/events?employee_id=EMP001&outcome=marked",
        headers=admin_headers,
    )
    assert [e["direction"] for e in rows.json()] == ["check_out", "check_in"]
