"""
Unit tests for FFmpeg/Pillow compressor - Image/video compression logic.
"""

import pytest
from pathlib import Path
from PIL import Image

from app.services.ffmpeg_compressor import (
    is_video,
    is_image,
    is_gif,
    is_heic,
    compress_image,
    compress_video,
    compress_file,
    check_ffmpeg_available,
    check_heic_support,
    _compress_image_sync,
    PRESETS,
    VIDEO_EXTENSIONS,
    IMAGE_EXTENSIONS,
)


class TestFileTypeDetection:
    """Tests for file type detection functions."""

    def test_is_video_mp4(self):
        """MP4 should be detected as video."""
        assert is_video(Path("test.mp4")) is True

    def test_is_video_mov(self):
        """MOV should be detected as video."""
        assert is_video(Path("test.MOV")) is True

    def test_is_video_mkv(self):
        """MKV should be detected as video."""
        assert is_video(Path("video.mkv")) is True

    def test_is_video_jpg_false(self):
        """JPG should not be detected as video."""
        assert is_video(Path("test.jpg")) is False

    def test_is_video_all_extensions(self):
        """All video extensions should be detected."""
        for ext in VIDEO_EXTENSIONS:
            assert is_video(Path(f"test{ext}")) is True, f"Failed for {ext}"

    def test_is_image_jpg(self):
        """JPG should be detected as image."""
        assert is_image(Path("test.jpg")) is True

    def test_is_image_jpeg(self):
        """JPEG should be detected as image."""
        assert is_image(Path("test.JPEG")) is True

    def test_is_image_png(self):
        """PNG should be detected as image."""
        assert is_image(Path("test.png")) is True

    def test_is_image_heic(self):
        """HEIC should be detected as image."""
        assert is_image(Path("test.heic")) is True

    def test_is_image_mp4_false(self):
        """MP4 should not be detected as image."""
        assert is_image(Path("test.mp4")) is False

    def test_is_image_all_extensions(self):
        """All image extensions should be detected."""
        for ext in IMAGE_EXTENSIONS:
            assert is_image(Path(f"test{ext}")) is True, f"Failed for {ext}"

    def test_is_gif(self):
        """GIF should be detected."""
        assert is_gif(Path("test.gif")) is True
        assert is_gif(Path("test.GIF")) is True

    def test_is_gif_jpg_false(self):
        """JPG should not be detected as GIF."""
        assert is_gif(Path("test.jpg")) is False

    def test_is_heic(self):
        """HEIC/HEIF should be detected."""
        assert is_heic(Path("test.heic")) is True
        assert is_heic(Path("test.HEIC")) is True
        assert is_heic(Path("test.heif")) is True
        assert is_heic(Path("test.HEIF")) is True

    def test_is_heic_jpg_false(self):
        """JPG should not be detected as HEIC."""
        assert is_heic(Path("test.jpg")) is False


class TestPresets:
    """Tests for compression presets configuration."""

    def test_all_presets_exist(self):
        """All expected presets should be defined."""
        expected = ["facebook", "instagram", "high_quality", "balanced", "aggressive"]
        for preset in expected:
            assert preset in PRESETS, f"Missing preset: {preset}"

    def test_preset_has_video_config(self):
        """Each preset should have video configuration."""
        for name, config in PRESETS.items():
            assert "video" in config, f"{name} missing video config"
            assert "codec" in config["video"]
            assert "crf" in config["video"]
            assert "preset" in config["video"]

    def test_preset_has_image_config(self):
        """Each preset should have image configuration."""
        for name, config in PRESETS.items():
            assert "image" in config, f"{name} missing image config"
            assert "quality" in config["image"]
            assert "max_dimension" in config["image"]

    def test_facebook_preset_values(self):
        """Facebook preset should have correct values."""
        fb = PRESETS["facebook"]
        assert fb["image"]["quality"] == 80
        assert fb["image"]["max_dimension"] == 2048
        assert fb["video"]["codec"] == "libx264"

    def test_instagram_preset_values(self):
        """Instagram preset should have correct values."""
        ig = PRESETS["instagram"]
        assert ig["image"]["quality"] == 80
        assert ig["image"]["max_dimension"] == 1440

    def test_high_quality_no_resize(self):
        """High quality preset should not resize."""
        hq = PRESETS["high_quality"]
        assert hq["image"]["max_dimension"] is None
        assert hq["image"]["quality"] == 88


