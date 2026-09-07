from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.deps import AdminDep, SessionDep
from app.models.employee import Employee
from app.schemas.enrollment import (
    EmbeddingResult,
    EnrollmentResponse,
    ReembedRequest,
    ReembedResponse,
)
from app.services import enrollment_service

router = APIRouter(prefix="/enrollment", tags=["enrollment"])


@router.post(
    "/{employee_id}/images",
    response_model=EnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def enroll_images(
    employee_id: str,
    session: SessionDep,
    _: AdminDep,
    files: list[UploadFile] = File(...),
):
    employee = await session.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "employee not found")

    results: list[EmbeddingResult] = []
    version = 0
    for f in files:
        data = await f.read()
        if not data:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "empty file")
        try:
            result, version = await enrollment_service.enroll_image(
                session, employee, data, f.content_type
            )
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
        results.append(
            EmbeddingResult(
                embedding_id=result.embedding_id,
                source_image_id=result.source_image_id,
                model_version=result.model_version,
                created_at=result.created_at,
            )
        )
    return EnrollmentResponse(
        employee_id=employee_id, gallery_version=version, results=results
    )


@router.post("/reembed", response_model=ReembedResponse)
async def reembed(body: ReembedRequest, session: SessionDep, _: AdminDep):
    """Model migration: regenerate all templates from retained source images."""
    try:
        outcome = await enrollment_service.reembed_gallery(
            session, body.target_model_version, body.site_id
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return ReembedResponse(
        target_model_version=body.target_model_version,
        employees_processed=outcome.employees_processed,
        embeddings_created=outcome.embeddings_created,
        gallery_version=outcome.gallery_version,
    )
