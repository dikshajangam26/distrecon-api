import os
import shutil
import subprocess
from pathlib import Path


class PipelineError(Exception):
    """Custom error for reconstruction pipeline failures."""

    def __init__(self, message: str, error_log: dict | None = None):
        super().__init__(message)
        self.error_log = error_log or {}

def require_command(command_name: str):
    """
    Check if a command exists on the system.
    Example: ffmpeg, colmap, ns-process-data, ns-train
    """

    if shutil.which(command_name) is None:
        raise PipelineError(
            f"Required command not found: {command_name}. "
            f"Please install it before running the reconstruction pipeline."
        )


def run_command(command: list[str], step_name: str):
    """
    Safely run a terminal command.

    If the command fails, raise PipelineError with useful logs.
    """

    print(f"\n[PIPELINE STEP] {step_name}")
    print("[COMMAND]", " ".join(command))

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    except FileNotFoundError as error:
        error_log = {
            "step": step_name,
            "command": command,
            "stdout": "",
            "stderr": str(error),
            "return_code": None,
        }

        raise PipelineError(
            f"{step_name} failed because a required command was not found.",
            error_log=error_log,
        )

    except Exception as error:
        error_log = {
            "step": step_name,
            "command": command,
            "stdout": "",
            "stderr": str(error),
            "return_code": None,
        }

        raise PipelineError(
            f"{step_name} failed because of an unexpected system error.",
            error_log=error_log,
        )

    if result.returncode != 0:
        error_log = {
            "step": step_name,
            "command": command,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode,
        }

        error_message = (
            f"{step_name} failed. "
            f"This may happen if the video is blurry, has weak camera movement, "
            f"has too few visual features, or if the external tool could not process it."
        )

        raise PipelineError(
            error_message,
            error_log=error_log,
        )

    print(f"[DONE] {step_name}")

    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
    }

def extract_frames_from_video(video_path: Path, images_dir: Path):
    """
    Convert uploaded video into image frames.

    COLMAP works on images, not directly on video files.
    """

    require_command("ffmpeg")

    images_dir.mkdir(parents=True, exist_ok=True)

    frame_pattern = images_dir / "frame_%06d.jpg"

    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            "fps=0.5",
            str(frame_pattern),
        ],
        "Extract frames from video",
    )


def run_colmap_sparse_reconstruction(workspace_dir: Path):
    """
    Run the basic COLMAP sparse reconstruction pipeline.

    Steps:
    1. Feature extraction
    2. Feature matching
    3. Sparse mapping
    """

    require_command("colmap")

    images_dir = workspace_dir / "images"
    database_path = workspace_dir / "database.db"
    sparse_dir = workspace_dir / "sparse"

    sparse_dir.mkdir(parents=True, exist_ok=True)

    run_command(
        [
            "colmap",
            "feature_extractor",
            "--database_path",
            str(database_path),
            "--image_path",
            str(images_dir),
            "--SiftExtraction.use_gpu",
            "0",
            "--SiftExtraction.max_image_size",
            "1600",
            "--SiftExtraction.num_threads",
            "2",
        ],
        "COLMAP feature extraction",
    )

    run_command(
        [
            "colmap",
            "exhaustive_matcher",
            "--database_path",
            str(database_path),
            "--SiftMatching.use_gpu",
            "0",
            "--SiftMatching.num_threads",
            "2",
        ],
        "COLMAP feature matching",
    )

    run_command(
        [
            "colmap",
            "mapper",
            "--database_path",
            str(database_path),
            "--image_path",
            str(images_dir),
            "--output_path",
            str(sparse_dir),
        ],
        "COLMAP sparse reconstruction",
    )

    sparse_model_dir = sparse_dir / "0"

    if not sparse_model_dir.exists():
        raise PipelineError(
            "COLMAP finished, but no sparse model was created at sparse/0. "
            "This usually means the video frames did not have enough matching visual features, "
            "or the camera movement was not suitable for reconstruction.",
            error_log={
                "step": "Validate COLMAP sparse model",
                "expected_path": str(sparse_model_dir),
                "reason": "Missing sparse/0 output directory",
            },
        )


    return sparse_model_dir


def run_nerfstudio_pipeline(video_path: Path, output_dir: Path):
    """
    Optional Nerfstudio processing and training step.

    This only runs if RUN_NERFSTUDIO=1 is set in the environment.
    """

    require_command("ns-process-data")
    require_command("ns-train")

    nerfstudio_dir = output_dir / "nerfstudio"
    processed_data_dir = nerfstudio_dir / "processed"

    processed_data_dir.mkdir(parents=True, exist_ok=True)

    run_command(
        [
            "ns-process-data",
            "video",
            "--data",
            str(video_path),
            "--output-dir",
            str(processed_data_dir),
        ],
        "Nerfstudio process video data",
    )

    run_command(
        [
            "ns-train",
            "nerfacto",
            "--data",
            str(processed_data_dir),
        ],
        "Nerfstudio train nerfacto model",
    )

    return processed_data_dir


def run_reconstruction_pipeline(job_id: str, file_path: str):
    """
    Main pipeline called by the Celery worker.
    """

    video_path = Path(file_path)
    output_dir = Path("data/outputs") / job_id
    workspace_dir = output_dir / "colmap_workspace"
    images_dir = workspace_dir / "images"

    output_dir.mkdir(parents=True, exist_ok=True)
    workspace_dir.mkdir(parents=True, exist_ok=True)

    extract_frames_from_video(video_path, images_dir)

    sparse_model_dir = run_colmap_sparse_reconstruction(workspace_dir)

    result = {
        "output_dir": str(output_dir),
        "colmap_workspace": str(workspace_dir),
        "sparse_model_dir": str(sparse_model_dir),
    }

    run_nerfstudio = os.getenv("RUN_NERFSTUDIO", "0") == "1"

    if run_nerfstudio:
        nerfstudio_data_dir = run_nerfstudio_pipeline(video_path, output_dir)
        result["nerfstudio_data_dir"] = str(nerfstudio_data_dir)
    else:
        result["nerfstudio_status"] = "SKIPPED"

    return result