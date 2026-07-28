from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any


def fetch_lineup_browser(
    racecard_url: str,
    rider_numbers: list[int],
    timeout_seconds: int = 90,
) -> tuple[list[list[int]], list[str]]:
    worker_path = Path(__file__).with_name(
        "lineup_dom_worker.py"
    )

    logs = [
        "並び予想処理: 分離Worker",
        f"Worker: {worker_path.name}",
    ]

    with tempfile.TemporaryDirectory(
        prefix="keirin_lineup_"
    ) as temporary_directory:
        output_path = (
            Path(temporary_directory)
            / "result.json"
        )

        command = [
            sys.executable,
            str(worker_path),
            "--racecard-url",
            racecard_url,
            "--riders",
            ",".join(str(value) for value in rider_numbers),
            "--output",
            str(output_path),
        ]

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=str(worker_path.parent),
            )

        except subprocess.TimeoutExpired:
            logs.append(
                f"並び予想取得が{timeout_seconds}秒で"
                "タイムアウトしました。"
            )
            return [], logs

        except Exception as exc:
            logs.append(
                f"Worker起動エラー: "
                f"{type(exc).__name__}: {exc}"
            )
            return [], logs

        logs.append(
            f"Worker終了コード: "
            f"{completed.returncode}"
        )

        if completed.stderr.strip():
            logs.append("Worker標準エラー:")
            logs.extend(
                completed.stderr.strip().splitlines()[-30:]
            )

        if not output_path.exists():
            logs.append(
                "並び予想Workerの結果ファイルがありません。"
            )
            return [], logs

        try:
            payload = json.loads(
                output_path.read_text(
                    encoding="utf-8"
                )
            )

        except Exception as exc:
            logs.append(
                f"結果読込エラー: "
                f"{type(exc).__name__}: {exc}"
            )
            return [], logs

        logs.extend(
            str(message)
            for message in payload.get(
                "logs",
                [],
            )
        )

        groups = payload.get("groups", [])

        if not payload.get("success"):
            return [], logs

        if not isinstance(groups, list):
            logs.append(
                "並び予想データの形式が不正です。"
            )
            return [], logs

        return groups, logs
