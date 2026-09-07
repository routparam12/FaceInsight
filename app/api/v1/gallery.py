from fastapi import APIRouter, Query

from app.api.deps import DeviceDep, SessionDep
from app.schemas.gallery import GalleryDeltaResponse, GalleryFullResponse
from app.services import gallery_service

router = APIRouter(prefix="/gallery", tags=["gallery"])


@router.get("", response_model=GalleryDeltaResponse)
async def gallery_delta(
    session: SessionDep,
    device: DeviceDep,
    since_version: int = Query(0, ge=0),
    site_id: str | None = Query(None),
):
    # A device only ever syncs its own site.
    return await gallery_service.get_delta(
        session, site_id or device.site_id, since_version
    )


@router.get("/full", response_model=GalleryFullResponse)
async def gallery_full(
    session: SessionDep,
    device: DeviceDep,
    site_id: str | None = Query(None),
):
    return await gallery_service.get_full(session, site_id or device.site_id)
