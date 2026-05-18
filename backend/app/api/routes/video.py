from fastapi import APIRouter

from app.core.enums import ModuleType
from app.models.job import JobListResponse, JobRecord
from app.models.video import VideoJobCreate
from app.providers.video import MockVideoProvider, WanImageToVideoProvider
from app.services.job_service import job_service
from app.services.storage_service import storage_service

router = APIRouter(prefix="/video", tags=["video"])


@router.post("/jobs", response_model=JobRecord)
def create_video_job(request: VideoJobCreate) -> JobRecord:
    provider = _select_provider(request)
    job = job_service.create(ModuleType.video, provider.name, request.model_dump())
    job_service.mark_running(job)
    try:
        result = provider.run(request)
        outputs = storage_service.save_artifacts(ModuleType.video, job.id, result.artifacts)
        return job_service.mark_succeeded(job, outputs)
    except Exception as exc:
        return job_service.mark_failed(job, exc)


@router.get("/jobs", response_model=JobListResponse)
def list_video_jobs() -> JobListResponse:
    return JobListResponse(jobs=job_service.list(ModuleType.video))


@router.get("/jobs/{job_id}", response_model=JobRecord)
def get_video_job(job_id: str) -> JobRecord:
    return job_service.get(job_id)


def _select_provider(request: VideoJobCreate) -> MockVideoProvider | WanImageToVideoProvider:
    if request.provider == "mock":
        return MockVideoProvider()
    return WanImageToVideoProvider()
