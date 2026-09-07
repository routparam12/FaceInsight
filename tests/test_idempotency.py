from conftest import embedding_for, enroll, event_body, make_employee

IMG = b"reference-face-bytes-idem"


async def test_same_event_id_does_not_double_mark(client, admin_headers, device_headers):
    await make_employee(client, admin_headers, "EMP001")
    await enroll(client, admin_headers, "EMP001", IMG)
    emb = embedding_for(IMG)

    first = await client.post(
        "/api/v1/attendance/events",
        json=event_body("EMP001", emb, "evt-repeat-0001"),
        headers=device_headers,
    )
    assert first.json()["outcome"] == "marked"

    second = await client.post(
        "/api/v1/attendance/events",
        json=event_body("EMP001", emb, "evt-repeat-0001"),
        headers=device_headers,
    )
    assert second.status_code == 200, second.text
    assert second.json()["outcome"] == "duplicate_ignored"

    rows = await client.get(
        "/api/v1/attendance/events?employee_id=EMP001", headers=admin_headers
    )
    marked = [e for e in rows.json() if e["outcome"] == "marked"]
    assert len(marked) == 1
    assert len(rows.json()) == 1  # the retry created no new row


async def test_new_event_id_within_debounce_is_ignored(
    client, admin_headers, device_headers
):
    await make_employee(client, admin_headers, "EMP001")
    await enroll(client, admin_headers, "EMP001", IMG)
    emb = embedding_for(IMG)

    a = await client.post(
        "/api/v1/attendance/events",
        json=event_body("EMP001", emb, "evt-deb-0001"),
        headers=device_headers,
    )
    assert a.json()["outcome"] == "marked"

    b = await client.post(
        "/api/v1/attendance/events",
        json=event_body("EMP001", emb, "evt-deb-0002"),  # different id, seconds later
        headers=device_headers,
    )
    assert b.status_code == 200, b.text
    assert b.json()["outcome"] == "duplicate_ignored"

    rows = await client.get(
        "/api/v1/attendance/events?employee_id=EMP001&outcome=marked",
        headers=admin_headers,
    )
    assert len(rows.json()) == 1
