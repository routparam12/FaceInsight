from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Outcome(str, Enum):
    marked = "marked"
    duplicate_ignored = "duplicate_ignored"
    rejected_identity = "rejected_identity"
    rejected_liveness = "rejected_liveness"
    outside_shift = "outside_shift"
    wrong_site = "wrong_site"
    queued_for_review = "queued_for_review"


class Direction(str, Enum):
    check_in = "check_in"
    check_out = "check_out"


class Quality(BaseModel):
    face_score: float = Field(ge=0.0, le=1.0)
    liveness_score: float = Field(ge=0.0, le=1.0)


class AttendanceEventRequest(BaseModel):
    event_id: str = Field(min_length=8, max_length=64)
    employee_id: str = Field(min_length=1, max_length=64)
    embedding: list[float]
    model_version: str
    device_captured_at: datetime
    quality: Quality
    # `direction` is intentionally NOT accepted from the client; the server
    # derives it from the employee's last event.


class AttendanceEventResponse(BaseModel):
    outcome: Outcome
    direction: Direction | None = None
    employee_name: str | None = None
    server_time: datetime
    similarity: float | None = None


class AttendanceEventRow(BaseModel):
    id: str
    client_event_id: str
    device_id: str
    employee_id: str | None
    outcome: Outcome
    direction: Direction | None
    similarity: float | None
    model_version: str
    site_id: str | None
    face_score: float | None
    liveness_score: float | None
    device_captured_at: datetime | None
    server_time: datetime

    model_config = {"from_attributes": True}
