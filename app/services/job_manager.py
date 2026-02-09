import uuid
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class JobStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class CompressionJob:
    id: str
    original_filename: str
    original_path: Path
    preset: str = "facebook"
    image_format: str = "jpg"
    status: JobStatus = JobStatus.PENDING
    progress: int = 0
    compressed_path: Optional[Path] = None
    original_size: int = 0
    compressed_size: int = 0
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "original_filename": self.original_filename,
            "preset": self.preset,
            "image_format": self.image_format,
            "status": self.status.value,
            "progress": self.progress,
            "original_size": self.original_size,
            "compressed_size": self.compressed_size,
            "compression_ratio": self._compression_ratio(),
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "download_ready": self.status == JobStatus.COMPLETED
            and self.compressed_path is not None,
            "output_filename": self.compressed_path.name
            if self.compressed_path
            else None,
        }

    def _compression_ratio(self) -> Optional[float]:
        if self.original_size > 0 and self.compressed_size > 0:
            return round((1 - self.compressed_size / self.original_size) * 100, 1)
        return None


class JobManager:
    def __init__(self):
        self.jobs: Dict[str, CompressionJob] = {}

    def create_job(
        self,
        original_filename: str,
        original_path: Path,
        preset: str = "facebook",
        image_format: str = "jpg",
    ) -> CompressionJob:
        job_id = str(uuid.uuid4())[:8]

        job = CompressionJob(
            id=job_id,
            original_filename=original_filename,
            original_path=original_path,
            preset=preset,
            image_format=image_format,
            original_size=original_path.stat().st_size,
        )

        self.jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[CompressionJob]:
        return self.jobs.get(job_id)

    def delete_job(self, job_id: str) -> bool:
        if job_id in self.jobs:
            del self.jobs[job_id]
            return True
        return False

    def update_job(
        self,
        job_id: str,
        status: Optional[JobStatus] = None,
        progress: Optional[int] = None,
        compressed_path: Optional[Path] = None,
        error_message: Optional[str] = None,
    ):
        job = self.jobs.get(job_id)
        if job:
            if status:
                job.status = status
                if status == JobStatus.COMPLETED:
                    job.completed_at = datetime.now()
            if progress is not None:
                job.progress = progress
            if compressed_path:
                job.compressed_path = compressed_path
                job.compressed_size = compressed_path.stat().st_size
            if error_message:
                job.error_message = error_message

    def list_jobs(self) -> list:
        return [
            job.to_dict()
            for job in sorted(
                self.jobs.values(), key=lambda x: x.created_at, reverse=True
            )
        ]

    def cleanup_old_jobs(self, max_age_hours: int = 24):
        now = datetime.now()
        jobs_to_remove = []

        for job_id, job in self.jobs.items():
            age = (now - job.created_at).total_seconds() / 3600
            if age > max_age_hours:
                if job.original_path.exists():
                    job.original_path.unlink()
                if job.compressed_path and job.compressed_path.exists():
                    job.compressed_path.unlink()
                jobs_to_remove.append(job_id)

        for job_id in jobs_to_remove:
            del self.jobs[job_id]

    def clear_all(self):
        self.jobs.clear()


job_manager = JobManager()
