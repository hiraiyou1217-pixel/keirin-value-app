from __future__ import annotations

from typing import Any

from learning_database import (
    get_race_car_numbers,
    get_unfinished_races,
    save_race_review,
    save_race_result,
)
from result_browser import (
    fetch_race_result,
)


def import_unfinished_results(
    *,
    maximum_races: int = 50,
) -> dict[str, Any]:
    unfinished = get_unfinished_races(
        limit=int(maximum_races)
    )

    summary = {
        "checked": 0,
        "registered": 0,
        "unsettled": 0,
        "review": 0,
        "failed": 0,
        "details": [],
    }

    for race in unfinished:
        race_id = str(
            race["race_id"]
        )

        valid_car_numbers = (
            get_race_car_numbers(
                race_id
            )
        )

        detail = {
            "race_id": race_id,
            "race_date": race[
                "race_date"
            ],
            "venue": race["venue"],
            "race_number": race[
                "race_number"
            ],
            "status": "",
            "message": "",
            "winning_combination": "",
            "payout_per_100": None,
            "logs": [],
        }

        summary["checked"] += 1

        saved_race_url = str(
            race.get(
                "race_url",
                "",
            )
            or ""
        ).strip()

        if not saved_race_url:
            detail["status"] = "url_missing"
            detail["message"] = (
                "出走表URLが未登録です。"
                "学習データ収集ページから"
                "URLを登録してください。"
            )

            summary["failed"] += 1
            summary["details"].append(
                detail
            )
            continue

        if not valid_car_numbers:
            detail["status"] = "failed"
            detail["message"] = (
                "保存済み選手データがありません。"
            )

            summary["failed"] += 1
            summary["details"].append(
                detail
            )
            continue

        result, logs = fetch_race_result(
            race_url=saved_race_url,
            valid_car_numbers=(
                valid_car_numbers
            ),
        )

        detail["logs"] = logs
        detail["status"] = str(
            result.get(
                "status",
                "error",
            )
        )
        detail["message"] = str(
            result.get(
                "message",
                "",
            )
        )

        if (
            result.get("success")
            and result.get("status")
            == "settled"
        ):
            finish_order = result[
                "finish_order"
            ]

            save_race_result(
                race_id=race_id,
                first_place=int(
                    finish_order[0]
                ),
                second_place=int(
                    finish_order[1]
                ),
                third_place=int(
                    finish_order[2]
                ),
                payout_per_100=int(
                    result[
                        "payout_per_100"
                    ]
                ),
                result_url=str(
                    result.get(
                        "result_url",
                        "",
                    )
                ),
                raw_result=result,
            )

            detail[
                "winning_combination"
            ] = result[
                "winning_combination"
            ]

            detail[
                "payout_per_100"
            ] = result[
                "payout_per_100"
            ]

            summary["registered"] += 1

        elif (
            result.get("success")
            and result.get("status")
            == "review"
        ):
            review_reason = "、".join(
                str(value)
                for value in result.get(
                    "review_reasons",
                    [],
                )
            )

            save_race_review(
                race_id=race_id,
                reason=review_reason,
                result_url=str(
                    result.get(
                        "result_url",
                        "",
                    )
                ),
                raw_result=result,
            )

            summary["review"] += 1

        elif (
            result.get("success")
            and result.get("status")
            == "unsettled"
        ):
            summary["unsettled"] += 1

        else:
            summary["failed"] += 1

        summary["details"].append(
            detail
        )

    return summary