class TestImageCompressionSync:
    """Tests for synchronous image compression logic."""

    def test_compress_jpg_to_jpg(self, sample_jpg: Path, temp_dir: Path):
        """JPEG should compress to JPEG."""
        output = temp_dir / "output.jpg"
        _compress_image_sync(sample_jpg, output, "jpg", quality=80)

        assert output.exists()
        assert output.stat().st_size > 0

    def test_compress_png_to_jpg(self, sample_png: Path, temp_dir: Path):
        """PNG should convert and compress to JPEG."""
        output = temp_dir / "output.jpg"
        _compress_image_sync(sample_png, output, "jpg", quality=80)

        assert output.exists()
        # Verify it's actually JPEG
        with Image.open(output) as img:
            assert img.format == "JPEG"

    def test_compress_with_resize(self, sample_large_jpg: Path, temp_dir: Path):
        """Large image should be resized when max_dimension is set."""
        output = temp_dir / "output.jpg"
        _compress_image_sync(
            sample_large_jpg, output, "jpg", quality=80, max_dimension=1000
        )

        assert output.exists()
        with Image.open(output) as img:
            assert max(img.size) <= 1000

    def test_compress_no_resize_when_small(
        self, sample_small_jpg: Path, temp_dir: Path
    ):
        """Small image should not be resized when under max_dimension."""
        output = temp_dir / "output.jpg"
        original_size = Image.open(sample_small_jpg).size

        _compress_image_sync(
            sample_small_jpg, output, "jpg", quality=80, max_dimension=2000
        )

        with Image.open(output) as img:
            # Size should be same or slightly different due to EXIF rotation
            assert img.size[0] <= original_size[0] + 1
            assert img.size[1] <= original_size[1] + 1

    def test_compress_to_webp(self, sample_jpg: Path, temp_dir: Path):
        """Should support WebP output format."""
        output = temp_dir / "output.webp"
        _compress_image_sync(sample_jpg, output, "webp", quality=80)

        assert output.exists()
        with Image.open(output) as img:
            assert img.format == "WEBP"

    def test_compress_to_png(self, sample_jpg: Path, temp_dir: Path):
        """Should support PNG output format."""
        output = temp_dir / "output.png"
        _compress_image_sync(sample_jpg, output, "png", quality=80)

        assert output.exists()
        with Image.open(output) as img:
            assert img.format == "PNG"


class TestAsyncImageCompression:
    """Tests for async image compression."""

    @pytest.mark.asyncio
    async def test_compress_image_returns_path(
        self, sample_jpg: Path, mock_download_dir: Path
    ):
        """compress_image should return output path."""
        result = await compress_image(sample_jpg, preset="facebook")

        assert result is not None
        assert result.exists()
        assert result.suffix == ".jpg"

    @pytest.mark.asyncio
    async def test_compress_image_with_custom_output(
        self, sample_jpg: Path, temp_dir: Path
    ):
        """compress_image should use custom output path."""
        output = temp_dir / "custom_output.jpg"
        result = await compress_image(sample_jpg, output_path=output)

        assert result == output
        assert output.exists()

    @pytest.mark.asyncio
    async def test_compress_image_different_presets(
        self, sample_large_jpg: Path, temp_dir: Path
    ):
        """Different presets should produce different sizes."""
        outputs = {}
        for preset in ["high_quality", "balanced", "aggressive"]:
            output = temp_dir / f"{preset}.jpg"
            await compress_image(sample_large_jpg, output_path=output, preset=preset)
            outputs[preset] = output.stat().st_size

        # High quality should generally be larger than aggressive
        assert outputs["high_quality"] >= outputs["aggressive"]


class TestAsyncVideoCompression:
    """Tests for async video compression."""

    @pytest.mark.asyncio
    async def test_compress_video_requires_ffmpeg(self):
        """Video compression requires FFmpeg to be available."""
        # This test just verifies FFmpeg is installed
        assert check_ffmpeg_available() is True

    @pytest.mark.asyncio
    async def test_compress_video_nonexistent_file(self, temp_dir: Path):
        """compress_video should handle non-existent input gracefully."""
        fake_video = temp_dir / "nonexistent.mp4"
        result = await compress_video(fake_video)

        assert result is None


class TestCompressFile:
    """Tests for the unified compress_file function."""

    @pytest.mark.asyncio
    async def test_compress_file_routes_jpg(
        self, sample_jpg: Path, mock_download_dir: Path
    ):
        """compress_file should route JPG to image compression."""
        result = await compress_file(sample_jpg, preset="facebook")

        assert result is not None
        assert result.exists()

    @pytest.mark.asyncio
    async def test_compress_file_unsupported_type(self, temp_dir: Path):
        """compress_file should return None for unsupported types."""
        unsupported = temp_dir / "document.pdf"
        unsupported.write_bytes(b"fake pdf content")

        result = await compress_file(unsupported)

        assert result is None


class TestSystemChecks:
    """Tests for system capability checks."""

    def test_check_ffmpeg_available(self):
        """FFmpeg should be available on the system."""
        result = check_ffmpeg_available()
        assert isinstance(result, bool)
        # We expect FFmpeg to be installed for development
        assert result is True

    def test_check_heic_support(self):
        """HEIC support should be available via pillow-heif."""
        result = check_heic_support()
        assert isinstance(result, bool)
        # We expect pillow-heif to be installed
        assert result is True
