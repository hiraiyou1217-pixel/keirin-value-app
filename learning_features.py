from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from learning_database import DATABASE_PATH


AI_MARK_SCORES = {
    "本命": 4.0,
    "対抗": 3.0,
    "単穴": 2.0,
    "連下": 1.0,
    "": 0.0,
}


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    if value in (None, ""):
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    if value in (None, ""):
        return default

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _style_values(style: str) -> tuple[int, int, int]:
    normalized = str(style).strip()

    return (
        int(normalized == "逃"),
        int(normalized == "両"),
        int(normalized == "追"),
    )


def _line_relation(
    first: dict[str, Any],
    second: dict[str, Any],
    third: dict[str, Any],
) -> dict[str, int]:
    first_line = first.get("lineup_number")
    second_line = second.get("lineup_number")
    third_line = third.get("lineup_number")

    first_position = first.get("lineup_position")
    second_position = second.get("lineup_position")
    third_position = third.get("lineup_position")

    same_12 = int(
        first_line is not None
        and first_line == second_line
    )

    same_23 = int(
        second_line is not None
        and second_line == third_line
    )

    same_all = int(
        first_line is not None
        and first_line == second_line
        and second_line == third_line
    )

    exact_line_order = int(
        same_all
        and second_position == first_position + 1
        and third_position == second_position + 1
    )

    leader_then_second = int(
        same_12
        and first_position == 0
        and second_position == 1
    )

    second_over_leader = int(
        same_12
        and first_position == 1
        and second_position == 0
    )

    return {
        "same_line_12": same_12,
        "same_line_23": same_23,
        "same_line_all": same_all,
        "exact_line_order": exact_line_order,
        "leader_then_second": leader_then_second,
        "second_over_leader": second_over_leader,
    }


def _rider_features(
    prefix: str,
    rider: dict[str, Any],
) -> dict[str, float]:
    style_escape, style_allround, style_chase = (
        _style_values(rider.get("style", ""))
    )

    ai_mark = str(
        rider.get("ai_mark", "")
    ).strip()

    return {
        f"{prefix}_competition_score": _safe_float(
            rider.get("competition_score")
        ),
        f"{prefix}_ai_mark_score": AI_MARK_SCORES.get(
            ai_mark,
            0.0,
        ),
        f"{prefix}_s_count": _safe_float(
            rider.get("s_count")
        ),
        f"{prefix}_h_count": _safe_float(
            rider.get("h_count")
        ),
        f"{prefix}_b_count": _safe_float(
            rider.get("b_count")
        ),
        f"{prefix}_win_rate": _safe_float(
            rider.get("win_rate")
        ),
        f"{prefix}_quinella_rate": _safe_float(
            rider.get("quinella_rate")
        ),
        f"{prefix}_trio_rate": _safe_float(
            rider.get("trio_rate")
        ),
        f"{prefix}_style_escape": style_escape,
        f"{prefix}_style_allround": style_allround,
        f"{prefix}_style_chase": style_chase,
        f"{prefix}_line_position": _safe_float(
            rider.get("lineup_position"),
            -1.0,
        ),
        f"{prefix}_line_length": _safe_float(
            rider.get("lineup_length"),
            1.0,
        ),
    }


