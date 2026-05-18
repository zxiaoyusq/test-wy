from typing import Any

from pydantic import BaseModel, Field


class VideoJobCreate(BaseModel):
    prompt: str
    character_asset_ids: list[str] = Field(default_factory=list)
    duration_seconds: int = Field(default=5, ge=2, le=15)
    fps: int = Field(default=24, ge=1, le=120)
    resolution: str = "720P"
    provider: str = "wan2.7-i2v-2026-04-25"
    params: dict[str, Any] = Field(default_factory=dict)
