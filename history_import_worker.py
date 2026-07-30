from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import traceback
from typing import Any

from history_catalog import (
    fetch_result_catalog,
    parse_result_catalog_html,
)
from learning_database import (
    get_race_by_identity,
    get_race_car_numbers,
    race_has_complete_learning_data,
    race_has_enriched_learning_features,
    save_independent_race_snapshot,
    save_race_result,
    save_race_review,
    save_race_snapshot,
    update_race_urls_by_identity,
    validate_complete_odds,
)
from lineup_browser import fetch_lineup_browser
from lineup_from_comments import (
    infer_lineup_from_comments,
    select_authoritative_lineup,
)
from odds_browser import (
    fetch_all_trifecta_odds_browser,
)
from odds_http import (
    fetch_trifecta_odds_http,
)
from racecard_browser import (
    fetch_racecard_data_browser,
)
from result_browser import fetch_race_result


def _atomic_write_json(
    path: Path,
    payload: dict[str, Any],
) -> None:
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


def _date_range(
    start_date: date,
    end_date: date,
) -> list[date]:
    days = (
        end_date - start_date
    ).days

    return [
        start_date + timedelta(days=offset)
        for offset in range(days + 1)
    ]


def _validate_lineup(
    groups: list[list[int]],
    rider_numbers: list[int],
) -> tuple[bool, str]:
    expected = {
        int(number)
        for number in rider_numbers
    }
    flattened = [
        int(number)
        for group in groups
        for number in group
    ]

    if not groups:
        return False, "並びを取得できませんでした。"

    if len(flattened) != len(
        set(flattened)
    ):
        return False, "並びに重複車番があります。"

    if set(flattened) != expected:
        return (
            False,
            "並びの車番が出走車番と一致しません。",
        )

    return True, "並びの全車番を確認しました。"


class Progress:
    def __init__(
        self,
        job_directory: Path,
        request: dict[str, Any],
    ) -> None:
        self.path = (
            job_directory
            / "progress.json"
        )
        self.data: dict[str, Any] = {
            **request,
            "status": "running",
            "phase": "discovery",
            "message": (
                "日付別結果一覧を確認しています。"
            ),
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
            "started_at": (
                datetime.now().isoformat(
                    timespec="seconds"
                )
            ),
        }
        self.write()

    def write(self) -> None:
        self.data["updated_at"] = (
            datetime.now().isoformat(
                timespec="seconds"
            )
        )
        _atomic_write_json(
            self.path,
            self.data,
        )

    def set(
        self,
        **values: Any,
    ) -> None:
        self.data.update(values)
        self.write()

    def append(
        self,
        category: str,
        detail: dict[str, Any],
    ) -> None:
        mapping = {
            "success": (
                "successes",
                "success_count",
            ),
            "failure": (
                "failures",
                "failure_count",
            ),
            "review": (
                "reviews",
                "review_count",
            ),
        }
        list_key, count_key = mapping[
            category
        ]
        self.data[list_key].append(detail)
        self.data[count_key] = len(
            self.data[list_key]
        )

        if (
            detail.get("data_scope")
            == "independent"
        ):
            self.data["independent_count"] = (
                int(
                    self.data.get(
                        "independent_count",
                        0,
                    )
                )
                + 1
            )

        self.write()


def _base_detail(
    entry: dict[str, Any],
) -> dict[str, Any]:
    return {
        "race_date": str(
            entry.get("race_date", "")
        ),
        "venue": str(
            entry.get("venue", "")
        ),
        "race_number": int(
            entry.get("race_number", 0)
        ),
        "racecard_url": str(
            entry.get("racecard_url", "")
        ),
        "result_url": str(
            entry.get("result_url", "")
        ),
    }


