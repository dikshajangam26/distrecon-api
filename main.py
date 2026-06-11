from pathlib import Path
from uuid import uuid4
import shutil

from fastapi import FastAPI, UploadFile, File, HTTPException, status


app = FastAPI(
    title="DistRecon API",
    description="A simple API gateway for 3D scene reconstruction jobs.",
    version="0.1.0",
)


# Local folders for uploaded videos and future output files
UPLOAD_DIR = Path("data/uploads")
OUTPUT_DIR = Path("data/outputs")

# Create folders automatically if they do not exist
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# Simple in-memory job database
# Important: this resets when the server restarts
jobs_db = {}


@app.get("/")
def read_root():
    return {
        "message": "DistRecon API is running",
        "docs_url": "/docs",
    }


@app.post("/reconstruct", status_code=status.HTTP_202_ACCEPTED)
async def create_reconstruction_job(video: UploadFile = File(...)):
    """
    Accept a raw uploaded video file and create a reconstruction job.
    """

    # Create a unique job ID
    job_id = str(uuid4())

    # Save uploaded video as data/uploads/<job_id>.mp4
    upload_path = UPLOAD_DIR / f"{job_id}.mp4"

    try:
        with upload_path.open("wb") as buffer:
            shutil.copyfileobj(video.file, buffer)

        jobs_db[job_id] = {
            "job_id": job_id,
            "status": "PENDING",
            "input_file": str(upload_path),
            "output_dir": str(OUTPUT_DIR / job_id),
        }

        return {
            "job_id": job_id,
            "status": "PENDING",
            "message": "Video uploaded successfully. Reconstruction job created.",
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save uploaded video: {str(error)}",
        )

    finally:
        await video.close()


@app.get("/status/{job_id}")
def get_job_status(job_id: str):
    """
    Return the current status of a reconstruction job.
    """

    job = jobs_db.get(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    return job