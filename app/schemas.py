from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    type: str = Field(min_length=1, max_length=64)
    payload: dict = Field(default_factory=dict)
    max_attempts: int = Field(default=5, ge=1, le=25)


class JobOut(BaseModel):
    id: UUID
    type: str
    status: str
    payload: dict
    result: dict | None
    attempts: int
    max_attempts: int
    run_at: datetime
    locked_by: str | None
    locked_until: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
