"""Turn enrollment photos into gallery templates, and re-embed the whole
gallery on a model upgrade without re-enrolling anyone."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.employee import Employee
from app.models.enrollment_image import EnrollmentImage
from app.models.face_embedding import FaceEmbedding
from app.services import gallery_service
from app.services.face_service import get_encoder
from app.utils import image as imageutil
from app.utils.logging import audit


@dataclass
class EnrollResult:
    embedding_id: str
    source_image_id: str
    model_version: str
    created_at: object


async def enroll_image(
    session: AsyncSession,
    employee: Employee,
    data: bytes,
    content_type: str,
) -> tuple[EnrollResult, int]:
    imageutil.validate_content_type(content_type)
    encoder = get_encoder()

    sha = imageutil.sha256_hex(data)
    key = f"{employee.id}/{uuid.uuid4().hex}"
    encrypted = imageutil.save_bytes(key, data)

    src = EnrollmentImage(
        employee_id=employee.id,
        storage_key=key,
        content_type=content_type,
        sha256=sha,
        size_bytes=len(data),
        encrypted=encrypted,
    )
    session.add(src)
    await session.flush()

    vector = encoder.embed(data)
    emb = FaceEmbedding(
        employee_id=employee.id,
        source_image_id=src.id,
        model_version=encoder.model_version,
        vector=[float(x) for x in vector.tolist()],
    )
    session.add(emb)
    await session.flush()

    version = await gallery_service.record_change(
        session,
        employee_id=employee.id,
        site_id=employee.site_id,
        op="upsert",
        model_version=encoder.model_version,
    )
    await session.commit()
    await session.refresh(emb)

    audit(
        "enrollment.image",
        employee_id=employee.id,
        embedding_id=emb.id,
        model_version=encoder.model_version,
        gallery_version=version,
    )
    return EnrollResult(
        embedding_id=emb.id,
        source_image_id=src.id,
        model_version=encoder.model_version,
        created_at=emb.created_at,
    ), version


@dataclass
class ReembedOutcome:
    employees_processed: int
    embeddings_created: int
    gallery_version: int


async def reembed_gallery(
    session: AsyncSession, target_model_version: str, site_id: str | None
) -> ReembedOutcome:
    """Regenerate every template from retained source images under the active
    encoder. The encoder's model_version must equal `target_model_version`."""
    encoder = get_encoder()
    if encoder.model_version != target_model_version:
        raise ValueError(
            f"active encoder is {encoder.model_version!r}, not {target_model_version!r}"
        )

    stmt = select(Employee)
    if site_id:
        stmt = stmt.where(Employee.site_id == site_id)
    employees = list(await session.scalars(stmt))

    processed = 0
    created = 0
    version = await gallery_service.current_version(session)

    for employee in employees:
        images = list(
            await session.scalars(
                select(EnrollmentImage).where(
                    EnrollmentImage.employee_id == employee.id
                )
            )
        )
        if not images:
            continue

        # Skip if already embedded under the target version.
        existing = await session.scalar(
            select(FaceEmbedding.id).where(
                FaceEmbedding.employee_id == employee.id,
                FaceEmbedding.model_version == target_model_version,
            )
        )
        if existing:
            continue

        for src in images:
            data = imageutil.load_bytes(src.storage_key, src.encrypted)
            vector = encoder.embed(data)
            session.add(
                FaceEmbedding(
                    employee_id=employee.id,
                    source_image_id=src.id,
                    model_version=target_model_version,
                    vector=[float(x) for x in vector.tolist()],
                )
            )
            created += 1

        version = await gallery_service.record_change(
            session,
            employee_id=employee.id,
            site_id=employee.site_id,
            op="upsert",
            model_version=target_model_version,
        )
        processed += 1

    await session.commit()
    audit(
        "enrollment.reembed",
        target_model_version=target_model_version,
        employees_processed=processed,
        embeddings_created=created,
        gallery_version=version,
    )
    return ReembedOutcome(
        employees_processed=processed,
        embeddings_created=created,
        gallery_version=version,
    )
