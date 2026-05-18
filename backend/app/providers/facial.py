import csv
import io
import json

from app.core.enums import AssetType
from app.models.facial import FacialJobCreate
from app.providers.base import ProviderArtifact, ProviderResult


class MockFacialProvider:
    name = "mock_facial"

    def run(self, request: FacialJobCreate) -> ProviderResult:
        curves = {
            "fps": request.params.get("fps", 30),
            "standard": request.output_standard,
            "frames": [
                {
                    "t": 0.0,
                    "head": {"yaw": 0.02, "pitch": -0.03, "roll": 0.01},
                    "blendshapes": {
                        "jawOpen": 0.35,
                        "mouthSmileLeft": 0.12,
                        "mouthSmileRight": 0.10,
                        "eyeBlinkLeft": 0.02,
                        "eyeBlinkRight": 0.03,
                        "browInnerUp": 0.18,
                    },
                },
                {
                    "t": 0.033,
                    "head": {"yaw": 0.03, "pitch": -0.02, "roll": 0.01},
                    "blendshapes": {
                        "jawOpen": 0.38,
                        "mouthSmileLeft": 0.13,
                        "mouthSmileRight": 0.11,
                        "eyeBlinkLeft": 0.03,
                        "eyeBlinkRight": 0.03,
                        "browInnerUp": 0.16,
                    },
                },
            ],
        }
        return ProviderResult(
            provider=self.name,
            artifacts=[
                ProviderArtifact(
                    name="face_curves.json",
                    type=AssetType.facial,
                    mime_type="application/json",
                    format="json",
                    content=json.dumps(curves, ensure_ascii=False, indent=2),
                    metadata={"schema": "face_curves.v1"},
                ),
                ProviderArtifact(
                    name="face_curves.csv",
                    type=AssetType.facial,
                    mime_type="text/csv",
                    format="csv",
                    content=_curves_to_csv(curves),
                    metadata={"standard": request.output_standard},
                ),
            ],
            raw_response={"mock": True, "source_asset_id": request.input_asset_id},
        )


def _curves_to_csv(curves: dict) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["t", "head_yaw", "head_pitch", "head_roll", "jawOpen", "eyeBlinkLeft", "eyeBlinkRight"])
    for frame in curves["frames"]:
        writer.writerow(
            [
                frame["t"],
                frame["head"]["yaw"],
                frame["head"]["pitch"],
                frame["head"]["roll"],
                frame["blendshapes"]["jawOpen"],
                frame["blendshapes"]["eyeBlinkLeft"],
                frame["blendshapes"]["eyeBlinkRight"],
            ]
        )
    return buffer.getvalue()

