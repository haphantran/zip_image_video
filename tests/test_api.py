"""
Unit tests for FastAPI endpoints - API integration tests.
"""

import io
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock

from httpx import AsyncClient, ASGITransport
from PIL import Image

from app.main import app
from app.services.job_manager import job_manager, JobStatus


@pytest.fixture
def anyio_backend():
    """Required for httpx async testing."""
    return "asyncio"


@pytest.fixture
async def client(mock_settings):
    """Create async test client with mocked settings."""
    # Clear any existing jobs
    job_manager.clear_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Cleanup after test
    job_manager.clear_all()


@pytest.fixture
def sample_jpg_bytes() -> bytes:
    """Create a sample JPEG image as bytes."""
    img = Image.new("RGB", (100, 100), color=(255, 128, 64))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=95)
    buffer.seek(0)
    return buffer.read()


@pytest.fixture
def sample_png_bytes() -> bytes:
    """Create a sample PNG image as bytes."""
    img = Image.new("RGBA", (100, 100), color=(0, 128, 255, 200))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.read()


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Health endpoint should return healthy status."""
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "ffmpeg_available" in data
        assert "heic_support" in data


class TestIndexEndpoint:
    """Tests for / (index) endpoint."""

    @pytest.mark.asyncio
    async def test_index_returns_html(self, client: AsyncClient):
        """Index should return HTML page."""
        response = await client.get("/")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestUploadEndpoint:
    """Tests for /upload endpoint."""

    @pytest.mark.asyncio
    async def test_upload_valid_jpg(
        self, client: AsyncClient, sample_jpg_bytes: bytes, mock_settings
    ):
        """Upload should accept valid JPEG file."""
        files = {"file": ("test.jpg", sample_jpg_bytes, "image/jpeg")}
        data = {"preset": "facebook", "image_format": "jpg"}

        response = await client.post("/upload", files=files, data=data)

        assert response.status_code == 200
        result = response.json()
        assert "job_id" in result
        assert result["message"] == "Upload successful, processing started"

    @pytest.mark.asyncio
    async def test_upload_valid_png(
        self, client: AsyncClient, sample_png_bytes: bytes, mock_settings
    ):
        """Upload should accept valid PNG file."""
        files = {"file": ("test.png", sample_png_bytes, "image/png")}
        data = {"preset": "instagram", "image_format": "jpg"}

        response = await client.post("/upload", files=files, data=data)

        assert response.status_code == 200
        result = response.json()
        assert "job_id" in result

    @pytest.mark.asyncio
    async def test_upload_unsupported_type(self, client: AsyncClient, mock_settings):
        """Upload should reject unsupported file types."""
        files = {"file": ("document.pdf", b"fake pdf content", "application/pdf")}
        data = {"preset": "facebook", "image_format": "jpg"}

        response = await client.post("/upload", files=files, data=data)

        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_no_file(self, client: AsyncClient):
        """Upload should fail when no file is provided."""
        response = await client.post("/upload", data={"preset": "facebook"})

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_upload_default_preset(
        self, client: AsyncClient, sample_jpg_bytes: bytes, mock_settings
    ):
        """Upload should use default preset when not specified."""
        files = {"file": ("test.jpg", sample_jpg_bytes, "image/jpeg")}

        response = await client.post("/upload", files=files)

        assert response.status_code == 200


class TestJobStatusEndpoint:
    """Tests for /job/{job_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_job_status(
        self, client: AsyncClient, sample_jpg_bytes: bytes, mock_settings
    ):
        """Should return job status for valid job ID."""
        # First upload a file
        files = {"file": ("test.jpg", sample_jpg_bytes, "image/jpeg")}
        upload_response = await client.post("/upload", files=files)
        job_id = upload_response.json()["job_id"]

        # Get job status
        response = await client.get(f"/job/{job_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == job_id
        assert "status" in data
        assert "original_filename" in data

    @pytest.mark.asyncio
    async def test_get_job_status_nonexistent(self, client: AsyncClient):
        """Should return 404 for non-existent job."""
        response = await client.get("/job/nonexistent")

        assert response.status_code == 404
        assert "Job not found" in response.json()["detail"]


class TestListJobsEndpoint:
    """Tests for /jobs endpoint."""

    @pytest.mark.asyncio
    async def test_list_jobs_empty(self, client: AsyncClient):
        """Should return empty list when no jobs exist."""
        response = await client.get("/jobs")

        assert response.status_code == 200
        data = response.json()
        assert data["jobs"] == []

    @pytest.mark.asyncio
    async def test_list_jobs_with_jobs(
        self, client: AsyncClient, sample_jpg_bytes: bytes, mock_settings
    ):
        """Should return list of jobs."""
        # Upload multiple files
        for i in range(3):
            files = {"file": (f"test{i}.jpg", sample_jpg_bytes, "image/jpeg")}
            await client.post("/upload", files=files)

        response = await client.get("/jobs")

        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) == 3


class TestDeleteJobEndpoint:
    """Tests for DELETE /job/{job_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_job(
        self, client: AsyncClient, sample_jpg_bytes: bytes, mock_settings
    ):
        """Should delete existing job."""
        # Upload a file
        files = {"file": ("test.jpg", sample_jpg_bytes, "image/jpeg")}
        upload_response = await client.post("/upload", files=files)
        job_id = upload_response.json()["job_id"]

        # Delete the job
        response = await client.delete(f"/job/{job_id}")

        assert response.status_code == 200
        assert response.json()["message"] == "Job deleted"

        # Verify job is deleted
        get_response = await client.get(f"/job/{job_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_job_nonexistent(self, client: AsyncClient):
        """Should return 404 for non-existent job."""
        response = await client.delete("/job/nonexistent")

        assert response.status_code == 404


class TestClearAllJobsEndpoint:
    """Tests for DELETE /jobs endpoint."""

    @pytest.mark.asyncio
    async def test_clear_all_jobs(
        self, client: AsyncClient, sample_jpg_bytes: bytes, mock_settings
    ):
        """Should clear all jobs."""
        # Upload multiple files
        for i in range(3):
            files = {"file": (f"test{i}.jpg", sample_jpg_bytes, "image/jpeg")}
            await client.post("/upload", files=files)

        # Clear all
        response = await client.delete("/jobs")

        assert response.status_code == 200
        data = response.json()
        assert data["cleared"] == 3

        # Verify all cleared
        list_response = await client.get("/jobs")
        assert list_response.json()["jobs"] == []


class TestDownloadEndpoint:
    """Tests for /download/{job_id} endpoint."""

    @pytest.mark.asyncio
    async def test_download_pending_job(self, client: AsyncClient, mock_settings):
        """Should return 400 when job is still pending (not completed)."""
        from app.services.job_manager import job_manager, JobStatus
        from pathlib import Path
        import tempfile

        # Create a temporary test file
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            from PIL import Image

            img = Image.new("RGB", (100, 100), color=(255, 128, 64))
            img.save(tmp.name, format="JPEG")
            tmp_path = Path(tmp.name)

        # Manually create a job in PENDING state (bypassing background processing)
        job = job_manager.create_job(
            original_filename="test.jpg",
            original_path=tmp_path,
            preset="facebook",
        )

        # Try to download while job is still pending
        response = await client.get(f"/download/{job.id}")

        # Should fail because job is not completed yet
        assert response.status_code == 400
        assert "not ready" in response.json()["detail"]

        # Cleanup
        tmp_path.unlink(missing_ok=True)
        job_manager.delete_job(job.id)

    @pytest.mark.asyncio
    async def test_download_nonexistent(self, client: AsyncClient):
        """Should return 404 for non-existent job."""
        response = await client.get("/download/nonexistent")

        assert response.status_code == 404


class TestThumbnailEndpoint:
    """Tests for /thumbnail/{job_id} endpoint."""

    @pytest.mark.asyncio
    async def test_thumbnail_nonexistent(self, client: AsyncClient):
        """Should return 404 for non-existent job."""
        response = await client.get("/thumbnail/nonexistent")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_thumbnail_for_uploaded_image(
        self, client: AsyncClient, sample_jpg_bytes: bytes, mock_settings
    ):
        """Should generate thumbnail for uploaded image."""
        # Upload a file
        files = {"file": ("test.jpg", sample_jpg_bytes, "image/jpeg")}
        upload_response = await client.post("/upload", files=files)
        job_id = upload_response.json()["job_id"]

        # Get thumbnail
        response = await client.get(f"/thumbnail/{job_id}")

        assert response.status_code == 200
        assert "image/jpeg" in response.headers["content-type"]


class TestDownloadAllEndpoint:
    """Tests for /download-all endpoint."""

    @pytest.mark.asyncio
    async def test_download_all_no_completed(self, client: AsyncClient):
        """Should return 400 when no completed files."""
        response = await client.get("/download-all")

        assert response.status_code == 400
        assert "No completed files" in response.json()["detail"]
