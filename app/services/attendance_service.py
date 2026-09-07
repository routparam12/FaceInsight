"""The attendance decision pipeline.

Order (matches the agreed design):
  idempotency -> model version -> embedding/skew -> quality+liveness
  -> 1:1 verify -> 1:N collision -> soft debounce -> direction
  -> site/shift rules -> append event -> update summary
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.attendance_event import AttendanceEvent
from app.models.attendance_summary import DailyAttendanceSummary
from app.models.device import Device
from app.models.employee import Employee
from app.schemas.attendance import (
    AttendanceEventRequest,
    AttendanceEventResponse,
    Direction,
    Outcome,
)
from app.services import recognition_service
from app.services.face_service import l2_normalize, to_vector, validate_dim
from app.utils.logging import audit
from app.utils.time import as_utc, utcnow

MAX_EVENT_AGE = timedelta(days=7)  # older offline-queued events are dropped


class PipelineError(Exception):
    """Hard client error -> HTTP 4xx, no event row written."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class _Ctx:
    req: AttendanceEventRequest
    device: Device
    now: datetime
    probe: object  # np.ndarray


# --- helpers --------------------------------------------------------------

def _local_date(dt: datetime, tz: str) -> date:
    try:
        return as_utc(dt).astimezone(ZoneInfo(tz)).date()
    except Exception:
        return as_utc(dt).date()


async def _existing(
    session: AsyncSession, device_id: str, client_event_id: str
) -> AttendanceEvent | None:
    return await session.scalar(
        select(AttendanceEvent).where(
            AttendanceEvent.device_id == device_id,
            AttendanceEvent.client_event_id == client_event_id,
        )
    )


async def _employee_name(session: AsyncSession, employee_id: str | None) -> str | None:
    if not employee_id:
        return None
    return await session.scalar(
        select(Employee.name).where(Employee.id == employee_id)
    )


def _response(
    ev: AttendanceEvent, employee_name: str | None
) -> AttendanceEventResponse:
    return AttendanceEventResponse(
        outcome=Outcome(ev.outcome),
        direction=Direction(ev.direction) if ev.direction else None,
        employee_name=employee_name,
        server_time=as_utc(ev.server_time),
        similarity=ev.similarity,
    )


async def _last_marked_today(
    session: AsyncSession, employee_id: str, tz: str, now: datetime
) -> AttendanceEvent | None:
    today = _local_date(now, tz)
    rows = await session.scalars(
        select(AttendanceEvent)
        .where(
            AttendanceEvent.employee_id == employee_id,
            AttendanceEvent.outcome == Outcome.marked.value,
        )
        .order_by(AttendanceEvent.server_time.desc())
        .limit(20)
    )
    for ev in rows:
        if _local_date(ev.server_time, tz) == today:
            return ev
    return None


async def _persist(
    session: AsyncSession,
    ctx: _Ctx,
    *,
    outcome: Outcome,
    direction: Direction | None,
    similarity: float | None,
    employee_id: str | None,
    site_id: str | None,
    note: str | None,
) -> AttendanceEvent:
    ev = AttendanceEvent(
        client_event_id=ctx.req.event_id,
        device_id=ctx.device.id,
        employee_id=employee_id,
        outcome=outcome.value,
        direction=direction.value if direction else None,
        similarity=similarity,
        model_version=ctx.req.model_version,
        site_id=site_id,
        face_score=ctx.req.quality.face_score,
        liveness_score=ctx.req.quality.liveness_score,
        device_captured_at=as_utc(ctx.req.device_captured_at),
        server_time=ctx.now,
        note=note,
    )
    session.add(ev)
    try:
        await session.commit()
    except IntegrityError:
        # Concurrent duplicate of the same (device_id, event_id): replay the winner.
        await session.rollback()
        winner = await _existing(session, ctx.device.id, ctx.req.event_id)
        if winner is None:
            raise
        return winner
    await session.refresh(ev)
    return ev


