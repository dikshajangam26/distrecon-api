from pathlib import Path
from uuid import uuid4
import shutil

from fastapi import FastAPI, UploadFile, File, HTTPException, status

from job_store import create_job, get_job
from tasks import reconstruct_scene


app = FastAPI(
    title="DistRecon API",
    description="A scalable API gateway for 3D scene reconstruction jobs.",
    version="0.3.0",
)


UPLOAD_DIR = Path("data/uploads")
OUTPUT_DIR = Path("data/outputs")

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024 * 1024  # 5GB
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def validate_file_extension(filename: str):
    file_extension = Path(filename).suffix.lower()

    if file_extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported video format. Please upload a video file.",
        )


def validate_upload_size(size_in_bytes: int | None):
    if size_in_bytes is not None and size_in_bytes > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Uploaded video is too large. Maximum allowed size is 5GB.",
        )


def validate_basic_video_header(file_path: Path):
    """
    Lightweight corruption check.

    This is not a full video decoder.
    It only catches obviously invalid files before sending work to Celery.
    """

    file_extension = file_path.suffix.lower()

    if file_extension == ".mp4":
        with file_path.open("rb") as file:
            header = file.read(12)

        if len(header) < 12 or b"ftyp" not in header[4:12]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file does not look like a valid MP4 video.",
            )


@app.get("/")
def read_root():
    return {
        "message": "DistRecon API is running",
        "docs_url": "/docs",
    }


@app.post("/reconstruct", status_code=status.HTTP_202_ACCEPTED)
async def create_reconstruction_job(video: UploadFile = File(...)):
    """
    Accept an uploaded video file and start a background reconstruction job.
    """

    validate_file_extension(video.filename or "")
    validate_upload_size(getattr(video, "size", None))

    job_id = str(uuid4())

    file_extension = Path(video.filename or ".mp4").suffix.lower()
    upload_path = UPLOAD_DIR / f"{job_id}{file_extension}"
    output_path = OUTPUT_DIR / job_id

    bytes_written = 0

    try:
        with upload_path.open("wb") as buffer:
            while True:
                chunk = await video.read(1024 * 1024)

                if not chunk:
                    break

                bytes_written += len(chunk)

                if bytes_written > MAX_UPLOAD_SIZE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Uploaded video is too large. Maximum allowed size is 5GB.",
                    )

                buffer.write(chunk)

        validate_basic_video_header(upload_path)

        create_job(
            job_id=job_id,
            file_path=str(upload_path),
            output_dir=str(output_path),
        )

        reconstruct_scene.delay(job_id, str(upload_path))

        return {
            "job_id": job_id,
            "status": "PENDING",
            "message": "Video uploaded successfully. Reconstruction job started in the background.",
        }

    except HTTPException:
        if upload_path.exists():
            upload_path.unlink(missing_ok=True)
        raise

    except Exception as error:
        if upload_path.exists():
            upload_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=500,
            detail=f"Failed to create reconstruction job: {str(error)}",
        )

    finally:
        await video.close()


@app.get("/status/{job_id}")
def get_job_status(job_id: str):
    """
    Return the current status of a reconstruction job.
    """

    job = get_job(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    return job