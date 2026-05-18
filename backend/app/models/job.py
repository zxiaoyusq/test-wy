from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import JobStatus, ModuleType
from app.models.asset import AssetRecord


class JobRecord(BaseModel):
    id: str
    module: ModuleType
    status: JobStatus
    provider: str
    input: dict[str, Any]
    outputs: list[AssetRecord] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    jobs: list[JobRecord]

