from typing import Any

from pydantic import BaseModel, Field


class CharacterJobCreate(BaseModel):
    prompt: str
    reference_image_asset_id: str | None = None
    generate_image: bool = True
    generate_multiview: bool = False
    generate_3d: bool = False
    image_provider: str = "qwen-image-2.0-pro"
    model3d_provider: str = "tripo"
    params: dict[str, Any] = Field(default_factory=dict)