async def _update_summary(
    session: AsyncSession, employee_id: str, site_id: str | None, tz: str
) -> None:
    """Recompute the derived daily rollup from marked events for that local day."""
    # Pull a generous window and filter by local date in Python (portable).
    since = utcnow() - timedelta(days=2)
    rows = list(
        await session.scalars(
            select(AttendanceEvent)
            .where(
                AttendanceEvent.employee_id == employee_id,
                AttendanceEvent.outcome == Outcome.marked.value,
                AttendanceEvent.server_time >= since,
            )
            .order_by(AttendanceEvent.server_time.asc())
        )
    )
    today = _local_date(utcnow(), tz)
    day_events = [e for e in rows if _local_date(e.server_time, tz) == today]
    if not day_events:
        return

    first_in = next(
        (as_utc(e.server_time) for e in day_events if e.direction == Direction.check_in.value),
        None,
    )
    last_out = next(
        (
            as_utc(e.server_time)
            for e in reversed(day_events)
            if e.direction == Direction.check_out.value
        ),
        None,
    )

    worked = 0.0
    open_in: datetime | None = None
    for e in day_events:
        if e.direction == Direction.check_in.value:
            open_in = as_utc(e.server_time)
        elif e.direction == Direction.check_out.value and open_in is not None:
            worked += (as_utc(e.server_time) - open_in).total_seconds()
            open_in = None

    summary = await session.scalar(
        select(DailyAttendanceSummary).where(
            DailyAttendanceSummary.employee_id == employee_id,
            DailyAttendanceSummary.work_date == today,
        )
    )
    if summary is None:
        summary = DailyAttendanceSummary(
            employee_id=employee_id, work_date=today, site_id=site_id
        )
        session.add(summary)
    summary.site_id = site_id
    summary.first_in = first_in
    summary.last_out = last_out
    summary.worked_seconds = int(worked)
    summary.event_count = len(day_events)
    await session.commit()


# --- entrypoint --------------------------------------------------------------

