import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Device(Base):
    """A kiosk / Android app instance.

    Lifecycle: admin creates the row -> one-time provisioning token is returned
    -> device exchanges it at /devices/activate for a long-lived access token
    -> admin can revoke at any time. Only hashes are stored.
    """

    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255))
    site_id: Mapped[str] = mapped_column(String(64), index=True)

    # active | revoked
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)

    provisioning_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provisioned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    access_token_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
