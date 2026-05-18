from datetime import datetime, timezone
from uuid import uuid4

from app.core.config import get_settings
from app.core.enums import ModuleType
from app.models.asset import AssetRecord
from app.providers.base import ProviderArtifact
from app.services.asset_service import asset_service


class StorageService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def save_artifacts(
        self,
        module: ModuleType,
        job_id: str,
        artifacts: list[ProviderArtifact],
    ) -> list[AssetRecord]:
        output_dir = self.settings.assets_dir / module.value / job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        records: list[AssetRecord] = []
        for artifact in artifacts:
            file_path = output_dir / artifact.name
            if isinstance(artifact.content, bytes):
                file_path.write_bytes(artifact.content)
            else:
                file_path.write_text(artifact.content, encoding="utf-8")

            asset = AssetRecord(
                id=f"asset_{uuid4().hex}",
                type=artifact.type,
                module=module,
                job_id=job_id,
                name=artifact.name,
                path=str(file_path.relative_to(self.settings.data_dir.parent)).replace("\\", "/"),
                mime_type=artifact.mime_type,
                format=artifact.format,
                metadata=artifact.metadata,
                created_at=datetime.now(timezone.utc),
            )
            asset_service.save(asset)
            records.append(asset)

        return records


storage_service = StorageService()
