from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def run_calculation_worker(
    odds: list[dict[str, Any]],
    scores: dict[int, float],
    riders: list[dict[str, Any]],
    lineup_groups: list[list[int]],
    settings: dict[str, Any],
    timeout_seconds: int = 60,
) -> tuple[dict[str, Any], list[str]]:
    worker_path = Path(__file__).with_name(
        "calculation_worker.py"
    )

    logs = [
        "期待値計算処理: 分離Worker",
        f"Worker: {worker_path.name}",
    ]

    payload = {
        "odds": odds,
        "scores": {
            str(number): float(score)
            for number, score in scores.items()
        },
        "riders": riders,
        "lineup_groups": lineup_groups,
        "settings": settings,
    }

    with tempfile.TemporaryDirectory(
        prefix="keirin_calculation_"
    ) as temporary_directory:
        temporary_path = Path(temporary_directory)
        input_path = temporary_path / "input.json"
        output_path = temporary_path / "output.json"

        input_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        command = [
            sys.executable,
            str(worker_path),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]

        try:
            completed = subprocess.run(
                command,
                cwd=str(worker_path.parent),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )

        except subprocess.TimeoutExpired:
            return (
                {
                    "success": False,
                    "expected_values": [],
                    "bet_plan": [],
                    "candidate_count": 0,
                    "message": (
                        "期待値計算がタイムアウトしました。"
                    ),
                },
                logs,
            )

        except Exception as exc:
            return (
                {
                    "success": False,
                    "expected_values": [],
                    "bet_plan": [],
                    "candidate_count": 0,
                    "message": (
                        f"Worker起動エラー: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                },
                logs,
            )

        logs.append(
            f"Worker終了コード: {completed.returncode}"
        )

        if completed.stderr.strip():
            logs.append("Worker標準エラー:")
            logs.extend(
                completed.stderr.strip().splitlines()[-30:]
            )

        if not output_path.exists():
            return (
                {
                    "success": False,
                    "expected_values": [],
                    "bet_plan": [],
                    "candidate_count": 0,
                    "message": (
                        "計算結果ファイルが作成されませんでした。"
                    ),
                },
                logs,
            )

        result = json.loads(
            output_path.read_text(encoding="utf-8")
        )

        if result.get("traceback"):
            logs.extend(
                str(result["traceback"]).splitlines()
            )

        return result, logs
