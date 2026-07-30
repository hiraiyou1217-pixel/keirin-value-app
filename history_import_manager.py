from __future__ import annotations

from datetime import date, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from typing import Any


IMPORT_ROOT = (
    Path(__file__).resolve().parent
    / "data"
    / "history_import_jobs"
)


def _atomic_write_json(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )
    temporary.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def _read_json(
    path: Path,
) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return {}

    return (
        payload
        if isinstance(payload, dict)
        else {}
    )


def _pid_is_running(
    pid: int,
) -> bool:
    if pid <= 0:
        return False

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

    return True


def load_job(
    job_id: str,
) -> dict[str, Any]:
    job_directory = (
        IMPORT_ROOT
        / str(job_id)
    )
    progress = _read_json(
        job_directory / "progress.json"
    )
    request = _read_json(
        job_directory / "request.json"
    )

    if not progress and not request:
        return {}

    pid = 0

    try:
        pid = int(
            (
                job_directory
                / "pid.txt"
            )
            .read_text(
                encoding="utf-8"
            )
            .strip()
        )
    except (OSError, ValueError):
        pass

    output = {
        **request,
        **progress,
        "job_id": str(job_id),
        "job_directory": str(
            job_directory
        ),
        "pid": pid,
    }

    if (
        output.get("status") == "running"
        and pid
        and not _pid_is_running(pid)
    ):
        output["status"] = "stopped"
        output["message"] = (
            "Workerが終了しました。"
            "ログを確認してください。"
        )

    return output


def load_latest_job() -> dict[str, Any]:
    if not IMPORT_ROOT.exists():
        return {}

    directories = sorted(
        (
            path
            for path in IMPORT_ROOT.iterdir()
            if path.is_dir()
        ),
        key=lambda path: path.name,
        reverse=True,
    )

    for directory in directories:
        job = load_job(directory.name)

        if job:
            return job

    return {}


def start_history_import(
    *,
    start_date: date,
    end_date: date,
    maximum_races: int,
) -> dict[str, Any]:
    if start_date > end_date:
        raise ValueError(
            "開始日は終了日以前にしてください。"
        )

    if end_date >= date.today():
        raise ValueError(
            "過去レース専用です。"
            "終了日は昨日以前にしてください。"
        )

    maximum = int(maximum_races)

    if not 1 <= maximum <= 1000:
        raise ValueError(
            "最大取得数は1〜1000で指定してください。"
        )

    latest = load_latest_job()

    if latest.get("status") == "running":
        raise RuntimeError(
            "別の過去レースWorkerが実行中です。"
        )

    IMPORT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )
    job_id = (
        datetime.now().strftime(
            "%Y%m%dT%H%M%S"
        )
        + "_"
        + uuid.uuid4().hex[:8]
    )
    job_directory = IMPORT_ROOT / job_id
    job_directory.mkdir(
        parents=False,
        exist_ok=False,
    )

    request = {
        "job_id": job_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "maximum_races": maximum,
        "created_at": datetime.now().isoformat(
            timespec="seconds"
        ),
    }
    progress = {
        **request,
        "status": "running",
        "phase": "starting",
        "message": "Workerを起動しています。",
        "discovered": 0,
        "total": 0,
        "processed": 0,
        "success_count": 0,
        "failure_count": 0,
        "review_count": 0,
        "independent_count": 0,
        "successes": [],
        "failures": [],
        "reviews": [],
        "updated_at": datetime.now().isoformat(
            timespec="seconds"
        ),
    }

    _atomic_write_json(
        job_directory / "request.json",
        request,
    )
    _atomic_write_json(
        job_directory / "progress.json",
        progress,
    )

    worker_path = Path(__file__).with_name(
        "history_import_worker.py"
    )
    log_path = job_directory / "worker.log"

    with log_path.open("ab") as log_file:
        process = subprocess.Popen(
            [
                sys.executable,
                str(worker_path),
                "--job-dir",
                str(job_directory),
            ],
            cwd=str(worker_path.parent),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )

    (
        job_directory
        / "pid.txt"
    ).write_text(
        str(process.pid),
        encoding="utf-8",
    )

    return load_job(job_id)
