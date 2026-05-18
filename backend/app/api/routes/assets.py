from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.models.asset import AssetRecord, AssetSummary
from app.services.asset_service import asset_service

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=list[AssetSummary])
def list_assets() -> list[AssetSummary]:
    return [asset_service.to_summary(asset) for asset in asset_service.list()]


@router.get("/{asset_id}", response_model=AssetRecord)
def get_asset(asset_id: str) -> AssetRecord:
    return asset_service.get(asset_id)


@router.get("/{asset_id}/file")
def get_asset_file(asset_id: str) -> FileResponse:
    asset = asset_service.get(asset_id)
    path = asset_service.resolve_path(asset)
    return FileResponse(path=path, media_type=asset.mime_type, filename=asset.name)