async def process_event(
    session: AsyncSession,
    req: AttendanceEventRequest,
    device: Device,
) -> AttendanceEventResponse:
    now = utcnow()

    # 1. Idempotency: same (device, event_id) -> no new mark. Report
    #    `duplicate_ignored` (a success outcome for the client) carrying the
    #    original decision's direction/similarity.
    prior = await _existing(session, device.id, req.event_id)
    if prior is not None:
        audit(
            "attendance.replay",
            device_id=device.id,
            event_id=req.event_id,
            original_outcome=prior.outcome,
        )
        return AttendanceEventResponse(
            outcome=Outcome.duplicate_ignored,
            direction=Direction(prior.direction) if prior.direction else None,
            employee_name=await _employee_name(session, prior.employee_id),
            server_time=as_utc(prior.server_time),
            similarity=prior.similarity,
        )

    # 2. Model version must match the server's active model.
    if req.model_version != settings.model_version:
        raise PipelineError(
            409,
            f"model_version {req.model_version!r} != server {settings.model_version!r}",
        )

    # 3. Embedding shape + clock sanity.
    try:
        probe = l2_normalize(validate_dim(to_vector(req.embedding)))
    except ValueError as e:
        raise PipelineError(422, f"bad embedding: {e}")

    captured = as_utc(req.device_captured_at)
    if captured - now > timedelta(seconds=settings.clock_skew_seconds):
        raise PipelineError(422, "device_captured_at is in the future (clock skew)")
    if now - captured > MAX_EVENT_AGE:
        raise PipelineError(422, "event older than retention window")

    ctx = _Ctx(req=req, device=device, now=now, probe=probe)

    # 4. Quality + liveness (device already gates; server re-checks as defense).
    if req.quality.liveness_score < settings.min_liveness_score:
        ev = await _persist(
            session, ctx, outcome=Outcome.rejected_liveness, direction=None,
            similarity=None, employee_id=req.employee_id, site_id=None,
            note=f"liveness {req.quality.liveness_score:.2f} < {settings.min_liveness_score}",
        )
        audit("attendance.rejected_liveness", device_id=device.id, event_id=req.event_id)
        return _response(ev, await _employee_name(session, req.employee_id))
    if req.quality.face_score < settings.min_face_score:
        ev = await _persist(
            session, ctx, outcome=Outcome.rejected_liveness, direction=None,
            similarity=None, employee_id=req.employee_id, site_id=None,
            note=f"face_score {req.quality.face_score:.2f} < {settings.min_face_score}",
        )
        audit("attendance.rejected_quality", device_id=device.id, event_id=req.event_id)
        return _response(ev, await _employee_name(session, req.employee_id))

    # 5. Claimed employee must exist and be active.
    employee = await session.get(Employee, req.employee_id)
    if employee is None or not employee.active:
        ev = await _persist(
            session, ctx, outcome=Outcome.rejected_identity, direction=None,
            similarity=None, employee_id=req.employee_id, site_id=None,
            note="unknown or inactive employee",
        )
        audit("attendance.unknown_employee", device_id=device.id, event_id=req.event_id)
        return _response(ev, None)

    # 6. Server-side 1:1 verification against the claimed employee.
    verify = await recognition_service.verify_1_1(
        session, employee.id, probe, req.model_version
    )
    if not verify.matched:
        outcome = (
            Outcome.queued_for_review
            if verify.similarity >= settings.review_low_threshold
            else Outcome.rejected_identity
        )
        ev = await _persist(
            session, ctx, outcome=outcome, direction=None,
            similarity=verify.similarity, employee_id=employee.id,
            site_id=employee.site_id,
            note=f"1:1 {verify.similarity:.3f} vs accept {settings.accept_threshold}",
        )
        audit(
            "attendance.identity_not_confirmed",
            device_id=device.id, event_id=req.event_id,
            similarity=verify.similarity, outcome=outcome.value,
        )
        return _response(ev, employee.name)

    # 7. 1:N collision: does someone else match better by > margin?
    collision = await recognition_service.collision_check_1_n(
        session, employee.id, probe, req.model_version, employee.site_id
    )
    if collision.collision and collision.similarity - verify.similarity > settings.collision_margin:
        ev = await _persist(
            session, ctx, outcome=Outcome.rejected_identity, direction=None,
            similarity=verify.similarity, employee_id=employee.id,
            site_id=employee.site_id,
            note=f"collision with {collision.other_employee_id} @ {collision.similarity:.3f}",
        )
        audit(
            "attendance.collision",
            device_id=device.id, event_id=req.event_id,
            claimed=employee.id, other=collision.other_employee_id,
        )
        return _response(ev, employee.name)

    # 8. Soft debounce: a *different* event id arriving too soon after the last
    #    accepted mark for this employee.
    last_marked = await session.scalar(
        select(AttendanceEvent)
        .where(
            AttendanceEvent.employee_id == employee.id,
            AttendanceEvent.outcome == Outcome.marked.value,
        )
        .order_by(AttendanceEvent.server_time.desc())
        .limit(1)
    )
    if last_marked is not None:
        gap = (now - as_utc(last_marked.server_time)).total_seconds()
        if gap < settings.debounce_seconds:
            ev = await _persist(
                session, ctx, outcome=Outcome.duplicate_ignored,
                direction=Direction(last_marked.direction) if last_marked.direction else None,
                similarity=verify.similarity, employee_id=employee.id,
                site_id=employee.site_id,
                note=f"debounced ({gap:.0f}s < {settings.debounce_seconds}s)",
            )
            audit(
                "attendance.debounced",
                device_id=device.id, event_id=req.event_id, gap_seconds=gap,
            )
            return _response(ev, employee.name)

    # 9. Site rule.
    if settings.enforce_site_match and employee.site_id != device.site_id:
        ev = await _persist(
            session, ctx, outcome=Outcome.wrong_site, direction=None,
            similarity=verify.similarity, employee_id=employee.id,
            site_id=employee.site_id,
            note=f"employee site {employee.site_id} != device site {device.site_id}",
        )
        audit("attendance.wrong_site", device_id=device.id, event_id=req.event_id)
        return _response(ev, employee.name)

    # 10. Shift window rule.
    if settings.enforce_shift_window and employee.shift_start and employee.shift_end:
        try:
            local_now = as_utc(now).astimezone(ZoneInfo(employee.timezone)).time()
        except Exception:
            local_now = as_utc(now).time()
        grace = timedelta(minutes=settings.shift_grace_minutes)
        lo = (
            datetime.combine(date.today(), employee.shift_start) - grace
        ).time()
        hi = (
            datetime.combine(date.today(), employee.shift_end) + grace
        ).time()
        if not (lo <= local_now <= hi):
            ev = await _persist(
                session, ctx, outcome=Outcome.outside_shift, direction=None,
                similarity=verify.similarity, employee_id=employee.id,
                site_id=employee.site_id, note=f"local {local_now} outside {lo}-{hi}",
            )
            audit("attendance.outside_shift", device_id=device.id, event_id=req.event_id)
            return _response(ev, employee.name)

    # 11. Direction: toggle from the last marked event today; default check_in.
    prev_today = await _last_marked_today(session, employee.id, employee.timezone, now)
    if prev_today is None or prev_today.direction == Direction.check_out.value:
        direction = Direction.check_in
    else:
        direction = Direction.check_out

    # 12. Append the marked event.
    ev = await _persist(
        session, ctx, outcome=Outcome.marked, direction=direction,
        similarity=verify.similarity, employee_id=employee.id,
        site_id=employee.site_id, note=None,
    )
    if ev.outcome != Outcome.marked.value:  # lost the idempotency race
        return _response(ev, employee.name)

    # 13. Refresh the derived summary.
    await _update_summary(session, employee.id, employee.site_id, employee.timezone)

    audit(
        "attendance.marked",
        device_id=device.id, event_id=req.event_id, employee_id=employee.id,
        direction=direction.value, similarity=verify.similarity,
    )
    return _response(ev, employee.name)
