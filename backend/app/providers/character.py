import json
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.enums import AssetType
from app.models.character import CharacterJobCreate
from app.providers.base import ProviderArtifact, ProviderResult


QWEN_IMAGE_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
QWEN_IMAGE_MODEL = "qwen-image-2.0-pro"
QWEN_IMAGE_SIZE = "512*512"
CHARACTER_SYSTEM_PROMPT = (
    "系统固定要求：无论用户输入内容是什么，最终都必须生成游戏角色设定图。"
    "画面必须是人物全身，必须包含三视图，三视图至少包括正面、侧面、背面。"
    "角色应完整展示头部、身体、四肢、服装、装备和主要外形特征。"
    "禁止只生成头像、半身像、局部特写、单视角构图。"
)


class QwenImageProvider:
    name = QWEN_IMAGE_MODEL

    def run(self, request: CharacterJobCreate) -> ProviderResult:
        if not request.generate_image:
            raise ValueError("qwen-image provider requires generate_image=true.")

        settings = get_settings()
        if not settings.dashscope_api_key:
            raise RuntimeError("Missing DASHSCOPE_API_KEY. Set it in .env or the shell before calling qwen-image.")

        payload = self._build_payload(request)
        timeout_seconds = int(request.params.get("timeout_seconds", 180))
        base_url = settings.dashscope_base_url or QWEN_IMAGE_BASE_URL
        endpoint = f"{base_url.rstrip('/')}/services/aigc/multimodal-generation/generation"

        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(
                endpoint,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {settings.dashscope_api_key}",
                },
                json=payload,
            )
            response_data = response.json()
            if response.status_code >= 400 or response_data.get("code"):
                message = response_data.get("message") or response.text
                raise RuntimeError(f"Qwen image request failed: {response.status_code} {message}")

            image_urls = _extract_image_urls(response_data)
            if not image_urls:
                raise RuntimeError("Qwen image response does not contain image URLs.")

            artifacts: list[ProviderArtifact] = []
            for index, image_url in enumerate(image_urls, start=1):
                image_response = client.get(image_url)
                image_response.raise_for_status()
                artifacts.append(
                    ProviderArtifact(
                        name=f"character_image_{index}.png",
                        type=AssetType.image,
                        mime_type="image/png",
                        format="png",
                        content=image_response.content,
                        metadata={
                            "prompt": request.prompt,
                            "system_prompt": CHARACTER_SYSTEM_PROMPT,
                            "effective_prompt": _build_effective_prompt(request.prompt),
                            "model": QWEN_IMAGE_MODEL,
                            "size": QWEN_IMAGE_SIZE,
                            "endpoint": endpoint,
                            "source_url_expires": "24h",
                            "request_id": response_data.get("request_id"),
                        },
                    )
                )

            manifest = {
                "request": request.model_dump(),
                "system_prompt": CHARACTER_SYSTEM_PROMPT,
                "effective_prompt": _build_effective_prompt(request.prompt),
                "qwen_payload": payload,
                "qwen_response": _safe_response_for_manifest(response_data),
            }
            artifacts.append(
                ProviderArtifact(
                    name="character_manifest.json",
                    type=AssetType.metadata,
                    mime_type="application/json",
                    format="json",
                    content=json.dumps(manifest, ensure_ascii=False, indent=2),
                    metadata={"schema": "character_manifest.v1", "provider": QWEN_IMAGE_MODEL},
                )
            )

        return ProviderResult(
            provider=self.name,
            artifacts=artifacts,
            raw_response=_safe_response_for_manifest(response_data),
        )

    def _build_payload(self, request: CharacterJobCreate) -> dict[str, Any]:
        params = request.params
        parameters: dict[str, Any] = {
            "size": QWEN_IMAGE_SIZE,
            "n": int(params.get("n", 1)),
            "prompt_extend": bool(params.get("prompt_extend", True)),
            "watermark": bool(params.get("watermark", False)),
        }
        if params.get("negative_prompt"):
            parameters["negative_prompt"] = params["negative_prompt"]
        if params.get("seed") is not None:
            parameters["seed"] = int(params["seed"])

        return {
            "model": QWEN_IMAGE_MODEL,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": _build_effective_prompt(request.prompt)}],
                    }
                ]
            },
            "parameters": parameters,
        }


