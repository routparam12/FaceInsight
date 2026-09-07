"""Server-side identity checks. The device's local match is UX only; these
results are authoritative."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.face_embedding import FaceEmbedding
from app.services.face_service import cosine, to_vector


@dataclass
class VerifyResult:
    matched: bool
    similarity: float
    template_count: int


@dataclass
class CollisionResult:
    collision: bool
    other_employee_id: str | None
    similarity: float


async def _templates_for(
    session: AsyncSession, employee_id: str, model_version: str
) -> list[list[float]]:
    rows = await session.scalars(
        select(FaceEmbedding.vector).where(
            FaceEmbedding.employee_id == employee_id,
            FaceEmbedding.model_version == model_version,
        )
    )
    return [list(r) for r in rows]


async def verify_1_1(
    session: AsyncSession,
    employee_id: str,
    probe: np.ndarray,
    model_version: str,
) -> VerifyResult:
    templates = await _templates_for(session, employee_id, model_version)
    if not templates:
        return VerifyResult(matched=False, similarity=-1.0, template_count=0)
    best = max(cosine(probe, to_vector(t)) for t in templates)
    return VerifyResult(
        matched=best >= settings.accept_threshold,
        similarity=best,
        template_count=len(templates),
    )


async def collision_check_1_n(
    session: AsyncSession,
    claimed_employee_id: str,
    probe: np.ndarray,
    model_version: str,
    site_id: str | None,
) -> CollisionResult:
    """Does the probe match some *other* enrolled person better than the
    claimed one, by more than COLLISION_MARGIN? That signals gallery drift or
    an impersonation attempt.

    Portability: linear scan here. On Postgres, replace with a pgvector ANN
    query (`ORDER BY vector <=> :probe LIMIT k`) filtered to the site.
    """
    stmt = select(
        FaceEmbedding.employee_id, FaceEmbedding.vector
    ).where(FaceEmbedding.model_version == model_version)
    if site_id is not None:
        from app.models.employee import Employee

        stmt = stmt.join(Employee, Employee.id == FaceEmbedding.employee_id).where(
            Employee.site_id == site_id
        )

    best_other = -1.0
    best_other_id: str | None = None
    for emp_id, vec in (await session.execute(stmt)).all():
        if emp_id == claimed_employee_id:
            continue
        s = cosine(probe, to_vector(vec))
        if s > best_other:
            best_other, best_other_id = s, emp_id

    collided = (
        best_other >= settings.collision_threshold
        and best_other_id is not None
    )
    return CollisionResult(
        collision=collided,
        other_employee_id=best_other_id if collided else None,
        similarity=best_other,
    )
