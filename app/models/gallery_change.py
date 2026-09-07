from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GalleryChange(Base):
    """Monotonic change log that drives device delta sync.

    `id` is the gallery version. A device passes `since_version`; it gets every
    row after that, including `op="remove"` tombstones so revoked employees are
    dropped from local storage rather than lingering.
    """

    __tablename__ = "gallery_changes"

    # BIGINT on Postgres; INTEGER (rowid alias, so it autoincrements) on SQLite.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    employee_id: Mapped[str] = mapped_column(String(64), index=True)
    site_id: Mapped[str] = mapped_column(String(64), index=True)
    op: Mapped[str] = mapped_column(String(16))  # upsert | remove
    model_version: Mapped[str] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