def _collect_learning_snapshot(
    entry: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[list[int]],
    bool,
]:
    racecard_url = str(
        entry["racecard_url"]
    )
    riders, rider_logs = (
        fetch_racecard_data_browser(
            racecard_url
        )
    )

    for log in rider_logs:
        print(
            f"[racecard] {log}",
            flush=True,
        )

    if not riders:
        raise RuntimeError(
            "出走表・選手データを"
            "取得できませんでした。"
        )

    rider_numbers = sorted(
        int(rider["車番"])
        for rider in riders
    )

    odds_rows, odds_logs = (
        fetch_trifecta_odds_http(
            racecard_url
        )
    )

    for log in odds_logs:
        print(
            f"[odds-http] {log}",
            flush=True,
        )

    complete, complete_message = (
        validate_complete_odds(
            riders,
            odds_rows,
        )
    )

    if not complete:
        print(
            "[odds] HTTP取得が不完全なため"
            "DOM取得へ切り替えます。",
            flush=True,
        )

        odds_rows, odds_logs = (
            fetch_all_trifecta_odds_browser(
                racecard_url
            )
        )

        for log in odds_logs:
            print(
                f"[odds-dom] {log}",
                flush=True,
            )

        complete, complete_message = (
            validate_complete_odds(
                riders,
                odds_rows,
            )
        )

    if not complete:
        print(
            "[odds] オッズ完全性NG: "
            f"{complete_message} "
            "不完全なオッズは破棄し、"
            "オッズ非依存AI用として"
            "収集を継続します。",
            flush=True,
        )
        odds_rows = []

    dom_lineup_groups, lineup_logs = (
        fetch_lineup_browser(
            racecard_url,
            rider_numbers,
        )
    )

    for log in lineup_logs:
        print(
            f"[lineup] {log}",
            flush=True,
        )

    (
        comment_lineup_groups,
        comment_lineup_logs,
    ) = infer_lineup_from_comments(
        riders
    )
    (
        lineup_groups,
        lineup_metadata,
        selection_logs,
    ) = select_authoritative_lineup(
        dom_lineup_groups,
        comment_lineup_groups,
        rider_numbers,
    )

    for log in (
        comment_lineup_logs
        + selection_logs
    ):
        print(
            f"[lineup] {log}",
            flush=True,
        )

    riders = [
        {
            **rider,
            **lineup_metadata,
        }
        for rider in riders
    ]

    lineup_ok, lineup_message = (
        _validate_lineup(
            lineup_groups,
            rider_numbers,
        )
    )

    if not lineup_ok:
        raise RuntimeError(
            lineup_message
        )

    return (
        riders,
        odds_rows,
        lineup_groups,
        complete,
    )


