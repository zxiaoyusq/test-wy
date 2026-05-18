from fastapi import APIRouter

from app.core.enums import ModuleType
from app.models.character import CharacterJobCreate
from app.models.job import JobListResponse, JobRecord
from app.providers.character import MockCharacterProvider, QwenImageProvider
from app.services.job_service import job_service
from app.services.storage_service import storage_service

router = APIRouter(prefix="/character", tags=["character"])


@router.post("/jobs", response_model=JobRecord)
def create_character_job(request: CharacterJobCreate) -> JobRecord:
    provider = _select_provider(request)
    job = job_service.create(ModuleType.character, provider.name, request.model_dump())
    job_service.mark_running(job)
    try:
        result = provider.run(request)
        outputs = storage_service.save_artifacts(ModuleType.character, job.id, result.artifacts)
        return job_service.mark_succeeded(job, outputs)
    except Exception as exc:
        return job_service.mark_failed(job, exc)


@router.get("/jobs", response_model=JobListResponse)
def list_character_jobs() -> JobListResponse:
    return JobListResponse(jobs=job_service.list(ModuleType.character))


@router.get("/jobs/{job_id}", response_model=JobRecord)
def get_character_job(job_id: str) -> JobRecord:
    return job_service.get(job_id)


def _select_provider(request: CharacterJobCreate) -> MockCharacterProvider | QwenImageProvider:
    if request.image_provider == "mock":
        return MockCharacterProvider()
    return QwenImageProvider()
