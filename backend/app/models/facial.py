from typing import Any

from pydantic import BaseModel, Field


class FacialJobCreate(BaseModel):
    input_asset_id: str
    provider: str = "mock_facial"
    output_standard: str = "arkit_52"
    include_head_pose: bool = True
    output_formats: list[str] = Field(default_factory=lambda: ["json", "csv"])
    params: dict[str, Any] = Field(default_factory=dict)

