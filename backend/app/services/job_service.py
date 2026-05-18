from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from app.core.config import get_settings
from app.core.enums import JobStatus, ModuleType
from app.models.asset import AssetRecord
from app.models.job import JobRecord


class JobService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def create(self, module: ModuleType, provider: str, payload: dict) -> JobRecord:
        now = datetime.now(timezone.utc)
        job = JobRecord(
            id=f"job_{uuid4().hex}",
            module=module,
            status=JobStatus.pending,
            provider=provider,
            input=payload,
            outputs=[],
            error=None,
            created_at=now,
            updated_at=now,
        )
        self.save(job)
        return job

    def mark_running(self, job: JobRecord) -> JobRecord:
        job.status = JobStatus.running
        job.updated_at = datetime.now(timezone.utc)
        self.save(job)
        return job

    def mark_succeeded(self, job: JobRecord, outputs: list[AssetRecord]) -> JobRecord:
        job.status = JobStatus.succeeded
        job.outputs = outputs
        job.updated_at = datetime.now(timezone.utc)
        self.save(job)
        return job

    def mark_failed(self, job: JobRecord, error: Exception | str) -> JobRecord:
        job.status = JobStatus.failed
        job.error = str(error)
        job.updated_at = datetime.now(timezone.utc)
        self.save(job)
        return job

    def save(self, job: JobRecord) -> None:
        path = self.settings.jobs_dir / f"{job.id}.json"
        path.write_text(job.model_dump_json(indent=2), encoding="utf-8")

    def get(self, job_id: str) -> JobRecord:
        path = self.settings.jobs_dir / f"{job_id}.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        return JobRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self, module: ModuleType | None = None) -> list[JobRecord]:
        jobs: list[JobRecord] = []
        for path in sorted(self.settings.jobs_dir.glob("*.json")):
            job = JobRecord.model_validate_json(path.read_text(encoding="utf-8"))
            if module is None or job.module == module:
                jobs.append(job)
        return sorted(jobs, key=lambda item: item.created_at, reverse=True)


job_service = JobService()