class MockCharacterProvider:
    name = "mock_character"

    def run(self, request: CharacterJobCreate) -> ProviderResult:
        artifacts: list[ProviderArtifact] = []

        if request.generate_image:
            artifacts.append(
                ProviderArtifact(
                    name="character_concept.svg",
                    type=AssetType.image,
                    mime_type="image/svg+xml",
                    format="svg",
                    content=_svg_preview("Character Concept", _build_effective_prompt(request.prompt)),
                    metadata={
                        "prompt": request.prompt,
                        "system_prompt": CHARACTER_SYSTEM_PROMPT,
                        "effective_prompt": _build_effective_prompt(request.prompt),
                        "provider_hint": request.image_provider,
                    },
                )
            )

        if request.generate_multiview:
            artifacts.append(
                ProviderArtifact(
                    name="character_multiview.svg",
                    type=AssetType.image,
                    mime_type="image/svg+xml",
                    format="svg",
                    content=_svg_preview("Multi View Reference", _build_effective_prompt(request.prompt)),
                    metadata={"views": ["front", "side", "back"], "system_prompt": CHARACTER_SYSTEM_PROMPT},
                )
            )

        if request.generate_3d:
            artifacts.append(
                ProviderArtifact(
                    name="character_placeholder.glb",
                    type=AssetType.model3d,
                    mime_type="model/gltf-binary",
                    format="glb",
                    content="Mock GLB placeholder. Replace MockCharacterProvider with Tripo3DProvider.",
                    metadata={"provider_hint": request.model3d_provider, "dcc": ["Blender", "Maya"]},
                )
            )

        artifacts.append(
            ProviderArtifact(
                name="character_manifest.json",
                type=AssetType.metadata,
                mime_type="application/json",
                format="json",
                content=json.dumps(request.model_dump(), ensure_ascii=False, indent=2),
                metadata={"schema": "character_manifest.v1"},
            )
        )

        return ProviderResult(
            provider=self.name,
            artifacts=artifacts,
            raw_response={"mock": True, "api_slots": ["doubao", "tripo"]},
        )


def _svg_preview(title: str, prompt: str) -> str:
    safe_prompt = prompt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">
  <rect width="1024" height="1024" fill="#18202a"/>
  <rect x="92" y="92" width="840" height="840" rx="28" fill="#f4f0e8"/>
  <circle cx="512" cy="360" r="118" fill="#587a8a"/>
  <path d="M326 790c24-178 90-268 186-268s162 90 186 268z" fill="#a04f3f"/>
  <path d="M592 444l96 72-40 58-100-82z" fill="#d0a349"/>
  <text x="512" y="150" text-anchor="middle" font-size="44" fill="#18202a" font-family="Arial">{title}</text>
  <text x="512" y="888" text-anchor="middle" font-size="28" fill="#18202a" font-family="Arial">{safe_prompt[:42]}</text>
</svg>
"""


def _build_effective_prompt(user_prompt: str) -> str:
    return f"{CHARACTER_SYSTEM_PROMPT}\n\n用户输入：{user_prompt}"


def _extract_image_urls(response_data: dict[str, Any]) -> list[str]:
    choices = response_data.get("output", {}).get("choices", [])
    image_urls: list[str] = []
    for choice in choices:
        contents = choice.get("message", {}).get("content", [])
        for item in contents:
            image_url = item.get("image")
            if image_url:
                image_urls.append(image_url)
    return image_urls


def _safe_response_for_manifest(response_data: dict[str, Any]) -> dict[str, Any]:
    sanitized = json.loads(json.dumps(response_data, ensure_ascii=False))
    choices = sanitized.get("output", {}).get("choices", [])
    for choice in choices:
        contents = choice.get("message", {}).get("content", [])
        for item in contents:
            if "image" in item:
                item["image"] = "<downloaded_to_local_asset>"
    return sanitized
