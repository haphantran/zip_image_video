import uuid
import io
import zipfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from loguru import logger

from app.config import settings
from app.services.job_manager import job_manager, JobStatus
from app.services.ffmpeg_compressor import (
    compress_file,
    check_ffmpeg_available,
    check_heic_support,
)

app = FastAPI(title="Media Compression Service", version="2.0.0")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

ALLOWED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".bmp",
    ".tiff",
    ".heic",
    ".heif",
}
ALLOWED_VIDEO_EXTENSIONS = {
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
ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS


async def process_compression_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        return

    job_manager.update_job(job_id, status=JobStatus.PROCESSING, progress=10)

    try:
        job_manager.update_job(job_id, progress=30)

        compressed_path = await compress_file(
            job.original_path, preset=job.preset, image_format=job.image_format
        )

        job_manager.update_job(job_id, progress=90)

        if compressed_path and compressed_path.exists():
            job_manager.update_job(
                job_id,
                status=JobStatus.COMPLETED,
                progress=100,
                compressed_path=compressed_path,
            )
            logger.info(f"Job {job_id} completed successfully")
        else:
            job_manager.update_job(
                job_id,
                status=JobStatus.FAILED,
                error_message="Compression produced no output",
            )

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        job_manager.update_job(job_id, status=JobStatus.FAILED, error_message=str(e))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "ffmpeg_available": check_ffmpeg_available(),
            "heic_support": check_heic_support(),
        },
    )


@app.post("/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    preset: str = Form("facebook"),
    image_format: str = Form("jpg"),
):
    filename = file.filename or ""
    if not filename:
        raise HTTPException(status_code=400, detail="No file provided")

    filename = str(filename)
    file_ext = Path(filename).suffix.lower() if filename else ""

    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_ext}. Supported: images (jpg, png, heic, webp, gif) and videos (mp4, mov, avi, mkv, webm)",
        )

    file_id = str(uuid.uuid4())[:8]
    file_path = settings.upload_dir / f"{file_id}_{filename}"

    content = await file.read()
    if len(content) > settings.max_file_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.max_file_size_mb}MB",
        )

    with open(file_path, "wb") as buffer:
        buffer.write(content)

    job = job_manager.create_job(
        original_filename=filename,
        original_path=file_path,
        preset=preset,
        image_format=image_format,
    )

    background_tasks.add_task(process_compression_job, job.id)

    return {"job_id": job.id, "message": "Upload successful, processing started"}


@app.get("/job/{job_id}")
async def get_job_status(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@app.delete("/job/{job_id}")
async def delete_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.original_path and job.original_path.exists():
        try:
            job.original_path.unlink()
        except Exception:
            pass
    if job.compressed_path and job.compressed_path.exists():
        try:
            job.compressed_path.unlink()
        except Exception:
            pass

    job_manager.delete_job(job_id)
    return {"message": "Job deleted"}


@app.get("/jobs")
async def list_jobs():
    return {"jobs": job_manager.list_jobs()}


@app.delete("/jobs")
async def clear_all_jobs():
    """Clear all jobs and their associated files"""
    jobs = job_manager.list_jobs()
    cleared_count = 0

    for job_dict in jobs:
        job = job_manager.get_job(job_dict["id"])
        if job:
            # Delete original uploaded file
            if job.original_path and job.original_path.exists():
                try:
                    job.original_path.unlink()
                except Exception:
                    pass
            # Delete compressed output file
            if job.compressed_path and job.compressed_path.exists():
                try:
                    job.compressed_path.unlink()
                except Exception:
                    pass
            cleared_count += 1

    job_manager.clear_all()
    return {"message": f"Cleared {cleared_count} jobs", "cleared": cleared_count}


@app.get("/download/{job_id}")
async def download_file(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.COMPLETED or not job.compressed_path:
        raise HTTPException(status_code=400, detail="File not ready for download")

    if not job.compressed_path.exists():
        raise HTTPException(status_code=404, detail="Compressed file not found")

    return FileResponse(
        path=job.compressed_path,
        filename=job.compressed_path.name,
        media_type="application/octet-stream",
    )


@app.get("/download-all")
async def download_all_completed():
    """Download all completed files as a ZIP archive"""
    from datetime import datetime

    completed_jobs = [
        job
        for job in job_manager.list_jobs()
        if job.get("status") == "completed" and job.get("download_ready")
    ]

    if not completed_jobs:
        raise HTTPException(status_code=400, detail="No completed files to download")

    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for job_dict in completed_jobs:
            job = job_manager.get_job(job_dict["id"])
            if job and job.compressed_path and job.compressed_path.exists():
                zip_file.write(job.compressed_path, job.compressed_path.name)

    zip_buffer.seek(0)

    # Generate filename with timestamp: compressed_YYYYMMDD_HHMM.zip
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"compressed_{timestamp}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/thumbnail/{job_id}")
async def get_thumbnail(job_id: str):
    """Get a thumbnail for an uploaded file"""
    from PIL import Image
    import pillow_heif

    pillow_heif.register_heif_opener()

    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.original_path or not job.original_path.exists():
        raise HTTPException(status_code=404, detail="Original file not found")

    file_ext = job.original_path.suffix.lower()
    is_video = file_ext in {
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
    is_image = file_ext in {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".bmp",
        ".tiff",
        ".heic",
        ".heif",
        ".gif",
    }

    try:
        if is_image:
            # Generate thumbnail using Pillow
            with Image.open(job.original_path) as img:
                # Convert to RGB if needed
                if img.mode in ("RGBA", "LA", "P"):
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    background.paste(
                        img,
                        mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None,
                    )
                    img = background
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                # Create thumbnail (max 200x200)
                img.thumbnail((200, 200), Image.Resampling.LANCZOS)

                # Save to buffer
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=70)
                buffer.seek(0)

                return StreamingResponse(buffer, media_type="image/jpeg")

        elif is_video:
            # Generate video thumbnail using FFmpeg
            import asyncio
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp_path = tmp.name

            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(job.original_path),
                "-ss",
                "00:00:01",  # Capture at 1 second
                "-vframes",
                "1",
                "-vf",
                "scale=200:-1",
                tmp_path,
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            if Path(tmp_path).exists() and Path(tmp_path).stat().st_size > 0:
                with open(tmp_path, "rb") as f:
                    content = f.read()
                Path(tmp_path).unlink()
                return StreamingResponse(io.BytesIO(content), media_type="image/jpeg")
            else:
                Path(tmp_path).unlink(missing_ok=True)
                raise HTTPException(
                    status_code=500, detail="Failed to generate video thumbnail"
                )

        else:
            raise HTTPException(
                status_code=400, detail="Cannot generate thumbnail for this file type"
            )

    except Exception as e:
        logger.error(f"Thumbnail generation failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Thumbnail generation failed: {str(e)}"
        )


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "ffmpeg_available": check_ffmpeg_available(),
        "heic_support": check_heic_support(),
    }


@app.on_event("startup")
async def startup_event():
    logger.info("Starting Media Compression Service")
    logger.info(f"FFmpeg available: {check_ffmpeg_available()}")
    logger.info(f"HEIC support: {check_heic_support()}")
