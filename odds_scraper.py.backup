from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any


def fetch_trifecta_odds_safe(
    racecard_url: str,
    headless: bool = True,
    timeout_seconds: int = 120,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Playwright処理を別Pythonプロセスで実行する。
    ChromiumがクラッシュしてもStreamlit本体を巻き込まない。
    """
    worker_path = Path(__file__).with_name("odds_worker.py")

    with tempfile.TemporaryDirectory(prefix="keirin_odds_") as temp_dir:
        output_path = Path(temp_dir) / "result.json"

        command = [
            sys.executable,
            str(worker_path),
            "--racecard-url",
            racecard_url,
            "--output",
            str(output_path),
        ]
        if headless:
            command.append("--headless")

        logs = [
            "取得方式: 別プロセス",
            f"Worker: {worker_path.name}",
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
            logs.append(f"エラー: {timeout_seconds}秒でタイムアウトしました。")
            return [], logs
        except Exception as exc:
            logs.append(f"起動エラー: {type(exc).__name__}: {exc}")
            return [], logs

        logs.append(f"Worker終了コード: {completed.returncode}")

        if completed.stdout.strip():
            logs.append("Worker標準出力:")
            logs.extend(completed.stdout.strip().splitlines()[-20:])

        if completed.stderr.strip():
            logs.append("Worker標準エラー:")
            logs.extend(completed.stderr.strip().splitlines()[-30:])

        if completed.returncode != 0:
            logs.append(
                "オッズ取得用プロセスが異常終了しましたが、"
                "Streamlit本体は継続しています。"
            )
            return [], logs

        if not output_path.exists():
            logs.append("エラー: Workerの結果ファイルが作成されませんでした。")
            return [], logs

        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logs.append(f"結果読込エラー: {type(exc).__name__}: {exc}")
            return [], logs

        worker_logs = payload.get("logs", [])
        logs.extend(str(item) for item in worker_logs)

        rows = payload.get("rows", [])
        if not isinstance(rows, list):
            logs.append("エラー: 取得結果の形式が不正です。")
            return [], logs

        return rows, logs
