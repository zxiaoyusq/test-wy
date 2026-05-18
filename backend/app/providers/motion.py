import json

from app.core.enums import AssetType
from app.models.motion import MotionJobCreate
from app.providers.base import ProviderArtifact, ProviderResult


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

