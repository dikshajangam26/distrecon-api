from celery import Celery

from job_store import update_job_status, update_job_error
from pipeline import PipelineError, run_reconstruction_pipeline


celery = Celery(
    "distrecon_worker",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
)


@celery.task
def reconstruct_scene(job_id: str, file_path: str):
    """
    Background reconstruction task.

    This calls the real reconstruction pipeline and handles failures cleanly.
    """

    print(f"[STARTED] Reconstruction job received: {job_id}")
    print(f"[INPUT] Video path: {file_path}")

    try:
        update_job_status(job_id, "PROCESSING")

        result = run_reconstruction_pipeline(
            job_id=job_id,
            file_path=file_path,
        )

        update_job_status(
            job_id=job_id,
            status="SUCCESS",
            extra_data=result,
        )

        print(f"[SUCCESS] Job {job_id} completed successfully")

        return {
            "job_id": job_id,
            "status": "SUCCESS",
            **result,
        }

    except PipelineError as error:
        error_message = str(error)

        update_job_error(
            job_id=job_id,
            error_message=error_message,
            error_log=error.error_log,
        )

        print(f"[FAILED] Job {job_id} failed")
        print(error_message)
        print(error.error_log)

        return {
            "job_id": job_id,
            "status": "FAILED",
            "error": error_message,
            "error_log": error.error_log,
        }

    except Exception as error:
        error_message = str(error)

        update_job_error(
            job_id=job_id,
            error_message=error_message,
            error_log={
                "step": "Unknown",
                "reason": "Unexpected worker error",
            },
        )

        print(f"[FAILED] Job {job_id} failed with unexpected error")
        print(error_message)

        return {
            "job_id": job_id,
            "status": "FAILED",
            "error": error_message,
        }