def _process_entry(
    entry: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    detail = _base_detail(entry)
    existing = get_race_by_identity(
        race_date=detail["race_date"],
        venue=detail["venue"],
        race_number=detail["race_number"],
    )

    if existing is not None:
        update_race_urls_by_identity(
            race_date=detail["race_date"],
            venue=detail["venue"],
            race_number=detail["race_number"],
            race_url=detail["racecard_url"],
            result_url=detail["result_url"],
        )

        race_id = str(
            existing["race_id"]
        )
        detail["race_id"] = race_id
        learning_complete, _ = (
            race_has_complete_learning_data(
                race_id
            )
        )
        needs_enrichment = not (
            race_has_enriched_learning_features(
                race_id
            )
        )

        if learning_complete:
            detail["data_scope"] = "full"

        if (
            learning_complete
            and not needs_enrichment
            and str(
                existing.get(
                    "result_status",
                    "",
                )
            )
            == "確定"
        ):
            detail["status"] = "already_saved"
            detail["message"] = (
                "完全データ・結果とも登録済みです。"
            )
            return "success", detail

    else:
        race_id = ""
        learning_complete = False
        needs_enrichment = True

    riders: list[dict[str, Any]] = []
    odds_rows: list[dict[str, Any]] = []
    lineup_groups: list[list[int]] = []
    snapshot_odds_complete = (
        learning_complete
    )

    if learning_complete and not needs_enrichment:
        valid_car_numbers = (
            get_race_car_numbers(
                race_id
            )
        )
    else:
        (
            riders,
            odds_rows,
            lineup_groups,
            snapshot_odds_complete,
        ) = _collect_learning_snapshot(
            entry
        )
        valid_car_numbers = sorted(
            int(rider["車番"])
            for rider in riders
        )

    result, result_logs = (
        fetch_race_result(
            race_url=detail["result_url"],
            valid_car_numbers=(
                valid_car_numbers
            ),
        )
    )

    for log in result_logs:
        print(
            f"[result] {log}",
            flush=True,
        )

    result_status = str(
        result.get("status", "error")
    )

    if not result.get("success"):
        detail["status"] = result_status
        detail["message"] = str(
            result.get(
                "message",
                "結果を取得できませんでした。",
            )
        )
        return "failure", detail

    if (
        not learning_complete
        or needs_enrichment
    ):
        snapshot_arguments = {
            "race_date": detail["race_date"],
            "venue": detail["venue"],
            "race_number": detail[
                "race_number"
            ],
            "race_url": detail["racecard_url"],
            "race_title": (
                f"{detail['venue']} "
                f"{detail['race_number']}R"
            ),
            "riders": riders,
            "lineup_groups": lineup_groups,
        }

        if snapshot_odds_complete:
            race_id = save_race_snapshot(
                **snapshot_arguments,
                odds_rows=odds_rows,
                odds_complete=True,
            )
            detail["data_scope"] = "full"
        else:
            race_id = (
                save_independent_race_snapshot(
                    **snapshot_arguments,
                )
            )
            detail["data_scope"] = (
                "full"
                if learning_complete
                else "independent"
            )

        detail["race_id"] = race_id
        update_race_urls_by_identity(
            race_date=detail["race_date"],
            venue=detail["venue"],
            race_number=detail["race_number"],
            race_url=detail["racecard_url"],
            result_url=detail["result_url"],
        )

    if result_status == "settled":
        finish_order = [
            int(value)
            for value in result[
                "finish_order"
            ]
        ]
        payout = int(
            result["payout_per_100"]
        )

        save_race_result(
            race_id=race_id,
            first_place=finish_order[0],
            second_place=finish_order[1],
            third_place=finish_order[2],
            payout_per_100=payout,
            result_url=detail["result_url"],
            raw_result=result,
        )

        if (
            detail.get("data_scope")
            == "independent"
        ):
            detail["status"] = (
                "saved_independent"
            )
            detail["message"] = (
                "オッズが非表示のため、"
                "オッズ非依存AI用データと"
                "結果を保存しました。"
            )
        else:
            detail["status"] = "saved"
            detail["message"] = (
                "学習データと結果を"
                "保存しました。"
            )

        detail["winning_combination"] = (
            str(
                result[
                    "winning_combination"
                ]
            )
        )
        detail["payout_per_100"] = payout
        return "success", detail

    if result_status in (
        "review",
        "unsettled",
    ):
        reasons = [
            str(value)
            for value in result.get(
                "review_reasons",
                [],
            )
        ]

        if result_status == "unsettled":
            reasons.append(
                "過去日ですが結果が未確定です"
            )

        reason = "、".join(reasons)

        save_race_review(
            race_id=race_id,
            reason=reason,
            result_url=detail["result_url"],
            raw_result=result,
        )

        detail["status"] = "review"
        detail["message"] = reason

        if (
            detail.get("data_scope")
            == "independent"
        ):
            detail["message"] += (
                "（オッズ非依存AI用データ"
                "として保存）"
            )

        return "review", detail

    detail["status"] = result_status
    detail["message"] = str(
        result.get(
            "message",
            "結果状態を判定できませんでした。",
        )
    )
    return "failure", detail


def run_job(
    job_directory: Path,
) -> int:
    request_path = (
        job_directory
        / "request.json"
    )
    request = json.loads(
        request_path.read_text(
            encoding="utf-8"
        )
    )
    start_date = date.fromisoformat(
        str(request["start_date"])
    )
    end_date = date.fromisoformat(
        str(request["end_date"])
    )
    maximum_races = int(
        request["maximum_races"]
    )

    if start_date > end_date:
        raise ValueError(
            "開始日は終了日以前にしてください。"
        )

    if end_date >= date.today():
        raise ValueError(
            "終了日は昨日以前にしてください。"
        )

    progress = Progress(
        job_directory,
        request,
    )
    entries_by_url: dict[
        str,
        dict[str, Any],
    ] = {}

    try:
        for selected_date in _date_range(
            start_date,
            end_date,
        ):
            progress.set(
                phase="discovery",
                message=(
                    f"{selected_date.isoformat()}の"
                    "結果一覧を確認しています。"
                ),
            )

            try:
                entries, logs = (
                    fetch_result_catalog(
                        selected_date
                    )
                )

                for log in logs:
                    print(
                        f"[catalog] {log}",
                        flush=True,
                    )

                for entry in entries:
                    entries_by_url[
                        str(
                            entry["result_url"]
                        )
                    ] = entry

                progress.set(
                    discovered=len(
                        entries_by_url
                    )
                )

            except Exception as exc:
                progress.append(
                    "failure",
                    {
                        "race_date": (
                            selected_date
                            .isoformat()
                        ),
                        "venue": "",
                        "race_number": 0,
                        "status": (
                            "catalog_error"
                        ),
                        "message": (
                            f"{type(exc).__name__}: "
                            f"{exc}"
                        ),
                    },
                )

        entries = sorted(
            entries_by_url.values(),
            key=lambda item: (
                str(item["race_date"]),
                str(item["venue"]),
                int(item["race_number"]),
            ),
        )[:maximum_races]

        progress.set(
            phase="collecting",
            total=len(entries),
            message=(
                f"{len(entries)}レースを"
                "順番に取得します。"
            ),
        )

        for index, entry in enumerate(
            entries,
            start=1,
        ):
            progress.set(
                phase="collecting",
                message=(
                    f"{entry['race_date']} "
                    f"{entry['venue']} "
                    f"{entry['race_number']}R "
                    f"({index}/{len(entries)})"
                ),
            )
            print(
                "[race] "
                f"{entry['race_date']} "
                f"{entry['venue']} "
                f"{entry['race_number']}R",
                flush=True,
            )

            try:
                category, detail = (
                    _process_entry(entry)
                )
            except Exception as exc:
                category = "failure"
                detail = {
                    **_base_detail(entry),
                    "status": "error",
                    "message": (
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
                }
                traceback.print_exc()

            progress.append(
                category,
                detail,
            )
            progress.set(
                processed=index,
            )

        progress.set(
            status="completed",
            phase="completed",
            message=(
                "過去レース一括インポートが"
                "完了しました。"
            ),
            finished_at=(
                datetime.now().isoformat(
                    timespec="seconds"
                )
            ),
        )
        return 0

    except Exception as exc:
        traceback.print_exc()
        progress.set(
            status="failed",
            phase="failed",
            message=(
                f"{type(exc).__name__}: {exc}"
            ),
            finished_at=(
                datetime.now().isoformat(
                    timespec="seconds"
                )
            ),
        )
        return 1


def run_self_test() -> int:
    sample_html = """
    <a href="/keirin/toyohashi/raceresult/2026072545/4/1">1R</a>
    <a href="/keirin/toyohashi/raceresult/2026072545/4/1">duplicate</a>
    <a href="/keirin/toride/raceresult/2026072623/3/2">2R</a>
    """
    entries = parse_result_catalog_html(
        sample_html,
        "2026-07-28",
    )
    lineup_ok, _ = _validate_lineup(
        [[1, 2], [3]],
        [1, 2, 3],
    )

    if len(entries) != 2 or not lineup_ok:
        print(
            json.dumps(
                {
                    "success": False,
                    "entries": len(entries),
                    "lineup_ok": lineup_ok,
                },
                ensure_ascii=False,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "success": True,
                "entries": len(entries),
                "lineup_ok": lineup_ok,
            },
            ensure_ascii=False,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--job-dir",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
    )
    arguments = parser.parse_args()

    if arguments.self_test:
        return run_self_test()

    if not arguments.job_dir:
        parser.error(
            "--job-dirが必要です。"
        )

    return run_job(
        Path(arguments.job_dir).resolve()
    )


if __name__ == "__main__":
    raise SystemExit(main())
