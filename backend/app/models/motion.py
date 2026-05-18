from typing import Any

from pydantic import BaseModel, Field


class MotionJobCreate(BaseModel):
    input_video_asset_id: str
    provider: str = "mock_motion"
    target_skeleton: str = "humanoid"
    output_formats: list[str] = Field(default_factory=lambda: ["json", "bvh"])
    params: dict[str, Any] = Field(default_factory=dict)

