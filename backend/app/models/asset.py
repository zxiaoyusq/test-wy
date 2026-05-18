from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import AssetType, ModuleType


class AssetRecord(BaseModel):
    id: str
    type: AssetType
    module: ModuleType
    job_id: str
    name: str
    path: str
    mime_type: str
    format: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AssetSummary(BaseModel):
    id: str
    type: AssetType
    module: ModuleType
    job_id: str
    name: str
    url: str
    format: str
    metadata: dict[str, Any] = Field(default_factory=dict)

