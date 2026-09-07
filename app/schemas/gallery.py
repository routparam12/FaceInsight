from pydantic import BaseModel


class GalleryEntry(BaseModel):
    employee_id: str
    op: str  # upsert | remove
    model_version: str | None = None
    # Present for upsert; one row per enrolled template.
    embeddings: list[list[float]] | None = None


class GalleryDeltaResponse(BaseModel):
    site_id: str
    since_version: int
    version: int  # latest version; pass back as since_version next time
    changes: list[GalleryEntry]


class GalleryFullResponse(BaseModel):
    site_id: str
    version: int
    model_version: str
    entries: list[GalleryEntry]
