"""
Pytest configuration and fixtures for Media Compressor tests.
"""

import asyncio
import tempfile
import shutil
from pathlib import Path
from typing import Generator

import pytest
from PIL import Image

from app.services.job_manager import JobManager
from app.config import settings


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def job_manager() -> Generator[JobManager, None, None]:
    """Create a fresh JobManager for each test."""
    manager = JobManager()
    yield manager
    manager.clear_all()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def sample_jpg(temp_dir: Path) -> Path:
    """Create a sample JPEG image for testing."""
    img_path = temp_dir / "sample.jpg"
    img = Image.new("RGB", (1000, 800), color=(255, 128, 64))
    img.save(img_path, format="JPEG", quality=95)
    return img_path


@pytest.fixture
def sample_png(temp_dir: Path) -> Path:
    """Create a sample PNG image with transparency for testing."""
    img_path = temp_dir / "sample.png"
    img = Image.new("RGBA", (800, 600), color=(0, 128, 255, 200))
    img.save(img_path, format="PNG")
    return img_path


@pytest.fixture
def sample_large_jpg(temp_dir: Path) -> Path:
    """Create a large JPEG image (>2048px) for resize testing."""
    img_path = temp_dir / "large.jpg"
    img = Image.new("RGB", (4000, 3000), color=(100, 150, 200))
    img.save(img_path, format="JPEG", quality=95)
    return img_path


@pytest.fixture
def sample_small_jpg(temp_dir: Path) -> Path:
    """Create a small JPEG image (<1000px) for no-resize testing."""
    img_path = temp_dir / "small.jpg"
    img = Image.new("RGB", (500, 400), color=(200, 100, 50))
    img.save(img_path, format="JPEG", quality=95)
    return img_path


@pytest.fixture
def mock_upload_dir(temp_dir: Path, monkeypatch) -> Path:
    """Override upload directory for testing."""
    upload_dir = temp_dir / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(settings, "upload_dir", upload_dir)
    return upload_dir


@pytest.fixture
def mock_download_dir(temp_dir: Path, monkeypatch) -> Path:
    """Override download directory for testing."""
    download_dir = temp_dir / "downloads"
    download_dir.mkdir()
    monkeypatch.setattr(settings, "download_dir", download_dir)
    return download_dir


@pytest.fixture
def mock_settings(mock_upload_dir: Path, mock_download_dir: Path):
    """Combined fixture for mocked settings."""
    return {
        "upload_dir": mock_upload_dir,
        "download_dir": mock_download_dir,
    }
