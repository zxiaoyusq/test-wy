from typing import Any

from pydantic import BaseModel, Field


class MotionJobCreate(BaseModel):
    # 上游视频 asset id：动作捕捉必须输入一个 MP4 视频
    input_video_asset_id: str
    # provider 决定走 mediapipe / 千面 / mock，默认走本地 MediaPipe（不依赖外部服务）
    provider: str = "mediapipe_motion"
    # 输出骨架类型，沿用上一版字段名以保持向后兼容；新逻辑使用 bonetype
    target_skeleton: str = "humanoid"
    output_formats: list[str] = Field(default_factory=lambda: ["json", "bvh"])

    # === 千面动捕业务参数（参考 https://www.qmai.vip/docs/document/video-upload.html） ===
    # 骨架格式编号：15 = BVH（默认，便于本地直接预览/调试）
    bonetype: int = 15
    # 动捕类型，逗号分隔字符串：0 全身 / 1 半身 / 2 手捕 / 3 面捕 / 5 自动；默认仅全身
    capturetype: str = "0"
    # 输出帧率，24/30 = 1 CV币/秒，60 = 2 CV币/秒，120 = 4 CV币/秒
    frame_rate: int = 30
    # 第一帧姿势：1 TPose / 2 APose / 3 原 Pose
    pose_type: int = 3
    # 是否原地动作，关闭表示保留位移
    stand_pose: bool = False
    # 视频逻辑名（不含 emoji）；不传时由 provider 用 asset 文件名兜底
    video_name: str | None = None

    # 通用扩展参数：例如 poll_interval_seconds / max_wait_seconds / video_sign 等放这里
    params: dict[str, Any] = Field(default_factory=dict)
