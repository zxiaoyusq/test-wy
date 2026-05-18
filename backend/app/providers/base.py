from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import AssetType


class ProviderArtifact(BaseModel):
    name: str
    type: AssetType
    mime_type: str
    format: str
    content: str | bytes
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderResult(BaseModel):
    provider: str
    external_task_id: str | None = None
    artifacts: list[ProviderArtifact] = Field(default_factory=list)
    raw_response: dict[str, Any] = Field(default_factory=dict)
