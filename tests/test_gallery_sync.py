from conftest import enroll, make_employee

IMG = b"reference-face-bytes-gallery"


async def test_delta_then_tombstone_then_full(client, admin_headers, device_headers):
    await make_employee(client, admin_headers, "EMP001")
    body = await enroll(client, admin_headers, "EMP001", IMG)
    v1 = body["gallery_version"]
    assert v1 > 0

    # Full delta from zero includes the upsert with embeddings.
    r = await client.get("/api/v1/gallery?since_version=0", headers=device_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["version"] == v1
    entry = next(c for c in data["changes"] if c["employee_id"] == "EMP001")
    assert entry["op"] == "upsert"
    assert entry["embeddings"] and len(entry["embeddings"][0]) == 512

    # Caught up: nothing new.
    r = await client.get(
        f"/api/v1/gallery?since_version={v1}", headers=device_headers
    )
    assert r.json()["changes"] == []

    # Deactivate -> tombstone in the next delta.
    r = await client.post(
        "/api/v1/employees/EMP001/deactivate", headers=admin_headers
    )
    assert r.status_code == 200, r.text
    r = await client.get(
        f"/api/v1/gallery?since_version={v1}", headers=device_headers
    )
    changes = r.json()["changes"]
    assert changes == [{"employee_id": "EMP001", "op": "remove",
                        "model_version": None, "embeddings": None}]

    # Full sync no longer lists the removed employee.
    r = await client.get("/api/v1/gallery/full", headers=device_headers)
    assert all(e["employee_id"] != "EMP001" for e in r.json()["entries"])


async def test_device_cannot_use_admin_routes(client, device_headers):
    r = await client.get("/api/v1/employees", headers=device_headers)
    assert r.status_code in (401, 403)


async def test_gallery_requires_device_auth(client, admin_headers):
    r = await client.get("/api/v1/gallery?since_version=0", headers=admin_headers)
    assert r.status_code == 401
