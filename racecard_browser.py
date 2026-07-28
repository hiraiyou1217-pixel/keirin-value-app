from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any


def fetch_racecard_data_browser(
    racecard_url: str,
    timeout_seconds: int = 90,
) -> tuple[list[dict[str, Any]], list[str]]:
    worker_path = Path(__file__).with_name(
        "racecard_dom_worker.py"
    )

    logs = [
        "出走表処理: 分離Worker",
        f"Worker: {worker_path.name}",
    ]

    with tempfile.TemporaryDirectory(
        prefix="keirin_racecard_"
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
                f"出走表取得が{timeout_seconds}秒で"
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
                "出走表Workerの結果ファイルがありません。"
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

        if not payload.get("success"):
            return [], logs

        riders = payload.get("riders", [])

        if not isinstance(riders, list):
            logs.append(
                "選手データの形式が不正です。"
            )
            return [], logs

        return riders, logs