def build_training_dataframe(
    database_path: Path = DATABASE_PATH,
) -> pd.DataFrame:
    if not database_path.exists():
        return pd.DataFrame()

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row

    try:
        races = connection.execute(
            """
            SELECT *
            FROM races
            WHERE
                result_status = '確定'
                AND odds_complete = 1
                AND winning_combination IS NOT NULL
            ORDER BY race_date, venue, race_number
            """
        ).fetchall()

        output_rows: list[dict[str, Any]] = []

        for race_row in races:
            race = dict(race_row)
            race_id = str(race["race_id"])

            rider_rows = connection.execute(
                """
                SELECT *
                FROM riders
                WHERE race_id = ?
                """,
                (race_id,),
            ).fetchall()

            riders = {
                int(row["car_number"]): dict(row)
                for row in rider_rows
            }

            odds_rows = connection.execute(
                """
                SELECT *
                FROM odds
                WHERE race_id = ?
                ORDER BY popularity
                """,
                (race_id,),
            ).fetchall()

            if len(riders) < 3 or not odds_rows:
                continue

            scores = [
                _safe_float(
                    rider.get("competition_score")
                )
                for rider in riders.values()
            ]

            race_score_mean = float(np.mean(scores))
            race_score_std = float(np.std(scores))

            for odds_row in odds_rows:
                odds_item = dict(odds_row)
                combination = str(
                    odds_item["combination"]
                )

                parts = combination.split("-")

                if len(parts) != 3:
                    continue

                try:
                    first, second, third = map(
                        int,
                        parts,
                    )
                except ValueError:
                    continue

                if not all(
                    number in riders
                    for number in (
                        first,
                        second,
                        third,
                    )
                ):
                    continue

                first_rider = riders[first]
                second_rider = riders[second]
                third_rider = riders[third]

                row: dict[str, Any] = {
                    "race_id": race_id,
                    "race_date": race["race_date"],
                    "venue": race["venue"],
                    "race_number": int(
                        race["race_number"]
                    ),
                    "combination": combination,
                    "first_car": first,
                    "second_car": second,
                    "third_car": third,
                    "popularity": _safe_int(
                        odds_item.get("popularity"),
                        9999,
                    ),
                    "odds": _safe_float(
                        odds_item.get("odds")
                    ),
                    "log_odds": float(
                        np.log1p(
                            _safe_float(
                                odds_item.get("odds")
                            )
                        )
                    ),
                    "market_probability_raw": (
                        1.0
                        / _safe_float(
                            odds_item.get("odds"),
                            9999.0,
                        )
                    ),
                    "race_score_mean": race_score_mean,
                    "race_score_std": race_score_std,
                    "target": int(
                        combination
                        == race["winning_combination"]
                    ),
                }

                row.update(
                    _rider_features(
                        "first",
                        first_rider,
                    )
                )
                row.update(
                    _rider_features(
                        "second",
                        second_rider,
                    )
                )
                row.update(
                    _rider_features(
                        "third",
                        third_rider,
                    )
                )

                row.update(
                    _line_relation(
                        first_rider,
                        second_rider,
                        third_rider,
                    )
                )

                row["score_diff_12"] = (
                    row["first_competition_score"]
                    - row["second_competition_score"]
                )

                row["score_diff_13"] = (
                    row["first_competition_score"]
                    - row["third_competition_score"]
                )

                row["score_sum"] = (
                    row["first_competition_score"]
                    + row["second_competition_score"]
                    + row["third_competition_score"]
                )

                row["ai_mark_sum"] = (
                    row["first_ai_mark_score"]
                    + row["second_ai_mark_score"]
                    + row["third_ai_mark_score"]
                )

                output_rows.append(row)

        return pd.DataFrame(output_rows)

    finally:
        connection.close()


IDENTIFIER_COLUMNS = [
    "race_id",
    "race_date",
    "venue",
    "combination",
]

TARGET_COLUMN = "target"


def get_feature_columns(
    dataframe: pd.DataFrame,
) -> list[str]:
    excluded = set(
        IDENTIFIER_COLUMNS
        + [TARGET_COLUMN]
    )

    return [
        column
        for column in dataframe.columns
        if column not in excluded
        and pd.api.types.is_numeric_dtype(
            dataframe[column]
        )
    ]


