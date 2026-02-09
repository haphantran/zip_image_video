"""
Unit tests for JobManager - Job CRUD operations and state transitions.
"""

import pytest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app.services.job_manager import JobManager, CompressionJob, JobStatus


class TestJobCreation:
    """Tests for job creation."""

    def test_create_job_returns_compression_job(
        self, job_manager: JobManager, sample_jpg: Path
    ):
        """Create job should return a CompressionJob instance."""
        job = job_manager.create_job(
            original_filename="test.jpg",
            original_path=sample_jpg,
            preset="facebook",
            image_format="jpg",
        )

        assert isinstance(job, CompressionJob)
        assert job.original_filename == "test.jpg"
        assert job.original_path == sample_jpg
        assert job.preset == "facebook"
        assert job.image_format == "jpg"

    def test_create_job_generates_unique_id(
        self, job_manager: JobManager, sample_jpg: Path
    ):
        """Each job should have a unique 8-character ID."""
        job1 = job_manager.create_job("test1.jpg", sample_jpg)
        job2 = job_manager.create_job("test2.jpg", sample_jpg)

        assert job1.id != job2.id
        assert len(job1.id) == 8
        assert len(job2.id) == 8

    def test_create_job_sets_pending_status(
        self, job_manager: JobManager, sample_jpg: Path
    ):
        """New jobs should start with PENDING status."""
        job = job_manager.create_job("test.jpg", sample_jpg)
        assert job.status == JobStatus.PENDING

    def test_create_job_records_original_size(
        self, job_manager: JobManager, sample_jpg: Path
    ):
        """Job should record the original file size."""
        job = job_manager.create_job("test.jpg", sample_jpg)
        assert job.original_size == sample_jpg.stat().st_size
        assert job.original_size > 0

    def test_create_job_sets_created_at(
        self, job_manager: JobManager, sample_jpg: Path
    ):
        """Job should have a creation timestamp."""
        before = datetime.now()
        job = job_manager.create_job("test.jpg", sample_jpg)
        after = datetime.now()

        assert before <= job.created_at <= after

    def test_create_job_default_preset(self, job_manager: JobManager, sample_jpg: Path):
        """Default preset should be 'facebook'."""
        job = job_manager.create_job("test.jpg", sample_jpg)
        assert job.preset == "facebook"

    def test_create_job_default_format(self, job_manager: JobManager, sample_jpg: Path):
        """Default image format should be 'jpg'."""
        job = job_manager.create_job("test.jpg", sample_jpg)
        assert job.image_format == "jpg"


class TestJobRetrieval:
    """Tests for job retrieval operations."""

    def test_get_job_existing(self, job_manager: JobManager, sample_jpg: Path):
        """Get job should return existing job."""
        created_job = job_manager.create_job("test.jpg", sample_jpg)
        retrieved_job = job_manager.get_job(created_job.id)

        assert retrieved_job is not None
        assert retrieved_job.id == created_job.id

    def test_get_job_nonexistent(self, job_manager: JobManager):
        """Get job should return None for non-existent ID."""
        result = job_manager.get_job("nonexistent")
        assert result is None

    def test_list_jobs_empty(self, job_manager: JobManager):
        """List jobs should return empty list when no jobs exist."""
        result = job_manager.list_jobs()
        assert result == []

    def test_list_jobs_returns_dicts(self, job_manager: JobManager, sample_jpg: Path):
        """List jobs should return list of dictionaries."""
        job_manager.create_job("test.jpg", sample_jpg)
        result = job_manager.list_jobs()

        assert len(result) == 1
        assert isinstance(result[0], dict)

    def test_list_jobs_sorted_by_created_at(
        self, job_manager: JobManager, sample_jpg: Path
    ):
        """List jobs should be sorted by created_at descending (newest first)."""
        job1 = job_manager.create_job("first.jpg", sample_jpg)
        job2 = job_manager.create_job("second.jpg", sample_jpg)
        job3 = job_manager.create_job("third.jpg", sample_jpg)

        result = job_manager.list_jobs()

        # Newest first
        assert result[0]["id"] == job3.id
        assert result[1]["id"] == job2.id
        assert result[2]["id"] == job1.id


class TestJobUpdate:
    """Tests for job update operations."""

    def test_update_job_status(self, job_manager: JobManager, sample_jpg: Path):
        """Update job should change status."""
        job = job_manager.create_job("test.jpg", sample_jpg)
        job_manager.update_job(job.id, status=JobStatus.PROCESSING)

        updated = job_manager.get_job(job.id)
        assert updated.status == JobStatus.PROCESSING

    def test_update_job_progress(self, job_manager: JobManager, sample_jpg: Path):
        """Update job should change progress."""
        job = job_manager.create_job("test.jpg", sample_jpg)
        job_manager.update_job(job.id, progress=50)

        updated = job_manager.get_job(job.id)
        assert updated.progress == 50

    def test_update_job_completed_sets_timestamp(
        self, job_manager: JobManager, sample_jpg: Path
    ):
        """Setting COMPLETED status should set completed_at."""
        job = job_manager.create_job("test.jpg", sample_jpg)
        assert job.completed_at is None

        job_manager.update_job(job.id, status=JobStatus.COMPLETED)

        updated = job_manager.get_job(job.id)
        assert updated.completed_at is not None
        assert isinstance(updated.completed_at, datetime)

    def test_update_job_compressed_path_and_size(
        self, job_manager: JobManager, sample_jpg: Path, sample_png: Path
    ):
        """Update compressed_path should also update compressed_size."""
        job = job_manager.create_job("test.jpg", sample_jpg)
        job_manager.update_job(job.id, compressed_path=sample_png)

        updated = job_manager.get_job(job.id)
        assert updated.compressed_path == sample_png
        assert updated.compressed_size == sample_png.stat().st_size

    def test_update_job_error_message(self, job_manager: JobManager, sample_jpg: Path):
        """Update job should set error message."""
        job = job_manager.create_job("test.jpg", sample_jpg)
        job_manager.update_job(job.id, error_message="Compression failed")

        updated = job_manager.get_job(job.id)
        assert updated.error_message == "Compression failed"

    def test_update_nonexistent_job(self, job_manager: JobManager):
        """Update on non-existent job should not raise error."""
        # Should not raise
        job_manager.update_job("nonexistent", status=JobStatus.PROCESSING)


