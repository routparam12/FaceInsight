from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import AdminDep, DeviceDep, SessionDep
from app.models.attendance_event import AttendanceEvent
from app.schemas.attendance import (
    AttendanceEventRequest,
    AttendanceEventResponse,
    AttendanceEventRow,
)
from app.services import attendance_service
from app.services.attendance_service import PipelineError

router = APIRouter(prefix="/attendance", tags=["attendance"])


@router.post("/events", response_model=AttendanceEventResponse)
async def submit_event(
    body: AttendanceEventRequest,
    session: SessionDep,
    device: DeviceDep,
):
    """Device posts a locally-recognised presence. The server verifies identity,
    applies rules and owns the decision. Idempotent on (device, event_id)."""
    try:
        return await attendance_service.process_event(session, body, device)
    except PipelineError as e:
        raise HTTPException(e.status_code, e.detail)


@router.get("/events", response_model=list[AttendanceEventRow])
async def list_events(
    session: SessionDep,
    _: AdminDep,
    employee_id: str | None = Query(None),
    device_id: str | None = Query(None),
    outcome: str | None = Query(None),
    since: datetime | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    stmt = select(AttendanceEvent).order_by(AttendanceEvent.server_time.desc())
    if employee_id:
        stmt = stmt.where(AttendanceEvent.employee_id == employee_id)
    if device_id:
        stmt = stmt.where(AttendanceEvent.device_id == device_id)
    if outcome:
        stmt = stmt.where(AttendanceEvent.outcome == outcome)
    if since:
        stmt = stmt.where(AttendanceEvent.server_time >= since)
    return list(await session.scalars(stmt.limit(limit)))
