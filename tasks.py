import time

from celery import Celery

from job_store import update_job_status


celery = Celery(
    "distrecon_worker",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
)


@celery.task
def reconstruct_scene(job_id: str, file_path: str):
    """
    Mock background reconstruction task.

    For now, this only waits for 10 seconds.
    Later, we will replace this with real 3D reconstruction code.
    """

    print(f"[STARTED] Reconstruction job received: {job_id}")
    print(f"[INPUT] Video path: {file_path}")

    update_job_status(job_id, "PROCESSING")
    print(f"[PROCESSING] Job {job_id} is now processing")

    time.sleep(10)

    update_job_status(job_id, "SUCCESS")
    print(f"[SUCCESS] Job {job_id} completed successfully")

    return {
        "job_id": job_id,
        "file_path": file_path,
        "status": "SUCCESS",
    }
