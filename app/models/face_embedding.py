import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FaceEmbedding(Base):
    """One enrolled template. Multiple rows per employee (angles, lighting,
    glasses). `vector` is L2-normalised at write time.

    Portability note: stored as JSON so sqlite works in dev/test. In production
    on Postgres, switch this column to pgvector `Vector(EMBEDDING_DIM)` and add
    an ANN index to make the server-side 1:N collision check cheap.
    """

    __tablename__ = "face_embeddings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True
    )
    source_image_id: Mapped[str | None] = mapped_column(
        ForeignKey("enrollment_images.id", ondelete="SET NULL"), nullable=True
    )
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    vector: Mapped[list[float]] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
