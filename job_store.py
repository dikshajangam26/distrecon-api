import json
import redis


redis_client = redis.Redis(
    host="localhost",
    port=6379,
    db=1,
    decode_responses=True,
)


def create_job(job_id: str, file_path: str, output_dir: str):
    job_data = {
        "job_id": job_id,
        "status": "PENDING",
        "input_file": file_path,
        "output_dir": output_dir,
        "error": None,
        "error_log": None,
    }

    redis_client.set(f"job:{job_id}", json.dumps(job_data))


def update_job_status(job_id: str, status: str, extra_data: dict | None = None):
    job_key = f"job:{job_id}"
    job_data = redis_client.get(job_key)

    if job_data is None:
        return None

    job = json.loads(job_data)
    job["status"] = status

    if extra_data:
        job.update(extra_data)

    redis_client.set(job_key, json.dumps(job))
    return job


def update_job_error(job_id: str, error_message: str, error_log: dict | None = None):
    return update_job_status(
        job_id=job_id,
        status="FAILED",
        extra_data={
            "error": error_message,
            "error_log": error_log,
        },
    )


def get_job(job_id: str):
    job_data = redis_client.get(f"job:{job_id}")

    if job_data is None:
        return None

    return json.loads(job_data)