from pathlib import Path
from uuid import uuid4
import shutil

from fastapi import FastAPI, UploadFile, File, HTTPException, status

from job_store import create_job, get_job
from tasks import reconstruct_scene


app = FastAPI(
    title="DistRecon API",
    description="A simple API gateway for 3D scene reconstruction jobs.",
    version="0.2.0",
)


UPLOAD_DIR = Path("data/uploads")
OUTPUT_DIR = Path("data/outputs")

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/")
def read_root():
    return {
        "message": "DistRecon API is running",
        "docs_url": "/docs",
    }


@app.post("/reconstruct", status_code=status.HTTP_202_ACCEPTED)
async def create_reconstruction_job(video: UploadFile = File(...)):
    """
    Accept a raw uploaded video file and start a background reconstruction job.
    """

    job_id = str(uuid4())

    upload_path = UPLOAD_DIR / f"{job_id}.mp4"
    output_path = OUTPUT_DIR / job_id

    try:
        with upload_path.open("wb") as buffer:
            shutil.copyfileobj(video.file, buffer)

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

    except Exception as error:
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