def build_current_race_dataframe(
    *,
    odds_rows: list[dict[str, Any]],
    riders: list[dict[str, Any]],
    lineup_groups: list[list[int]],
    race_id: str = "current_race",
    race_date: str = "",
    venue: str = "",
    race_number: int = 0,
) -> pd.DataFrame:
    """
    現在取得中のレースから、学習時と同じ形式の
    3連単特徴量データを作成する。
    """
    if not odds_rows or not riders:
        return pd.DataFrame()

    lineup_metadata: dict[int, dict[str, int]] = {}

    for lineup_number, group in enumerate(
        lineup_groups,
        start=1,
    ):
        for lineup_position, car_number in enumerate(group):
            lineup_metadata[int(car_number)] = {
                "lineup_number": lineup_number,
                "lineup_position": lineup_position,
                "lineup_length": len(group),
            }

    normalized_riders: dict[int, dict[str, Any]] = {}

    for rider in riders:
        car_number = _safe_int(
            rider.get("車番"),
            0,
        )

        if car_number <= 0:
            continue

        lineup = lineup_metadata.get(
            car_number,
            {
                "lineup_number": None,
                "lineup_position": None,
                "lineup_length": 1,
            },
        )

        normalized_riders[car_number] = {
            "car_number": car_number,
            "rider_name": rider.get(
                "選手名",
                "",
            ),
            "ai_mark": rider.get(
                "AI印",
                "",
            ),
            "competition_score": _safe_float(
                rider.get("競走得点")
            ),
            "style": rider.get(
                "脚質",
                "",
            ),
            "s_count": _safe_int(
                rider.get("S")
            ),
            "h_count": _safe_int(
                rider.get("H")
            ),
            "b_count": _safe_int(
                rider.get("B")
            ),
            "win_rate": _safe_float(
                rider.get("勝率")
            ),
            "quinella_rate": _safe_float(
                rider.get("2連対率")
            ),
            "trio_rate": _safe_float(
                rider.get("3連対率")
            ),
            "comment": rider.get(
                "コメント",
                "",
            ),
            **lineup,
        }

    if len(normalized_riders) < 3:
        return pd.DataFrame()

    competition_scores = [
        _safe_float(
            rider.get("competition_score")
        )
        for rider in normalized_riders.values()
    ]

    race_score_mean = float(
        np.mean(competition_scores)
    )

    race_score_std = float(
        np.std(competition_scores)
    )

    output_rows: list[dict[str, Any]] = []

    for odds_item in odds_rows:
        combination = str(
            odds_item.get("組番", "")
        ).strip()

        parts = combination.split("-")

        if len(parts) != 3:
            continue

        try:
            first, second, third = map(
                int,
                parts,
            )
        except ValueError:
            continue

        if len({first, second, third}) != 3:
            continue

        if not all(
            number in normalized_riders
            for number in (
                first,
                second,
                third,
            )
        ):
            continue

        odds_value = _safe_float(
            odds_item.get("オッズ")
        )

        if odds_value <= 1:
            continue

        first_rider = normalized_riders[first]
        second_rider = normalized_riders[second]
        third_rider = normalized_riders[third]

        row: dict[str, Any] = {
            "race_id": race_id,
            "race_date": race_date,
            "venue": venue,
            "race_number": int(race_number),
            "combination": combination,
            "first_car": first,
            "second_car": second,
            "third_car": third,
            "popularity": _safe_int(
                odds_item.get("人気"),
                9999,
            ),
            "odds": odds_value,
            "log_odds": float(
                np.log1p(odds_value)
            ),
            "market_probability_raw": (
                1.0 / odds_value
            ),
            "race_score_mean": race_score_mean,
            "race_score_std": race_score_std,
            "target": 0,
        }

        row.update(
            _rider_features(
                "first",
                first_rider,
            )
        )

        row.update(
            _rider_features(
                "second",
                second_rider,
            )
        )

        row.update(
            _rider_features(
                "third",
                third_rider,
            )
        )

        row.update(
            _line_relation(
                first_rider,
                second_rider,
                third_rider,
            )
        )

        row["score_diff_12"] = (
            row["first_competition_score"]
            - row["second_competition_score"]
        )

        row["score_diff_13"] = (
            row["first_competition_score"]
            - row["third_competition_score"]
        )

        row["score_sum"] = (
            row["first_competition_score"]
            + row["second_competition_score"]
            + row["third_competition_score"]
        )

        row["ai_mark_sum"] = (
            row["first_ai_mark_score"]
            + row["second_ai_mark_score"]
            + row["third_ai_mark_score"]
        )

        output_rows.append(row)

    return pd.DataFrame(output_rows)
