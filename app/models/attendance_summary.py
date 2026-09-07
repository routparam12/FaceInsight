import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DailyAttendanceSummary(Base):
    """Derived rollup for reporting. Rebuildable at any time from
    attendance_events; never written to directly by clients."""

    __tablename__ = "daily_attendance_summary"
    __table_args__ = (
        UniqueConstraint("employee_id", "work_date", name="uq_employee_date"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    employee_id: Mapped[str] = mapped_column(String(64), index=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    site_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    first_in: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_out: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    worked_seconds: Mapped[int] = mapped_column(Integer, default=0)
    event_count: Mapped[int] = mapped_column(Integer, default=0)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
