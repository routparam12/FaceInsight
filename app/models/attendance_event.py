import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AttendanceEvent(Base):
    """Append-only. The source of truth; the daily summary is derived from it.

    Idempotency: (device_id, client_event_id) is unique, so retries of the same
    fire-and-forget POST collapse to one row. This is distinct from the soft
    time-debounce, which rejects *new* event ids that arrive too soon.
    """

    __tablename__ = "attendance_events"
    __table_args__ = (
        UniqueConstraint("device_id", "client_event_id", name="uq_device_event"),
        Index("ix_events_employee_time", "employee_id", "server_time"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    client_event_id: Mapped[str] = mapped_column(String(64))
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)

    # Claimed by the device; may be null on a hard identity rejection.
    employee_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)

    # marked | duplicate_ignored | rejected_identity | rejected_liveness
    # | outside_shift | wrong_site | queued_for_review
    outcome: Mapped[str] = mapped_column(String(32), index=True)
    # check_in | check_out | null
    direction: Mapped[str | None] = mapped_column(String(16), nullable=True)

    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_version: Mapped[str] = mapped_column(String(64))
    site_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    face_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    liveness_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Free-text reason for the outcome (audit aid; not part of the API contract).
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    device_captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    server_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
