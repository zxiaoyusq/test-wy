import json
import mimetypes
import time
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.enums import AssetType
from app.models.motion import MotionJobCreate
from app.providers.base import ProviderArtifact, ProviderResult
# MediaPipe provider 单独放在 motion_mediapipe.py，这里 re-export 以便路由统一从 motion 拿
from app.providers.motion_mediapipe import (
    MEDIAPIPE_PROVIDER_NAME,
    MediaPipeMotionProvider,
)
from app.services.asset_service import asset_service


# 千面动捕开放平台默认 base，可在 .env 用 QMAI_BASE_URL 覆盖
QMAI_BASE_URL = "https://www.qmai.vip/business"
QIANMIAN_PROVIDER_NAME = "qianmian_motion"


class QianmianMotionProvider:
    """对接千面动捕 (https://www.qmai.vip) 的真实动捕 provider。

    流程：
        1. uploadCosCredential 申请 COS 预签名 PUT URL
        2. PUT 上传上游 MP4 二进制
        3. uploadCosConfirm 提交业务参数，拿到 videoId
        4. getStatus 轮询任务直至成功
        5. downloadCosCredential 拿到每个结果文件的 GET 下载地址并保存为本地 artifact
    """

    name = QIANMIAN_PROVIDER_NAME

    def run(self, request: MotionJobCreate) -> ProviderResult:
        settings = get_settings()
        if not settings.qmai_company_key:
            raise RuntimeError(
                "Missing QMAI_COMPANY_KEY. Set it in backend/.env before calling qianmian motion."
            )

        # 上游视频资产：必须存在且是 MP4
        source_asset = asset_service.get(request.input_video_asset_id)
        source_path = asset_service.resolve_path(source_asset)
        if source_asset.format.lower() != "mp4" and source_path.suffix.lower() != ".mp4":
            raise RuntimeError(
                f"Qianmian motion 只支持 MP4 输入，但当前资产为 format={source_asset.format} path={source_path.name}"
            )

        base_url = (settings.qmai_base_url or QMAI_BASE_URL).rstrip("/")
        company_key = settings.qmai_company_key
        # 视频逻辑名：优先用请求传入的，否则用文件名去掉扩展名
        video_name = (request.video_name or source_path.stem).strip()
        if not video_name:
            video_name = "motion_input"

        # 轮询参数：默认 15 秒一次，最多等 30 分钟
        poll_interval_seconds = int(request.params.get("poll_interval_seconds", 15))
        max_wait_seconds = int(request.params.get("max_wait_seconds", 1800))
        # 下载结果时是否带处理后视频/音频
        video_sign = int(request.params.get("video_sign", 0))

        # 单个 HTTP 请求最大超时（针对单次调用，不是整体）
        request_timeout = int(request.params.get("request_timeout_seconds", 120))

        with httpx.Client(timeout=request_timeout) as client:
            # 第 1 步：申请 COS 预签名 PUT 凭证
            cred = _call_qmai(
                client,
                "POST",
                f"{base_url}/uploadCosCredential",
                json_body={"companyKey": company_key, "suffix": ".mp4"},
                expect_status_field=True,
            )
            upload_url = cred.get("uploadUrl")
            cos_object_key = cred.get("cosObjectKey")
            if not upload_url or not cos_object_key:
                raise RuntimeError(f"千面 uploadCosCredential 返回缺少 uploadUrl/cosObjectKey：{cred}")

            # 第 2 步：直接 PUT 上传 MP4 二进制到 COS
            put_response = client.put(
                upload_url,
                content=source_path.read_bytes(),
                headers={"Content-Type": "video/mp4"},
            )
            if put_response.status_code >= 400:
                raise RuntimeError(
                    f"千面 COS 上传失败：HTTP {put_response.status_code} {put_response.text[:200]}"
                )

            # 第 3 步：确认上传 + 提交业务参数，创建动捕任务
            confirm_payload: dict[str, Any] = {
                "companyKey": company_key,
                "cosObjectKey": cos_object_key,
                "videoName": video_name,
                "bonetype": request.bonetype,
                "capturetype": request.capturetype,
                "frameRate": request.frame_rate,
                "poseType": request.pose_type,
                "standPose": request.stand_pose,
            }
            # 用户可在 params 里透传更多文档里的可选字段（mulPersonInfo、isStaticCamera 等）
            for extra_key in (
                "mulPersonInfo",
                "isStaticCamera",
                "halfWholeBodyCheck",
                "description",
                "rollbackUrl",
                "modelUrl",
                "piercing",
                "physicType",
                "physicTimes",
            ):
                if extra_key in request.params:
                    confirm_payload[extra_key] = request.params[extra_key]

            confirm = _call_qmai(
                client,
                "POST",
                f"{base_url}/uploadCosConfirm",
                json_body=confirm_payload,
                expect_status_field=True,
            )
            video_id = confirm.get("videoId")
            if not video_id or str(video_id) == "-1":
                raise RuntimeError(f"千面 uploadCosConfirm 未返回有效 videoId：{confirm}")

            # 第 4 步：轮询任务状态，直至成功或超时
            status_snapshot = _poll_status(
                client,
                base_url,
                company_key,
                str(video_id),
                poll_interval_seconds,
                max_wait_seconds,
            )

            # 第 5 步：拉取结果文件下载凭证并逐个下载，写为 artifact
            download_info = _call_qmai(
                client,
                "POST",
                f"{base_url}/downloadCosCredential",
                json_body={
                    "companyKey": company_key,
                    "videoId": str(video_id),
                    "videoSign": video_sign,
                },
                expect_status_field=True,
            )
            files = download_info.get("files") or []
            if not files:
                raise RuntimeError(f"千面 downloadCosCredential 未返回任何结果文件：{download_info}")

            artifacts: list[ProviderArtifact] = []
            for file_info in files:
                file_name = file_info.get("fileName")
                download_url = file_info.get("downloadUrl")
                if not file_name or not download_url:
                    # 异常项跳过即可，保留 manifest 里完整信息便于排查
                    continue
                file_resp = client.get(download_url)
                file_resp.raise_for_status()
                artifacts.append(
                    _build_artifact_for_file(
                        file_name=file_name,
                        content=file_resp.content,
                        source_asset_id=source_asset.id,
                        video_id=str(video_id),
                        bonetype=request.bonetype,
                        capturetype=request.capturetype,
                    )
                )

        # 最后追加一份 manifest，把请求与上游响应快照都留下来，便于复现/审计
        manifest = {
            "provider": self.name,
            "request": request.model_dump(),
            "source_asset": source_asset.model_dump(mode="json"),
            "qmai": {
                "video_id": str(video_id),
                "video_name": video_name,
                "cos_object_key": cos_object_key,
                "confirm_response": confirm,
                "status_snapshot": status_snapshot,
                "archive_name": download_info.get("archiveName"),
                "files": [
                    {"fileName": f.get("fileName")}
                    for f in files
                    if isinstance(f, dict)
                ],
            },
        }
        artifacts.append(
            ProviderArtifact(
                name="motion_manifest.json",
                type=AssetType.metadata,
                mime_type="application/json",
                format="json",
                content=json.dumps(manifest, ensure_ascii=False, indent=2),
                metadata={"schema": "motion_manifest.v1", "provider": self.name},
            )
        )

        return ProviderResult(
            provider=self.name,
            external_task_id=str(video_id),
            artifacts=artifacts,
            raw_response={
                "video_id": str(video_id),
                "archive_name": download_info.get("archiveName"),
            },
        )


