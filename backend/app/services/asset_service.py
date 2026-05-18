from pathlib import Path

from fastapi import HTTPException

from app.core.config import get_settings
from app.models.asset import AssetRecord, AssetSummary


class AssetService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def save(self, asset: AssetRecord) -> None:
        path = self.settings.asset_index_dir / f"{asset.id}.json"
        path.write_text(asset.model_dump_json(indent=2), encoding="utf-8")

    def get(self, asset_id: str) -> AssetRecord:
        path = self.settings.asset_index_dir / f"{asset_id}.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")
        return AssetRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self) -> list[AssetRecord]:
        assets: list[AssetRecord] = []
        for path in sorted(self.settings.asset_index_dir.glob("*.json")):
            assets.append(AssetRecord.model_validate_json(path.read_text(encoding="utf-8")))
        return sorted(assets, key=lambda asset: asset.created_at, reverse=True)

    def resolve_path(self, asset: AssetRecord) -> Path:
        asset_path = (self.settings.data_dir.parent / asset.path).resolve()
        if not asset_path.exists():
            raise HTTPException(status_code=404, detail=f"Asset file missing: {asset.id}")
        return asset_path

    def to_summary(self, asset: AssetRecord) -> AssetSummary:
        return AssetSummary(
            id=asset.id,
            type=asset.type,
            module=asset.module,
            job_id=asset.job_id,
            name=asset.name,
            url=f"/api/assets/{asset.id}/file",
            format=asset.format,
            metadata=asset.metadata,
        )


asset_service = AssetService()

