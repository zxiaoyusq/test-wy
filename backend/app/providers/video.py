import json
import base64
import time
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.enums import AssetType
from app.models.video import VideoJobCreate
from app.providers.base import ProviderArtifact, ProviderResult
from app.services.asset_service import asset_service


WAN_VIDEO_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
WAN_VIDEO_MODEL = "wan2.7-i2v-2026-04-25"
WAN_VIDEO_ENDPOINT_PATH = "/services/aigc/video-generation/video-synthesis"


class WanImageToVideoProvider:
    name = WAN_VIDEO_MODEL

    def run(self, request: VideoJobCreate) -> ProviderResult:
        if not request.character_asset_ids:
            raise ValueError("Wan image-to-video requires one character image asset as first_frame input.")

        settings = get_settings()
        if not settings.dashscope_api_key:
            raise RuntimeError("Missing DASHSCOPE_API_KEY. Set it in .env or the shell before calling Wan video.")

        first_frame_asset = asset_service.get(request.character_asset_ids[0])
        first_frame_path = asset_service.resolve_path(first_frame_asset)
        first_frame_url = _image_file_to_data_url(first_frame_path, first_frame_asset.mime_type)
        payload = _build_wan_payload(request, first_frame_url)

        timeout_seconds = int(request.params.get("timeout_seconds", 900))
        poll_interval_seconds = int(request.params.get("poll_interval_seconds", 15))
        max_wait_seconds = int(request.params.get("max_wait_seconds", 900))
        base_url = settings.dashscope_base_url or WAN_VIDEO_BASE_URL
        endpoint = f"{base_url.rstrip('/')}{WAN_VIDEO_ENDPOINT_PATH}"

        headers = {
            "Authorization": f"Bearer {settings.dashscope_api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }

        with httpx.Client(timeout=timeout_seconds) as client:
            submit_response = client.post(endpoint, headers=headers, json=payload)
            submit_data = submit_response.json()
            if submit_response.status_code >= 400 or submit_data.get("code"):
                message = submit_data.get("message") or submit_response.text
                raise RuntimeError(f"Wan video submit failed: {submit_response.status_code} {message}")

            task_id = submit_data.get("output", {}).get("task_id")
            if not task_id:
                raise RuntimeError("Wan video submit response does not contain task_id.")

            result_data = _poll_task(client, base_url, headers, task_id, poll_interval_seconds, max_wait_seconds)
            output = result_data.get("output", {})
            video_url = output.get("video_url")
            if not video_url:
                raise RuntimeError("Wan video succeeded response does not contain video_url.")

            video_response = client.get(video_url)
            video_response.raise_for_status()

        manifest = {
            "request": request.model_dump(),
            "source_asset": first_frame_asset.model_dump(mode="json"),
            "wan_payload": _safe_payload_for_manifest(payload),
            "submit_response": submit_data,
            "result_response": _safe_response_for_manifest(result_data),
        }

        return ProviderResult(
            provider=self.name,
            external_task_id=task_id,
            artifacts=[
                ProviderArtifact(
                    name="output_video.mp4",
                    type=AssetType.video,
                    mime_type="video/mp4",
                    format="mp4",
                    content=video_response.content,
                    metadata={
                        "model": WAN_VIDEO_MODEL,
                        "task_id": task_id,
                        "source_asset_id": first_frame_asset.id,
                        "duration_seconds": request.duration_seconds,
                        "resolution": _normalize_resolution(request.resolution),
                        "source_url_expires": "24h",
                    },
                ),
                ProviderArtifact(
                    name="video_config.json",
                    type=AssetType.metadata,
                    mime_type="application/json",
                    format="json",
                    content=json.dumps(manifest, ensure_ascii=False, indent=2),
                    metadata={"schema": "video_config.v1", "provider": WAN_VIDEO_MODEL},
                ),
            ],
            raw_response=_safe_response_for_manifest(result_data),
        )


class MockVideoProvider:
    name = "mock_video"

    def run(self, request: VideoJobCreate) -> ProviderResult:
        return ProviderResult(
            provider=self.name,
            artifacts=[
                ProviderArtifact(
                    name="video_storyboard.svg",
                    type=AssetType.preview,
                    mime_type="image/svg+xml",
                    format="svg",
                    content=_storyboard_svg(request.prompt),
                    metadata={"duration_seconds": request.duration_seconds, "fps": request.fps},
                ),
                ProviderArtifact(
                    name="output_mock.mp4",
                    type=AssetType.video,
                    mime_type="video/mp4",
                    format="mp4",
                    content="Mock MP4 placeholder. Replace MockVideoProvider with WanImageToVideoProvider.",
                    metadata={"provider_hint": request.provider},
                ),
                ProviderArtifact(
                    name="video_config.json",
                    type=AssetType.metadata,
                    mime_type="application/json",
                    format="json",
                    content=json.dumps(request.model_dump(), ensure_ascii=False, indent=2),
                    metadata={"schema": "video_config.v1"},
                ),
            ],
            raw_response={"mock": True, "api_slots": ["wan2.7-i2v-2026-04-25"]},
        )


def _storyboard_svg(prompt: str) -> str:
    safe_prompt = prompt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  <rect width="1280" height="720" fill="#101820"/>
  <rect x="80" y="80" width="1120" height="500" rx="18" fill="#e7ecef"/>
  <path d="M428 520c22-130 72-196 150-196s128 66 150 196z" fill="#9d4e42"/>
  <circle cx="578" cy="240" r="78" fill="#517f8f"/>
  <path d="M658 292l168 78-46 70-158-96z" fill="#d8a640"/>
  <text x="640" y="640" text-anchor="middle" font-size="32" fill="#e7ecef" font-family="Arial">{safe_prompt[:60]}</text>
</svg>
"""


def _build_wan_payload(request: VideoJobCreate, first_frame_url: str) -> dict[str, Any]:
    params = request.params
    input_payload: dict[str, Any] = {
        "prompt": request.prompt,
        "media": [
            {
                "type": "first_frame",
                "url": first_frame_url,
            }
        ],
    }
    if params.get("negative_prompt"):
        input_payload["negative_prompt"] = params["negative_prompt"]

    parameters: dict[str, Any] = {
        "resolution": _normalize_resolution(request.resolution),
        "duration": request.duration_seconds,
        "prompt_extend": bool(params.get("prompt_extend", True)),
        "watermark": bool(params.get("watermark", False)),
    }
    if params.get("seed") is not None:
        parameters["seed"] = int(params["seed"])

    return {
        "model": WAN_VIDEO_MODEL,
        "input": input_payload,
        "parameters": parameters,
    }


def _normalize_resolution(resolution: str) -> str:
    normalized = resolution.upper()
    if normalized in {"720P", "1080P"}:
        return normalized
    if "720" in normalized:
        return "720P"
    if "1080" in normalized:
        return "1080P"
    return "720P"


def _image_file_to_data_url(path: Path, mime_type: str) -> str:
    if mime_type not in {"image/png", "image/jpeg", "image/jpg", "image/bmp", "image/webp"}:
        raise ValueError(f"Wan first_frame requires an image asset, got {mime_type}.")
    normalized_mime_type = "image/jpeg" if mime_type == "image/jpg" else mime_type
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{normalized_mime_type};base64,{encoded}"


def _poll_task(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    task_id: str,
    poll_interval_seconds: int,
    max_wait_seconds: int,
) -> dict[str, Any]:
    task_url = f"{base_url.rstrip('/')}/tasks/{task_id}"
    deadline = time.monotonic() + max_wait_seconds
    query_headers = {"Authorization": headers["Authorization"]}

    while True:
        task_response = client.get(task_url, headers=query_headers)
        task_data = task_response.json()
        if task_response.status_code >= 400 or task_data.get("code"):
            message = task_data.get("message") or task_response.text
            raise RuntimeError(f"Wan video task query failed: {task_response.status_code} {message}")

        output = task_data.get("output", {})
        status = output.get("task_status")
        if status == "SUCCEEDED":
            return task_data
        if status in {"FAILED", "CANCELED", "UNKNOWN"}:
            message = output.get("message") or task_data.get("message") or status
            raise RuntimeError(f"Wan video task ended with {status}: {message}")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Wan video task timed out after {max_wait_seconds} seconds: {task_id}")

        time.sleep(max(3, poll_interval_seconds))


def _safe_payload_for_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = json.loads(json.dumps(payload, ensure_ascii=False))
    for media in sanitized.get("input", {}).get("media", []):
        if isinstance(media.get("url"), str) and media["url"].startswith("data:"):
            media["url"] = "<base64_image_data>"
    return sanitized


def _safe_response_for_manifest(response_data: dict[str, Any]) -> dict[str, Any]:
    sanitized = json.loads(json.dumps(response_data, ensure_ascii=False))
    output = sanitized.get("output", {})
    if "video_url" in output:
        output["video_url"] = "<downloaded_to_local_asset>"
    return sanitized
