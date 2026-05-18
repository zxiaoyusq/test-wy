from fastapi import APIRouter

from app.core.enums import ModuleType
from app.models.facial import FacialJobCreate
from app.models.job import JobListResponse, JobRecord
from app.providers.facial import MockFacialProvider
from app.services.job_service import job_service
from app.services.storage_service import storage_service

router = APIRouter(prefix="/facial", tags=["facial"])


@router.post("/jobs", response_model=JobRecord)
def create_facial_job(request: FacialJobCreate) -> JobRecord:
    provider = MockFacialProvider()
    job = job_service.create(ModuleType.facial, provider.name, request.model_dump())
    job_service.mark_running(job)
    try:
        result = provider.run(request)
        outputs = storage_service.save_artifacts(ModuleType.facial, job.id, result.artifacts)
        return job_service.mark_succeeded(job, outputs)
    except Exception as exc:
        return job_service.mark_failed(job, exc)


@router.get("/jobs", response_model=JobListResponse)
def list_facial_jobs() -> JobListResponse:
    return JobListResponse(jobs=job_service.list(ModuleType.facial))


@router.get("/jobs/{job_id}", response_model=JobRecord)
def get_facial_job(job_id: str) -> JobRecord:
    return job_service.get(job_id)