class MockMotionProvider:
    name = "mock_motion"

    def run(self, request: MotionJobCreate) -> ProviderResult:
        keypoints = {
            "fps": request.params.get("fps", 30),
            "coordinate_system": request.params.get("coordinate_system", "y_up"),
            "target_skeleton": request.target_skeleton,
            "frames": [
                {
                    "t": 0.0,
                    "hips": [0.0, 1.0, 0.0],
                    "spine": [0.0, 1.4, 0.0],
                    "left_hand": [-0.35, 1.45, 0.05],
                    "right_hand": [0.45, 1.42, 0.08],
                },
                {
                    "t": 0.033,
                    "hips": [0.0, 1.01, 0.0],
                    "spine": [0.0, 1.41, 0.0],
                    "left_hand": [-0.34, 1.46, 0.06],
                    "right_hand": [0.47, 1.43, 0.09],
                },
            ],
        }
        return ProviderResult(
            provider=self.name,
            artifacts=[
                ProviderArtifact(
                    name="motion_keypoints.json",
                    type=AssetType.motion,
                    mime_type="application/json",
                    format="json",
                    content=json.dumps(keypoints, ensure_ascii=False, indent=2),
                    metadata={"schema": "motion_keypoints.v1"},
                ),
                ProviderArtifact(
                    name="output_motion.bvh",
                    type=AssetType.motion,
                    mime_type="text/plain",
                    format="bvh",
                    content=_bvh_placeholder(),
                    metadata={"target_skeleton": request.target_skeleton},
                ),
            ],
            raw_response={"mock": True, "source_asset_id": request.input_video_asset_id},
        )


