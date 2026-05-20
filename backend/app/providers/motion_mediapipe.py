"""MediaPipe 动作捕捉 provider。

实现要点：
  1. 用 mediapipe.tasks PoseLandmarker (VIDEO 模式) 逐帧抽取 33 个 Pose 关键点
  2. 同时把骨架连线叠加到原帧上，写出一份预览 mp4
  3. 输出 motion_keypoints.json + motion_overlay.mp4 两份 artifact

注意：mediapipe 0.10.x 在 Python 3.13 上仅提供 tasks API，原来的
`mediapipe.solutions.pose / drawing_utils` 不可用，所以这里手动维护 POSE_CONNECTIONS。
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import cv2
import imageio_ffmpeg
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

from app.core.config import get_settings
from app.core.enums import AssetType
from app.models.motion import MotionJobCreate
from app.providers.base import ProviderArtifact, ProviderResult
from app.services.asset_service import asset_service


MEDIAPIPE_PROVIDER_NAME = "mediapipe_motion"

# MediaPipe Pose 33 个关键点的命名（顺序与官方 landmark 索引一一对应）
POSE_LANDMARK_NAMES = [
    "nose",
    "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear",
    "mouth_left", "mouth_right",
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_pinky", "right_pinky",
    "left_index", "right_index",
    "left_thumb", "right_thumb",
    "left_hip", "right_hip",
    "left_knee", "right_knee",
    "left_ankle", "right_ankle",
    "left_heel", "right_heel",
    "left_foot_index", "right_foot_index",
]

# Pose 骨架的连线对（索引对照 POSE_LANDMARK_NAMES）
# 与 mediapipe.solutions.pose.POSE_CONNECTIONS 保持一致，用于画预览
POSE_CONNECTIONS = [
    # 面部
    (0, 1), (1, 2), (2, 3), (3, 7),
    (0, 4), (4, 5), (5, 6), (6, 8),
    (9, 10),
    # 上半身
    (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21), (17, 19),
    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22), (18, 20),
    # 躯干 / 髋
    (11, 23), (12, 24), (23, 24),
    # 下半身
    (23, 25), (25, 27), (27, 29), (29, 31), (27, 31),
    (24, 26), (26, 28), (28, 30), (30, 32), (28, 32),
]


# 默认查找的模型路径：项目内 backend/data/models/pose_landmarker_lite.task
def _default_model_path() -> Path:
    return get_settings().data_dir / "models" / "pose_landmarker_lite.task"


class MediaPipeMotionProvider:
    """本地 MediaPipe Pose 动捕 provider，不依赖外部服务。"""

    name = MEDIAPIPE_PROVIDER_NAME

    def run(self, request: MotionJobCreate) -> ProviderResult:
        # 上游视频资产校验：必须存在且能被 OpenCV 读
        source_asset = asset_service.get(request.input_video_asset_id)
        source_path = asset_service.resolve_path(source_asset)

        # 用户可在 params 里覆盖以下默认值
        params = request.params
        model_path = Path(params.get("model_path") or _default_model_path())
        if not model_path.exists():
            raise RuntimeError(
                f"找不到 MediaPipe 模型文件 {model_path}，请确认已下载 pose_landmarker_lite.task"
            )
        # 默认置信度阈值参考官方推荐
        min_pose_detection_confidence = float(params.get("min_pose_detection_confidence", 0.5))
        min_pose_presence_confidence = float(params.get("min_pose_presence_confidence", 0.5))
        min_tracking_confidence = float(params.get("min_tracking_confidence", 0.5))
        num_poses = int(params.get("num_poses", 1))

        cap = cv2.VideoCapture(str(source_path))
        if not cap.isOpened():
            raise RuntimeError(f"OpenCV 打不开视频文件：{source_path}")

        # 读取视频元信息：宽高、fps、总帧数
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0

        # 把预览 mp4 先写到临时目录，最后再以 bytes 形式交给 storage_service
        overlay_tmp = Path(tempfile.mkstemp(suffix="_overlay.mp4")[1])
        # 通过 ffmpeg subprocess 写 H.264 mp4：OpenCV 自带的 mp4v 编码（MPEG-4 Part 2）
        # 不被主流浏览器 <video> 接受，必须用 libx264 + yuv420p + faststart 才能在前端原生播放
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        ffmpeg_cmd = [
            ffmpeg_exe,
            "-y",
            "-loglevel", "error",
            # 输入是从 stdin 读裸 BGR 帧
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{width}x{height}",
            "-r", f"{fps}",
            "-i", "-",
            # 输出 H.264 mp4
            "-an",
            "-vcodec", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "veryfast",
            "-movflags", "+faststart",
            str(overlay_tmp),
        ]
        ffmpeg_proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        # 初始化 PoseLandmarker（VIDEO 模式按时间戳推进）
        options = vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=num_poses,
            min_pose_detection_confidence=min_pose_detection_confidence,
            min_pose_presence_confidence=min_pose_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

        frames_output: list[dict[str, Any]] = []
        detected_frames = 0

        try:
            with vision.PoseLandmarker.create_from_options(options) as landmarker:
                frame_index = 0
                while True:
                    ok, frame_bgr = cap.read()
                    if not ok:
                        break

                    # MediaPipe 需要 RGB；时间戳单位是毫秒，必须单调递增
                    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    timestamp_ms = int(frame_index * 1000.0 / fps)
                    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    result = landmarker.detect_for_video(image, timestamp_ms)

                    # 收集当前帧的关键点数据（最多取第 0 个人）
                    landmarks_payload: list[dict[str, float]] | None = None
                    world_landmarks_payload: list[dict[str, float]] | None = None
                    if result.pose_landmarks:
                        detected_frames += 1
                        landmarks = result.pose_landmarks[0]
                        landmarks_payload = [
                            {
                                "name": POSE_LANDMARK_NAMES[i],
                                "x": float(lm.x),
                                "y": float(lm.y),
                                "z": float(lm.z),
                                "visibility": float(lm.visibility),
                            }
                            for i, lm in enumerate(landmarks)
                        ]
                        # 世界坐标（米为单位的近似 3D），下游做 retarget 时更稳
                        if result.pose_world_landmarks:
                            world = result.pose_world_landmarks[0]
                            world_landmarks_payload = [
                                {
                                    "name": POSE_LANDMARK_NAMES[i],
                                    "x": float(lm.x),
                                    "y": float(lm.y),
                                    "z": float(lm.z),
                                    "visibility": float(lm.visibility),
                                }
                                for i, lm in enumerate(world)
                            ]
                        # 把骨架画到当前帧（直接修改 frame_bgr）
                        _draw_pose_on_frame(frame_bgr, landmarks, width, height)

                    frames_output.append(
                        {
                            "frame": frame_index,
                            "t": round(timestamp_ms / 1000.0, 6),
                            "landmarks": landmarks_payload,
                            "world_landmarks": world_landmarks_payload,
                        }
                    )

                    writer_write_frame(ffmpeg_proc, frame_bgr)
                    frame_index += 1
        finally:
            cap.release()
            # 关闭 ffmpeg stdin，等其完成 mp4 写盘；如果失败则把 stderr 抛出来，便于排查
            try:
                if ffmpeg_proc.stdin is not None:
                    ffmpeg_proc.stdin.close()
            except BrokenPipeError:
                pass
            stderr_bytes = b""
            try:
                _, stderr_bytes = ffmpeg_proc.communicate(timeout=120)
            except subprocess.TimeoutExpired:
                ffmpeg_proc.kill()
                raise RuntimeError("ffmpeg 写 mp4 超时（>120s）")
            if ffmpeg_proc.returncode != 0:
                raise RuntimeError(
                    f"ffmpeg 编码失败 (returncode={ffmpeg_proc.returncode}): "
                    f"{stderr_bytes.decode('utf-8', errors='ignore')}"
                )

        # 读出预览 mp4 字节，存为 artifact 后即可删临时文件
        overlay_bytes = overlay_tmp.read_bytes()
        try:
            overlay_tmp.unlink()
        except OSError:
            pass

        # 组装 JSON：包含元信息 + 帧数据，schema 与 MockMotionProvider 兼容
        keypoints_doc: dict[str, Any] = {
            "schema": "mediapipe_pose.v1",
            "provider": self.name,
            "source_asset_id": source_asset.id,
            "model": model_path.name,
            "fps": fps,
            "width": width,
            "height": height,
            "total_frames": len(frames_output),
            "detected_frames": detected_frames,
            "landmark_names": POSE_LANDMARK_NAMES,
            "pose_connections": POSE_CONNECTIONS,
            "frames": frames_output,
        }

        artifacts = [
            ProviderArtifact(
                name="motion_keypoints.json",
                type=AssetType.motion,
                mime_type="application/json",
                format="json",
                content=json.dumps(keypoints_doc, ensure_ascii=False, indent=2),
                metadata={
                    "schema": "mediapipe_pose.v1",
                    "source_asset_id": source_asset.id,
                    "fps": fps,
                    "frames": len(frames_output),
                    "detected_frames": detected_frames,
                },
            ),
            ProviderArtifact(
                name="motion_overlay.mp4",
                type=AssetType.video,
                mime_type="video/mp4",
                format="mp4",
                content=overlay_bytes,
                metadata={
                    "source_asset_id": source_asset.id,
                    "fps": fps,
                    "width": width,
                    "height": height,
                    "frames": len(frames_output),
                },
            ),
        ]

        return ProviderResult(
            provider=self.name,
            artifacts=artifacts,
            raw_response={
                "source_asset_id": source_asset.id,
                "total_frames": len(frames_output),
                "detected_frames": detected_frames,
                "fps": fps,
            },
        )


def writer_write_frame(proc: subprocess.Popen, frame_bgr: np.ndarray) -> None:
    """把一帧 BGR 图像写入 ffmpeg stdin。
    必须保证 frame_bgr 是连续内存的 uint8 数组，且尺寸与 ffmpeg 命令里的 -s 一致。
    """
    # OpenCV 输出的 frame 已经是 uint8 BGR，直接 tobytes 就是 raw bgr24
    if not frame_bgr.flags["C_CONTIGUOUS"]:
        frame_bgr = np.ascontiguousarray(frame_bgr)
    assert proc.stdin is not None
    proc.stdin.write(frame_bgr.tobytes())


def _draw_pose_on_frame(frame_bgr: np.ndarray, landmarks: list, width: int, height: int) -> None:
    """把 33 个关键点和骨架连线画到 BGR 图像上（原地修改）。"""
    # 像素坐标
    points: list[tuple[int, int] | None] = []
    for lm in landmarks:
        # MediaPipe 输出归一化坐标，部分点 visibility 低时 x/y 可能越界，clip 一下
        x = int(np.clip(lm.x, 0.0, 1.0) * width)
        y = int(np.clip(lm.y, 0.0, 1.0) * height)
        # visibility < 0.3 的点视为不可靠，不画
        points.append((x, y) if lm.visibility >= 0.3 else None)

    # 先画连线（绿色）
    for a, b in POSE_CONNECTIONS:
        pa, pb = points[a], points[b]
        if pa and pb:
            cv2.line(frame_bgr, pa, pb, (0, 220, 0), 2, lineType=cv2.LINE_AA)
    # 再画关键点（红色）
    for p in points:
        if p:
            cv2.circle(frame_bgr, p, 3, (0, 0, 255), -1, lineType=cv2.LINE_AA)
