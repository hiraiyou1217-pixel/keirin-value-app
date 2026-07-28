from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any


def fetch_all_trifecta_odds_browser(
    racecard_url: str,
    timeout_seconds: int = 120,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    DOM操作は別Pythonプロセスで実行する。

    ChromeやPlaywrightに問題が起きても、
    Streamlit本体を巻き込まない。
    """
    worker_path = Path(__file__).with_name(
        "odds_dom_worker.py"
    )

    logs = [
        "取得処理: 分離Worker",
        f"Worker: {worker_path.name}",
    ]

    with tempfile.TemporaryDirectory(
        prefix="keirin_odds_"
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
                f"取得処理が{timeout_seconds}秒で"
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
                completed.stderr
                .strip()
                .splitlines()[-30:]
            )

        if not output_path.exists():
            logs.append(
                "Workerの結果ファイルがありません。"
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

        rows = payload.get("rows", [])

        if not isinstance(rows, list):
            logs.append(
                "Workerの取得結果が不正です。"
            )
            return [], logs

        return rows, logs
