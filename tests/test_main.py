import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.main as main


client = TestClient(main.app)


class FakeCeleryTask:
    def delay(self, job_id: str, file_path: str):
        return None


@pytest.fixture(autouse=True)
def patch_external_services(monkeypatch):
    """
    Prevent tests from needing Redis or a real Celery worker.
    """

    fake_jobs = {}

    def fake_create_job(job_id: str, file_path: str, output_dir: str):
        fake_jobs[job_id] = {
            "job_id": job_id,
            "status": "PENDING",
            "input_file": file_path,
            "output_dir": output_dir,
            "error": None,
            "error_log": None,
        }

    def fake_get_job(job_id: str):
        return fake_jobs.get(job_id)

    monkeypatch.setattr(main, "create_job", fake_create_job)
    monkeypatch.setattr(main, "get_job", fake_get_job)
    monkeypatch.setattr(main, "reconstruct_scene", FakeCeleryTask())


def test_root_endpoint_returns_success():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["message"] == "DistRecon API is running"


def test_reconstruct_accepts_valid_mp4():
    fake_mp4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100

    response = client.post(
        "/reconstruct",
        files={
            "video": (
                "sample.mp4",
                fake_mp4,
                "video/mp4",
            )
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "PENDING"
    assert "job_id" in body


def test_reconstruct_rejects_corrupted_mp4():
    corrupted_file = b"this is not a real mp4 file"

    response = client.post(
        "/reconstruct",
        files={
            "video": (
                "corrupted.mp4",
                corrupted_file,
                "video/mp4",
            )
        },
    )

    assert response.status_code == 400
    assert "valid MP4" in response.json()["detail"]


def test_reconstruct_rejects_unsupported_extension():
    response = client.post(
        "/reconstruct",
        files={
            "video": (
                "notes.txt",
                b"hello",
                "text/plain",
            )
        },
    )

    assert response.status_code == 400
    assert "Unsupported video format" in response.json()["detail"]


def test_validate_upload_size_rejects_over_5gb():
    too_large_size = main.MAX_UPLOAD_SIZE_BYTES + 1

    with pytest.raises(HTTPException) as error:
        main.validate_upload_size(too_large_size)

    assert error.value.status_code == 413