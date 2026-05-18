from fastapi import APIRouter

from app.core.enums import ModuleType
from app.models.job import JobListResponse, JobRecord
from app.models.motion import MotionJobCreate
from app.providers.motion import MockMotionProvider
from app.services.job_service import job_service
from app.services.storage_service import storage_service

router = APIRouter(prefix="/motion", tags=["motion"])


@router.post("/jobs", response_model=JobRecord)
def create_motion_job(request: MotionJobCreate) -> JobRecord:
    provider = MockMotionProvider()
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