def _unwrap_qmai_envelope(data: dict[str, Any]) -> dict[str, Any]:
    """剥掉千面网关层的 {code, message, data: {...}} 外壳。

    线上实测：开放平台部分接口返回会再包一层网关响应，业务字段都塞在 data 里。
    如果没有这层壳就原样返回。
    """
    if not isinstance(data, dict):
        return data
    inner = data.get("data")
    has_code_field = "code" in data
    if isinstance(inner, dict) and has_code_field:
        outer_code = data.get("code")
        if outer_code not in (None, 0, "0"):
            raise RuntimeError(
                f"千面网关层失败 code={outer_code}：{data.get('message')}"
            )
        return inner
    return data


def _call_qmai(
    client: httpx.Client,
    method: str,
    url: str,
    json_body: dict[str, Any] | None = None,
    expect_status_field: bool = True,
) -> dict[str, Any]:
    """统一封装千面接口调用：解析 JSON、把 status != 200 当作业务失败抛出。"""
    response = client.request(method, url, json=json_body)
    if response.status_code >= 500:
        # 千面文档里明确写过：无结果等内部异常会返回 500 且无 body
        raise RuntimeError(
            f"千面接口 {url} 返回 HTTP {response.status_code}：{response.text[:200] or '<empty body>'}"
        )
    try:
        data = response.json()
    except ValueError:
        raise RuntimeError(f"千面接口 {url} 响应不是合法 JSON：{response.text[:200]}")

    if response.status_code >= 400:
        message = data.get("message") if isinstance(data, dict) else None
        raise RuntimeError(f"千面接口 {url} HTTP {response.status_code}：{message or response.text[:200]}")

    # 千面网关实测会在文档示例外再包一层 {code, message, data: {...}}；
    # 这里自动剥壳，让上层只关心业务字段（uploadUrl / cosObjectKey / videoId / files 等）。
    data = _unwrap_qmai_envelope(data) if isinstance(data, dict) else data

    if expect_status_field and isinstance(data, dict):
        status = str(data.get("status", "")) if data.get("status") is not None else ""
        # 千面返回的 status 是字符串 "200"/"600"/"500"
        if status and status != "200":
            message = data.get("message") or data
            raise RuntimeError(f"千面接口 {url} 业务失败 status={status}：{message}")

    return data if isinstance(data, dict) else {"raw": data}


