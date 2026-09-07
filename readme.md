# face-attendance

FastAPI backend for a face-recognition attendance system.

## Trust model

The Android app recognises faces **locally** for a fast UX ("Hi Param"). That
result is never trusted. Every attendance decision is re-derived on the server:

```
Android                                   FastAPI (authority)
  CameraX -> detect -> quality/liveness      device auth + revocation
  -> ArcFace embedding -> local 1:N          model-version check
  -> "Hi Param" (UI only)                    embedding + skew validation
        |                                    quality + liveness re-check
        |  POST /attendance/events           server 1:1 verify (claimed employee)
        |  { event_id, employee_id,          server 1:N collision check
        |    embedding, model_version,       soft debounce
        |    device_captured_at, quality }   direction (check_in/check_out)
        v                                    site / shift rules
   outcome + server_time                     append event -> update summary
```

## Decision pipeline (`app/services/attendance_service.py`)

`idempotency -> model version -> embedding/skew -> quality+liveness -> 1:1
verify -> 1:N collision -> soft debounce -> direction -> site/shift rules ->
append event -> update daily summary`

Outcomes: `marked`, `duplicate_ignored`, `rejected_identity`,
`rejected_liveness`, `outside_shift`, `wrong_site`, `queued_for_review`.

* **Idempotency** — `(device_id, event_id)` is unique. A retried POST returns
  `duplicate_ignored` with the original decision and writes no new row.
* **Soft debounce** — a *different* `event_id` arriving within
  `DEBOUNCE_SECONDS` of the last accepted mark also returns `duplicate_ignored`.
* **Direction** is derived from the employee's last marked event that local day;
  the client never sends it.
* **Server time is authoritative.** `device_captured_at` is validated for clock
  skew and event age only.

## Data model

`attendance_events` is append-only and is the source of truth.
`daily_attendance_summary` is a derived rollup, rebuildable at any time.
`gallery_changes` is a monotonic log (version = row id) driving device delta
sync, including `op="remove"` tombstones.

## Endpoints (`/api/v1`)

| Method & path | Auth | Purpose |
| --- | --- | --- |
| `POST /auth/login` | — | Admin username/password -> JWT |
| `POST /devices` | admin | Register a device -> one-time provisioning token |
| `POST /devices/activate` | provisioning token | Exchange for a long-lived device token |
| `GET /devices` | admin | List devices |
| `POST /devices/{id}/revoke` | admin | Revoke a device |
| `POST /employees` | admin | Create employee |
| `GET /employees`, `GET /employees/{id}` | admin | Read |
| `POST /employees/{id}/deactivate` | admin | Deactivate + gallery tombstone |
| `POST /enrollment/{id}/images` | admin | Upload photos -> store (encrypted) + embed |
| `POST /enrollment/reembed` | admin | Re-embed the gallery under a new model |
| `GET /gallery?since_version=` | device | Delta sync (upserts + removes) |
| `GET /gallery/full` | device | Full resync |
| `POST /attendance/events` | device | Submit a recognised presence |
| `GET /attendance/events` | admin | Reporting / audit |

## Recognition math

The device sends its own embedding, so the server needs an encoder only for
**enrollment**. If `FACE_MODEL_PATH` is set, `OnnxArcFaceEncoder` is used
(wire the detector/aligner to match the client — one seam in
`face_service.py`). Otherwise a deterministic `StubEncoder` runs so the full
enrollment -> gallery -> attendance path works in dev/CI without ONNX.

Embeddings are stored L2-normalised as JSON for SQLite portability. **In
production on Postgres, switch `face_embeddings.vector` to pgvector
`Vector(EMBEDDING_DIM)` with an ANN index** and replace the linear scan in
`recognition_service.collision_check_1_n` with `ORDER BY vector <=> :probe`.

## Model migration

Enrollment source images are retained (disk, Fernet-encrypted when
`ENROLLMENT_ENCRYPTION_KEY` is set). On a model bump:

```
POST /api/v1/enrollment/reembed { "target_model_version": "arcface-v2" }
```

regenerates every template and bumps the gallery version; devices pick it up on
their next sync. Nobody re-enrolls physically.

## Run locally

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Docs at `http://localhost:8000/docs`. On startup the app runs `create_all`
against `DATABASE_URL` (SQLite by default) for convenience.

## Migrations (Postgres)

```bash
alembic upgrade head          # apply
alembic revision --autogenerate -m "message"
```

`alembic/env.py` reads `DATABASE_URL` from settings.

## Docker

```bash
docker compose up --build      # Postgres (pgvector image) + API on :8000
```

## Tests

```bash
pytest
```

Covers the rule engine, `(device_id, event_id)` idempotency vs. time-debounce,
gallery delta/tombstone/full sync, and 1:1 verification.

## Configuration

See `.env.example`. Key knobs: `MODEL_VERSION`, `EMBEDDING_DIM`,
`ACCEPT_THRESHOLD` / `REVIEW_LOW_THRESHOLD` (identity vs. review band),
`COLLISION_THRESHOLD` / `COLLISION_MARGIN`, `MIN_FACE_SCORE` /
`MIN_LIVENESS_SCORE`, `CLOCK_SKEW_SECONDS`, `DEBOUNCE_SECONDS`,
`ENFORCE_SITE_MATCH`, `ENFORCE_SHIFT_WINDOW`.
