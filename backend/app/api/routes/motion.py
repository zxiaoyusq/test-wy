from fastapi import APIRouter

from app.core.enums import ModuleType
from app.models.job import JobListResponse, JobRecord
from app.models.motion import MotionJobCreate
from app.providers.motion import (
    MediaPipeMotionProvider,
    MockMotionProvider,
    QianmianMotionProvider,
)
from app.services.job_service import job_service
from app.services.storage_service import storage_service

router = APIRouter(prefix="/motion", tags=["motion"])


@router.post("/jobs", response_model=JobRecord)
def create_motion_job(request: MotionJobCreate) -> JobRecord:
    # 默认走本地 MediaPipe；如需千面云服务传 provider="qianmian_motion"，调试用 provider="mock_motion"
    provider = _select_provider(request)
    job = job_service.create(ModuleType.motion, provider.name, request.model_dump())
    job_service.mark_running(job)
    try:
        result = provider.run(request)
        outputs = storage_service.save_artifacts(ModuleType.motion, job.id, result.artifacts)
        return job_service.mark_succeeded(job, outputs)
    except Exception as exc:
        return job_service.mark_failed(job, exc)


@router.get("/jobs", response_model=JobListResponse)
def list_motion_jobs() -> JobListResponse:
    return JobListResponse(jobs=job_service.list(ModuleType.motion))


@router.get("/jobs/{job_id}", response_model=JobRecord)
def get_motion_job(job_id: str) -> JobRecord:
    return job_service.get(job_id)


def _select_provider(
    request: MotionJobCreate,
) -> MockMotionProvider | QianmianMotionProvider | MediaPipeMotionProvider:
    # 显式 provider 优先：mock_motion / qianmian_motion 走原通道
    if request.provider == "mock_motion":
        return MockMotionProvider()
    if request.provider == "qianmian_motion":
        return QianmianMotionProvider()
    # 其它一律走本地 MediaPipe（包含默认值 mediapipe_motion 与未识别的 provider）
    return MediaPipeMotionProvider()
