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
    }

    redis_client.set(f"job:{job_id}", json.dumps(job_data))


def update_job_status(job_id: str, status: str):
    job_key = f"job:{job_id}"
    job_data = redis_client.get(job_key)

    if job_data is None:
        return None

    job = json.loads(job_data)
    job["status"] = status

    redis_client.set(job_key, json.dumps(job))
    return job


def get_job(job_id: str):
    job_data = redis_client.get(f"job:{job_id}")

    if job_data is None:
        return None

    return json.loads(job_data)