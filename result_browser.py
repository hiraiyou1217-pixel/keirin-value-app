from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def fetch_race_result(
    *,
    race_url: str,
    valid_car_numbers: list[int],
    timeout_seconds: int = 90,
) -> tuple[dict[str, Any], list[str]]:
    worker_path = Path(__file__).with_name(
        "result_dom_worker.py"
    )

    logs = [
        "結果処理: 分離Worker",
        f"Worker: {worker_path.name}",
    ]

    payload = {
        "race_url": race_url,
        "valid_car_numbers": (
            valid_car_numbers
        ),
    }

    with tempfile.TemporaryDirectory(
        prefix="keirin_result_"
    ) as temporary_directory:
        temporary_path = Path(
            temporary_directory
        )

        input_path = (
            temporary_path
            / "input.json"
        )

        output_path = (
            temporary_path
            / "output.json"
        )

        input_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(worker_path),
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                ],
                cwd=str(worker_path.parent),
                capture_output=True,
                text=True,
                timeout=int(
                    timeout_seconds
                ),
            )

        except subprocess.TimeoutExpired:
            return (
                {
                    "success": False,
                    "status": "timeout",
                    "message": (
                        "結果取得が"
                        "タイムアウトしました。"
                    ),
                },
                logs,
            )

        logs.append(
            "Worker終了コード: "
            f"{completed.returncode}"
        )

        if completed.stderr.strip():
            logs.append(
                "Worker標準エラー:"
            )

            logs.extend(
                completed.stderr.strip()
                .splitlines()[-30:]
            )

        if not output_path.exists():
            return (
                {
                    "success": False,
                    "status": "error",
                    "message": (
                        "結果ファイルが"
                        "作成されませんでした。"
                    ),
                },
                logs,
            )

        result = json.loads(
            output_path.read_text(
                encoding="utf-8"
            )
        )

        logs.extend(
            result.get(
                "logs",
                [],
            )
        )

        return result, logs
