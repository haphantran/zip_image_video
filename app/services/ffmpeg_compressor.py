import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Literal
from loguru import logger
from PIL import Image
import pillow_heif

from app.config import settings

# Register HEIF/HEIC opener with Pillow
pillow_heif.register_heif_opener()

CompressionPreset = Literal[
    "facebook", "instagram", "high_quality", "balanced", "aggressive"
]
ImageOutputFormat = Literal["jpg", "png", "webp"]


PRESETS = {
    "facebook": {
        "video": {
            "codec": "libx264",
            "crf": "23",
            "preset": "medium",
            "extra": [
                "-maxrate",
                "1638k",
                "-bufsize",
                "3276k",
                "-movflags",
                "+faststart",
            ],
        },
        "image": {"quality": 80, "max_dimension": 2048},
    },
    "instagram": {
        "video": {
            "codec": "libx264",
            "crf": "23",
            "preset": "medium",
            "extra": [
                "-maxrate",
                "3500k",
                "-bufsize",
                "7000k",
                "-movflags",
                "+faststart",
            ],
        },
        "image": {"quality": 80, "max_dimension": 1440},
    },
    "high_quality": {
        "video": {
            "codec": "libx265",
            "crf": "22",
            "preset": "slow",
            "extra": ["-tag:v", "hvc1", "-movflags", "+faststart"],
        },
        "image": {"quality": 88, "max_dimension": None},
    },
    "balanced": {
        "video": {
            "codec": "libx265",
            "crf": "26",
            "preset": "medium",
            "extra": ["-tag:v", "hvc1", "-movflags", "+faststart"],
        },
        "image": {"quality": 75, "max_dimension": 2400},
    },
    "aggressive": {
        "video": {
            "codec": "libx265",
            "crf": "30",
            "preset": "fast",
            "extra": ["-tag:v", "hvc1", "-movflags", "+faststart"],
        },
        "image": {"quality": 65, "max_dimension": 1920},
    },
}

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
    ".m4v",
    ".wmv",
    ".flv",
    ".mts",
    ".m2ts",
}
# Static images - processed with Pillow
IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tiff",
    ".heic",
    ".heif",
}
# Animated GIFs - processed with FFmpeg
GIF_EXTENSION = {".gif"}


def is_video(file_path: Path) -> bool:
    return file_path.suffix.lower() in VIDEO_EXTENSIONS


def is_gif(file_path: Path) -> bool:
    return file_path.suffix.lower() in GIF_EXTENSION


def is_image(file_path: Path) -> bool:
    return file_path.suffix.lower() in IMAGE_EXTENSIONS


def is_heic(file_path: Path) -> bool:
    return file_path.suffix.lower() in {".heic", ".heif"}


async def compress_video(
    input_path: Path,
    output_path: Optional[Path] = None,
    preset: CompressionPreset = "facebook",
) -> Optional[Path]:
    if output_path is None:
        output_path = settings.download_dir / f"compressed_{input_path.stem}.mp4"

    preset_config = PRESETS[preset]["video"]

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-c:v",
        preset_config["codec"],
        "-crf",
        preset_config["crf"],
        "-preset",
        preset_config["preset"],
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        *preset_config["extra"],
        str(output_path),
    ]

    logger.info(f"Compressing video: {input_path.name}")

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            logger.info(f"Video compressed: {output_path.name}")
            return output_path
        else:
            logger.error(f"FFmpeg error: {stderr.decode()}")
            return None

    except Exception as e:
        logger.error(f"Video compression failed: {e}")
        return None


async def compress_image(
    input_path: Path,
    output_path: Optional[Path] = None,
    preset: CompressionPreset = "facebook",
    output_format: ImageOutputFormat = "jpg",
) -> Optional[Path]:
    if output_path is None:
        output_path = (
            settings.download_dir / f"compressed_{input_path.stem}.{output_format}"
        )

    preset_config = PRESETS[preset]["image"]
    quality = preset_config["quality"]
    max_dimension = preset_config.get("max_dimension")

    logger.info(
        f"Compressing image: {input_path.name} -> {output_format.upper()} (Q{quality}, max {max_dimension or 'full'}px)"
    )

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            _compress_image_sync,
            input_path,
            output_path,
            output_format,
            quality,
            max_dimension,
        )

        if output_path.exists():
            logger.info(f"Image compressed: {output_path.name}")
            return output_path
        else:
            logger.error("Pillow compression produced no output")
            return None

    except Exception as e:
        logger.error(f"Image compression failed: {e}")
        return None


def _compress_image_sync(
    input_path: Path,
    output_path: Path,
    output_format: str,
    quality: int,
    max_dimension: Optional[int] = None,
) -> None:
    with Image.open(input_path) as img:
        # Convert to RGB if necessary (HEIC, PNG with alpha, etc.)
        if img.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(
                img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None
            )
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Preserve EXIF orientation
        try:
            from PIL import ExifTags

            exif = img._getexif()
            if exif:
                for tag, value in exif.items():
                    if ExifTags.TAGS.get(tag) == "Orientation":
                        if value == 3:
                            img = img.rotate(180, expand=True)
                        elif value == 6:
                            img = img.rotate(270, expand=True)
                        elif value == 8:
                            img = img.rotate(90, expand=True)
                        break
        except (AttributeError, KeyError, IndexError):
            pass

        # Resize if max_dimension is set and image exceeds it
        if max_dimension and max(img.size) > max_dimension:
            img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            logger.info(f"Resized to {img.size[0]}x{img.size[1]}")

        # Save with compression
        save_kwargs = {"optimize": True}

        if output_format == "jpg":
            save_kwargs["quality"] = quality
            save_kwargs["progressive"] = True
        elif output_format == "webp":
            save_kwargs["quality"] = quality
            save_kwargs["method"] = 4
        elif output_format == "png":
            save_kwargs["compress_level"] = 9

        img.save(
            output_path,
            format=output_format.upper() if output_format != "jpg" else "JPEG",
            **save_kwargs,
        )


async def compress_file(
    input_path: Path,
    preset: CompressionPreset = "facebook",
    image_format: ImageOutputFormat = "jpg",
) -> Optional[Path]:
    if is_video(input_path):
        return await compress_video(input_path, preset=preset)
    elif is_gif(input_path):
        return await compress_gif(input_path, preset=preset)
    elif is_image(input_path):
        return await compress_image(
            input_path, preset=preset, output_format=image_format
        )
    else:
        logger.error(f"Unsupported file type: {input_path.suffix}")
        return None


async def compress_gif(
    input_path: Path,
    output_path: Optional[Path] = None,
    preset: CompressionPreset = "facebook",
) -> Optional[Path]:
    """Compress animated GIF using FFmpeg"""
    if output_path is None:
        output_path = settings.download_dir / f"compressed_{input_path.stem}.gif"

    # GIF optimization: reduce colors and optimize palette
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        "fps=15,scale='min(480,iw)':-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer",
        str(output_path),
    ]

    logger.info(f"Compressing GIF: {input_path.name}")

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            logger.info(f"GIF compressed: {output_path.name}")
            return output_path
        else:
            logger.error(f"FFmpeg GIF error: {stderr.decode()}")
            return None

    except Exception as e:
        logger.error(f"GIF compression failed: {e}")
        return None


def check_ffmpeg_available() -> bool:
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def check_heic_support() -> bool:
    """Check if HEIC support is available via pillow-heif"""
    try:
        import pillow_heif  # noqa: F401

        return True
    except ImportError:
        return False
