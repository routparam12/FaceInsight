from datetime import datetime

from pydantic import BaseModel


class EmbeddingResult(BaseModel):
    embedding_id: str
    source_image_id: str
    model_version: str
    created_at: datetime


class EnrollmentResponse(BaseModel):
    employee_id: str
    gallery_version: int
    results: list[EmbeddingResult]


class ReembedRequest(BaseModel):
    target_model_version: str
    site_id: str | None = None  # limit scope; None = all sites


class ReembedResponse(BaseModel):
    target_model_version: str
    employees_processed: int
    embeddings_created: int
    gallery_version: int