def _poll_status(
    client: httpx.Client,
    base_url: str,
    company_key: str,
    video_id: str,
    poll_interval_seconds: int,
    max_wait_seconds: int,
) -> dict[str, Any]:
    """轮询 getStatus，直到 videoStatus 表示已完成。

    文档说明：成功时 videoStatus 是可读文案（待制作 / 制作中 / 已完成 等），
    没有标准化的枚举，因此我们用关键字匹配判断成功/失败/进行中。
    """
    # 路径中的 videoId / companyKey 用文档建议的方式保持原样（companyKey 是 UUID，不含特殊字符）
    status_url = f"{base_url}/getStatus/{video_id}/{company_key}"
    deadline = time.monotonic() + max_wait_seconds
    poll_interval = max(5, poll_interval_seconds)

    while True:
        # getStatus 无请求体，按文档使用 POST
        response = client.post(status_url)
        if response.status_code >= 500:
            # 任务尚未生效时千面可能会偶发 5xx，等下一轮再试
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"千面任务 {video_id} 状态查询持续 5xx，已超过 {max_wait_seconds} 秒"
                )
            time.sleep(poll_interval)
            continue

        try:
            data = response.json()
        except ValueError:
            raise RuntimeError(
                f"千面 getStatus 响应不是合法 JSON：HTTP {response.status_code} {response.text[:200]}"
            )

        # 同样处理网关层的 {code, message, data: {...}} 外壳
        data = _unwrap_qmai_envelope(data)

        video_status_text = (data.get("videoStatus") or "").strip()
        message = data.get("message")
        # 成功关键字：千面线上常见的"已完成 / 制作完成 / 已成功 / 完成"
        if any(token in video_status_text for token in ("已完成", "完成", "成功", "Success", "SUCCESS")):
            return data
        # 失败关键字：包含"失败"/"异常"，或 message 是错误文案（status=200 但 message 仍可能是错误说明）
        if any(token in video_status_text for token in ("失败", "异常", "错误")):
            raise RuntimeError(
                f"千面任务 {video_id} 失败：videoStatus={video_status_text} message={message}"
            )
        # 进行中或排队中：直接等下一次
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"千面任务 {video_id} 等待超时 {max_wait_seconds} 秒，当前 videoStatus={video_status_text}"
            )
        time.sleep(poll_interval)


def _build_artifact_for_file(
    file_name: str,
    content: bytes,
    source_asset_id: str,
    video_id: str,
    bonetype: int,
    capturetype: str,
) -> ProviderArtifact:
    """根据文件名后缀决定 AssetType 与 mime/format。

    动捕结果可能包含 .fbx / .bvh / .json / .vmd / .anim / .mp4 等多种格式，
    这里做最小化分类：视频 → AssetType.video，其它一律归到 AssetType.motion。
    """
    suffix = Path(file_name).suffix.lower().lstrip(".") or "bin"
    mime_guess, _ = mimetypes.guess_type(file_name)
    if suffix == "mp4":
        asset_type = AssetType.video
        mime = mime_guess or "video/mp4"
    elif suffix == "json":
        asset_type = AssetType.motion
        mime = "application/json"
    elif suffix in {"bvh", "csv", "txt", "vmd", "anim"}:
        asset_type = AssetType.motion
        mime = mime_guess or "text/plain"
    else:
        # FBX / GLB / 其它二进制
        asset_type = AssetType.motion
        mime = mime_guess or "application/octet-stream"

    return ProviderArtifact(
        name=file_name,
        type=asset_type,
        mime_type=mime,
        format=suffix,
        content=content,
        metadata={
            "provider": QIANMIAN_PROVIDER_NAME,
            "qmai_video_id": video_id,
            "source_asset_id": source_asset_id,
            "bonetype": bonetype,
            "capturetype": capturetype,
        },
    )


def _bvh_placeholder() -> str:
    return """HIERARCHY
ROOT Hips
{
  OFFSET 0.00 1.00 0.00
  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
  JOINT Spine
  {
    OFFSET 0.00 0.40 0.00
    CHANNELS 3 Zrotation Xrotation Yrotation
    End Site
    {
      OFFSET 0.00 0.20 0.00
    }
  }
}
MOTION
Frames: 2
Frame Time: 0.0333333
0 1 0 0 0 0 0 0 0
0 1.01 0 0 1 0 0 0 0
"""
