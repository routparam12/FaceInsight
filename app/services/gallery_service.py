"""Delta + full gallery sync for devices, driven by the GalleryChange log."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.face_embedding import FaceEmbedding
from app.models.gallery_change import GalleryChange
from app.schemas.gallery import (
    GalleryDeltaResponse,
    GalleryEntry,
    GalleryFullResponse,
)


async def current_version(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.coalesce(func.max(GalleryChange.id), 0))))


async def record_change(
    session: AsyncSession, *, employee_id: str, site_id: str, op: str, model_version: str
) -> int:
    """Append a change and return the new gallery version. Caller commits."""
    row = GalleryChange(
        employee_id=employee_id, site_id=site_id, op=op, model_version=model_version
    )
    session.add(row)
    await session.flush()
    return int(row.id)


async def _embeddings_for(
    session: AsyncSession, employee_id: str, model_version: str
) -> list[list[float]]:
    rows = await session.scalars(
        select(FaceEmbedding.vector).where(
            FaceEmbedding.employee_id == employee_id,
            FaceEmbedding.model_version == model_version,
        )
    )
    return [list(r) for r in rows]


async def get_delta(
    session: AsyncSession, site_id: str, since_version: int
) -> GalleryDeltaResponse:
    latest = await current_version(session)
    rows = list(
        await session.scalars(
            select(GalleryChange)
            .where(
                GalleryChange.site_id == site_id,
                GalleryChange.id > since_version,
            )
            .order_by(GalleryChange.id.asc())
        )
    )

    # Collapse to the last op per employee within the window.
    last_op: dict[str, GalleryChange] = {}
    for r in rows:
        last_op[r.employee_id] = r

    changes: list[GalleryEntry] = []
    for emp_id, r in last_op.items():
        if r.op == "remove":
            changes.append(GalleryEntry(employee_id=emp_id, op="remove"))
        else:
            changes.append(
                GalleryEntry(
                    employee_id=emp_id,
                    op="upsert",
                    model_version=settings.model_version,
                    embeddings=await _embeddings_for(
                        session, emp_id, settings.model_version
                    ),
                )
            )
    return GalleryDeltaResponse(
        site_id=site_id,
        since_version=since_version,
        version=latest,
        changes=changes,
    )


async def get_full(session: AsyncSession, site_id: str) -> GalleryFullResponse:
    latest = await current_version(session)
    # Every employee at the site that currently has a non-removed change.
    rows = list(
        await session.scalars(
            select(GalleryChange)
            .where(GalleryChange.site_id == site_id)
            .order_by(GalleryChange.id.asc())
        )
    )
    last_op: dict[str, str] = {}
    for r in rows:
        last_op[r.employee_id] = r.op

    entries: list[GalleryEntry] = []
    for emp_id, op in last_op.items():
        if op == "remove":
            continue
        emb = await _embeddings_for(session, emp_id, settings.model_version)
        if not emb:
            continue
        entries.append(
            GalleryEntry(
                employee_id=emp_id,
                op="upsert",
                model_version=settings.model_version,
                embeddings=emb,
            )
        )
    return GalleryFullResponse(
        site_id=site_id,
        version=latest,
        model_version=settings.model_version,
        entries=entries,
    )