class TestJobDeletion:
    """Tests for job deletion operations."""

    def test_delete_job_existing(self, job_manager: JobManager, sample_jpg: Path):
        """Delete job should remove existing job and return True."""
        job = job_manager.create_job("test.jpg", sample_jpg)
        result = job_manager.delete_job(job.id)

        assert result is True
        assert job_manager.get_job(job.id) is None

    def test_delete_job_nonexistent(self, job_manager: JobManager):
        """Delete job should return False for non-existent ID."""
        result = job_manager.delete_job("nonexistent")
        assert result is False

    def test_clear_all(self, job_manager: JobManager, sample_jpg: Path):
        """Clear all should remove all jobs."""
        job_manager.create_job("test1.jpg", sample_jpg)
        job_manager.create_job("test2.jpg", sample_jpg)
        job_manager.create_job("test3.jpg", sample_jpg)

        job_manager.clear_all()

        assert job_manager.list_jobs() == []


class TestJobToDict:
    """Tests for CompressionJob.to_dict() serialization."""

    def test_to_dict_contains_required_fields(
        self, job_manager: JobManager, sample_jpg: Path
    ):
        """to_dict should include all required fields."""
        job = job_manager.create_job("test.jpg", sample_jpg)
        result = job.to_dict()

        required_fields = [
            "id",
            "original_filename",
            "preset",
            "image_format",
            "status",
            "progress",
            "original_size",
            "compressed_size",
            "compression_ratio",
            "error_message",
            "created_at",
            "completed_at",
            "download_ready",
            "output_filename",
        ]

        for field in required_fields:
            assert field in result, f"Missing field: {field}"

    def test_to_dict_status_is_string(self, job_manager: JobManager, sample_jpg: Path):
        """Status in to_dict should be string, not enum."""
        job = job_manager.create_job("test.jpg", sample_jpg)
        result = job.to_dict()

        assert isinstance(result["status"], str)
        assert result["status"] == "pending"

    def test_to_dict_download_ready_completed(
        self, job_manager: JobManager, sample_jpg: Path, sample_png: Path
    ):
        """download_ready should be True only when COMPLETED with compressed_path."""
        job = job_manager.create_job("test.jpg", sample_jpg)
        job_manager.update_job(
            job.id, status=JobStatus.COMPLETED, compressed_path=sample_png
        )

        updated = job_manager.get_job(job.id)
        result = updated.to_dict()

        assert result["download_ready"] is True
        assert result["output_filename"] == sample_png.name

    def test_to_dict_download_ready_pending(
        self, job_manager: JobManager, sample_jpg: Path
    ):
        """download_ready should be False for pending jobs."""
        job = job_manager.create_job("test.jpg", sample_jpg)
        result = job.to_dict()

        assert result["download_ready"] is False


class TestCompressionRatio:
    """Tests for compression ratio calculation."""

    def test_compression_ratio_calculated(
        self, job_manager: JobManager, sample_jpg: Path, sample_small_jpg: Path
    ):
        """Compression ratio should be calculated when both sizes available."""
        job = job_manager.create_job("test.jpg", sample_jpg)
        job_manager.update_job(job.id, compressed_path=sample_small_jpg)

        updated = job_manager.get_job(job.id)
        result = updated.to_dict()

        assert result["compression_ratio"] is not None
        assert isinstance(result["compression_ratio"], float)

    def test_compression_ratio_none_when_no_compressed_size(
        self, job_manager: JobManager, sample_jpg: Path
    ):
        """Compression ratio should be None when no compressed size."""
        job = job_manager.create_job("test.jpg", sample_jpg)
        result = job.to_dict()

        assert result["compression_ratio"] is None


class TestCleanupOldJobs:
    """Tests for job cleanup functionality."""

    def test_cleanup_old_jobs_removes_expired(
        self, job_manager: JobManager, temp_dir: Path
    ):
        """Cleanup should remove jobs older than max_age_hours."""
        # Create a file in temp dir
        test_file = temp_dir / "old.jpg"
        test_file.write_bytes(b"test data")

        job = job_manager.create_job("old.jpg", test_file)

        # Manually set created_at to 25 hours ago
        job.created_at = datetime.now() - timedelta(hours=25)

        job_manager.cleanup_old_jobs(max_age_hours=24)

        assert job_manager.get_job(job.id) is None

    def test_cleanup_old_jobs_keeps_recent(
        self, job_manager: JobManager, sample_jpg: Path
    ):
        """Cleanup should keep jobs newer than max_age_hours."""
        job = job_manager.create_job("recent.jpg", sample_jpg)

        job_manager.cleanup_old_jobs(max_age_hours=24)

        assert job_manager.get_job(job.id) is not None
