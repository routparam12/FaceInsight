from conftest import (
    embedding_for,
    enroll,
    event_body,
    make_employee,
    mismatch_embedding,
)

IMG = b"reference-face-bytes-0001"


async def test_matching_embedding_is_marked(client, admin_headers, device_headers):
    await make_employee(client, admin_headers, "EMP001")
    await enroll(client, admin_headers, "EMP001", IMG)

    r = await client.post(
        "/api/v1/attendance/events",
        json=event_body("EMP001", embedding_for(IMG), "evt-match-0001"),
        headers=device_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["outcome"] == "marked"
    assert body["direction"] == "check_in"
    assert body["employee_name"] == "emp001"
    assert body["similarity"] > 0.99


async def test_wrong_face_is_rejected(client, admin_headers, device_headers):
    await make_employee(client, admin_headers, "EMP001")
    await enroll(client, admin_headers, "EMP001", IMG)

    r = await client.post(
        "/api/v1/attendance/events",
        json=event_body("EMP001", mismatch_embedding(), "evt-nomatch-01"),
        headers=device_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] == "rejected_identity"


async def test_model_version_mismatch_is_409(client, admin_headers, device_headers):
    await make_employee(client, admin_headers, "EMP001")
    await enroll(client, admin_headers, "EMP001", IMG)

    r = await client.post(
        "/api/v1/attendance/events",
        json=event_body(
            "EMP001", embedding_for(IMG), "evt-badmodel", model_version="arcface-v9"
        ),
        headers=device_headers,
    )
    assert r.status_code == 409, r.text


async def test_unknown_employee_is_rejected(client, admin_headers, device_headers):
    r = await client.post(
        "/api/v1/attendance/events",
        json=event_body("GHOST", mismatch_embedding(), "evt-ghost-01"),
        headers=device_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] == "rejected_identity"
