from __future__ import annotations

import itertools
import re
import sqlite3
from datetime import (
    date,
    datetime,
    timedelta,
    timezone,
)
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from learning_database import DATABASE_PATH
from race_metadata import (
    class_ordinal,
    get_venue_characteristics,
    grade_ordinal,
    same_region_feature,
    stage_features,
    weather_features,
    wind_direction_features,
)


IDENTIFIER_COLUMNS = [
    "race_id",
    "race_date",
    "venue",
    "combination",
]
TARGET_COLUMN = "target"
FORBIDDEN_FEATURE_WORDS = (
    "odds",
    "popularity",
    "market",
    "ai_mark",
    "payout",
)

COMMENT_KEYWORDS = {
    "self": ("自力",),
    "leading": ("先行", "主導権"),
    "sprint": ("捲", "まく"),
    "mark": ("番手", "マーク"),
    "solo": ("単騎",),
    "flexible": ("自在", "何でも"),
    "forward": ("前々", "前へ"),
    "chase": ("追込", "追い込み"),
}

JAPAN_TIME_ZONE = timezone(
    timedelta(hours=9),
    name="JST",
)


def resolve_independent_training_cutoff_date(
    value: date | datetime | str | None = None,
) -> str:
    if value is None:
        japan_today = datetime.now(
            JAPAN_TIME_ZONE
        ).date()

        return (
            japan_today
            - timedelta(days=1)
        ).isoformat()

    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    text = str(value).strip()

    try:
        return date.fromisoformat(
            text[:10]
        ).isoformat()
    except ValueError as exc:
        raise ValueError(
            "独立AIの学習締切日は"
            "YYYY-MM-DD形式で指定してください。"
        ) from exc


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


def _style_features(
    value: Any,
) -> dict[str, float]:
    style = str(value or "").strip()

    return {
        "style_escape": float(style == "逃"),
        "style_allround": float(style == "両"),
        "style_chase": float(style == "追"),
    }


def _comment_features(
    value: Any,
) -> dict[str, float]:
    comment = str(value or "").strip()
    output = {
        "comment_length": float(
            min(len(comment), 100)
        ),
    }

    for feature_name, keywords in (
        COMMENT_KEYWORDS.items()
    ):
        output[
            f"comment_{feature_name}"
        ] = float(
            any(
                keyword in comment
                for keyword in keywords
            )
        )

    return output


def _normalize_stored_rider(
    row: sqlite3.Row,
) -> dict[str, Any]:
    rider = dict(row)

    return {
        "car_number": _safe_int(
            rider.get("car_number")
        ),
        "rider_name": str(
            rider.get("rider_name") or ""
        ),
        "cyclist_id": str(
            rider.get("cyclist_id") or ""
        ),
        "home_prefecture": str(
            rider.get(
                "home_prefecture"
            )
            or ""
        ),
        "class_name": str(
            rider.get("class_name") or ""
        ),
        "age": _safe_int(
            rider.get("age")
        ),
        "generation": _safe_int(
            rider.get("generation")
        ),
        "competition_score": _safe_float(
            rider.get("competition_score")
        ),
        "style": str(
            rider.get("style") or ""
        ),
        "s_count": _safe_float(
            rider.get("s_count")
        ),
        "h_count": _safe_float(
            rider.get("h_count")
        ),
        "b_count": _safe_float(
            rider.get("b_count")
        ),
        "win_rate": _safe_float(
            rider.get("win_rate")
        ),
        "quinella_rate": _safe_float(
            rider.get("quinella_rate")
        ),
        "trio_rate": _safe_float(
            rider.get("trio_rate")
        ),
        "comment": str(
            rider.get("comment") or ""
        ),
        "lineup_number": rider.get(
            "lineup_number"
        ),
        "lineup_position": rider.get(
            "lineup_position"
        ),
        "lineup_length": _safe_int(
            rider.get("lineup_length"),
            1,
        ),
    }


def _lineup_metadata(
    lineup_groups: list[list[int]],
) -> dict[int, dict[str, int]]:
    output: dict[int, dict[str, int]] = {}

    for lineup_number, group in enumerate(
        lineup_groups,
        start=1,
    ):
        for lineup_position, car_number in (
            enumerate(group)
        ):
            output[int(car_number)] = {
                "lineup_number": lineup_number,
                "lineup_position": lineup_position,
                "lineup_length": len(group),
            }

    return output


def _normalize_current_rider(
    rider: dict[str, Any],
    lineup: dict[str, int] | None,
) -> dict[str, Any]:
    lineup = lineup or {}

    return {
        "car_number": _safe_int(
            rider.get("車番")
        ),
        "rider_name": str(
            rider.get("選手名") or ""
        ),
        "cyclist_id": str(
            rider.get("選手ID") or ""
        ),
        "home_prefecture": str(
            rider.get("府県") or ""
        ),
        "class_name": str(
            rider.get("級班") or ""
        ),
        "age": _safe_int(
            rider.get("年齢")
        ),
        "generation": _safe_int(
            rider.get("期別")
        ),
        "competition_score": _safe_float(
            rider.get("競走得点")
        ),
        "style": str(
            rider.get("脚質") or ""
        ),
        "s_count": _safe_float(
            rider.get("S")
        ),
        "h_count": _safe_float(
            rider.get("H")
        ),
        "b_count": _safe_float(
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
        "comment": str(
            rider.get("コメント") or ""
        ),
        "lineup_number": lineup.get(
            "lineup_number"
        ),
        "lineup_position": lineup.get(
            "lineup_position"
        ),
        "lineup_length": _safe_int(
            lineup.get("lineup_length"),
            1,
        ),
    }


def _history_keys(
    rider: dict[str, Any],
) -> list[str]:
    keys: list[str] = []
    cyclist_id = str(
        rider.get("cyclist_id") or ""
    ).strip()
    rider_name = re.sub(
        r"\s+",
        "",
        str(
            rider.get("rider_name")
            or ""
        ),
    )

    if cyclist_id:
        keys.append(
            f"id:{cyclist_id}"
        )

    if rider_name:
        keys.append(
            f"name:{rider_name}"
        )

    return keys


def _rider_history(
    history: dict[
        str,
        list[dict[str, Any]],
    ],
    rider: dict[str, Any],
) -> list[dict[str, Any]]:
    observations: dict[
        str,
        dict[str, Any],
    ] = {}

    for key in _history_keys(rider):
        for observation in history.get(
            key,
            [],
        ):
            observations[
                str(
                    observation[
                        "race_id"
                    ]
                )
            ] = observation

    return sorted(
        observations.values(),
        key=lambda observation: (
            str(
                observation[
                    "race_date"
                ]
            ),
            str(
                observation[
                    "race_id"
                ]
            ),
        ),
    )


def _append_rider_history(
    history: dict[
        str,
        list[dict[str, Any]],
    ],
    rider: dict[str, Any],
    observation: dict[str, Any],
) -> None:
    for key in _history_keys(rider):
        history.setdefault(
            key,
            [],
        ).append(observation)


def _recent_form_features(
    observations: list[
        dict[str, Any]
    ],
    *,
    target_date: str,
    venue: str,
) -> dict[str, float]:
    prior = [
        observation
        for observation in observations
        if str(
            observation["race_date"]
        )
        < str(target_date)
    ]
    output: dict[str, float] = {}

    for window in (
        5,
        10,
    ):
        recent = prior[-window:]
        starts = len(recent)
        output[
            f"recent_starts_{window}"
        ] = float(starts)

        for metric in (
            "win",
            "top2",
            "top3",
        ):
            output[
                f"recent_{metric}_rate_{window}"
            ] = (
                sum(
                    float(
                        observation[
                            metric
                        ]
                    )
                    for observation in recent
                )
                / starts
                if starts
                else 0.0
            )

        output[
            f"recent_form_points_{window}"
        ] = (
            sum(
                float(
                    observation[
                        "form_points"
                    ]
                )
                for observation in recent
            )
            / starts
            if starts
            else 0.0
        )
        output[
            f"recent_score_mean_{window}"
        ] = (
            sum(
                float(
                    observation[
                        "competition_score"
                    ]
                )
                for observation in recent
            )
            / starts
            if starts
            else 0.0
        )

    same_venue = [
        observation
        for observation in prior[-20:]
        if str(
            observation["venue"]
        )
        == str(venue)
    ]
    output[
        "recent_same_venue_starts"
    ] = float(len(same_venue))
    output[
        "recent_same_venue_top3_rate"
    ] = (
        sum(
            float(
                observation["top3"]
            )
            for observation in same_venue
        )
        / len(same_venue)
        if same_venue
        else 0.0
    )

    if prior:
        try:
            target = date.fromisoformat(
                str(target_date)[:10]
            )
            latest = date.fromisoformat(
                str(
                    prior[-1][
                        "race_date"
                    ]
                )[:10]
            )
            days_since = max(
                0,
                (target - latest).days,
            )
        except ValueError:
            days_since = 0
    else:
        days_since = 0

    output["days_since_last_race"] = float(
        min(days_since, 365)
    )
    output["has_prior_race"] = float(
        bool(prior)
    )

    return output


def _normalize_race_conditions(
    source: dict[str, Any] | None,
) -> dict[str, Any]:
    values = source or {}

    return {
        "race_grade": str(
            values.get(
                "race_grade",
                values.get(
                    "レースグレード",
                    "",
                ),
            )
            or ""
        ),
        "race_stage": str(
            values.get(
                "race_stage",
                values.get(
                    "レース区分",
                    "",
                ),
            )
            or ""
        ),
        "race_class": str(
            values.get(
                "race_class",
                values.get(
                    "レース級別",
                    "",
                ),
            )
            or ""
        ),
        "day_number": _safe_int(
            values.get(
                "day_number",
                values.get("開催日目"),
            )
        ),
        "scheduled_start_time": str(
            values.get(
                "scheduled_start_time",
                values.get(
                    "発走時刻",
                    "",
                ),
            )
            or ""
        ),
        "race_distance_m": _safe_float(
            values.get(
                "race_distance_m",
                values.get("距離m"),
            )
        ),
        "lap_count": _safe_float(
            values.get(
                "lap_count",
                values.get("周回数"),
            )
        ),
        "weather": str(
            values.get(
                "weather",
                values.get("天候", ""),
            )
            or ""
        ),
        "temperature_c": _safe_float(
            values.get(
                "temperature_c",
                values.get("気温C"),
            )
        ),
        "wind_direction": str(
            values.get(
                "wind_direction",
                values.get("風向", ""),
            )
            or ""
        ),
        "wind_speed_mps": _safe_float(
            values.get(
                "wind_speed_mps",
                values.get("風速mps"),
            )
        ),
        "lineup_source": str(
            values.get(
                "lineup_source",
                values.get(
                    "並び取得方式",
                    "",
                ),
            )
            or ""
        ),
        "lineup_confidence": _safe_float(
            values.get(
                "lineup_confidence",
                values.get(
                    "並び信頼度",
                ),
            )
        ),
    }


def _race_condition_features(
    *,
    venue: str,
    conditions: dict[str, Any],
) -> dict[str, float]:
    venue_values = (
        get_venue_characteristics(
            venue
        )
    )
    start_time = str(
        conditions.get(
            "scheduled_start_time"
        )
        or ""
    )

    try:
        start_hour = (
            int(start_time.split(":")[0])
            + int(
                start_time.split(":")[1]
            )
            / 60.0
        )
        start_known = 1.0
    except (
        IndexError,
        TypeError,
        ValueError,
    ):
        start_hour = 0.0
        start_known = 0.0

    output = {
        "bank_length_m": float(
            venue_values[
                "bank_length_m"
            ]
        ),
        "home_straight_m": float(
            venue_values[
                "home_straight_m"
            ]
        ),
        "max_cant_degrees": float(
            venue_values[
                "max_cant_degrees"
            ]
        ),
        "venue_characteristics_known": float(
            venue_values[
                "venue_characteristics_known"
            ]
        ),
        "race_grade_ordinal": grade_ordinal(
            conditions.get("race_grade")
        ),
        "race_day_number": _safe_float(
            conditions.get("day_number")
        ),
        "scheduled_start_hour": start_hour,
        "scheduled_start_known": start_known,
        "race_distance_m": _safe_float(
            conditions.get(
                "race_distance_m"
            )
        ),
        "lap_count": _safe_float(
            conditions.get("lap_count")
        ),
        "temperature_c": _safe_float(
            conditions.get(
                "temperature_c"
            )
        ),
        "wind_speed_mps": _safe_float(
            conditions.get(
                "wind_speed_mps"
            )
        ),
        "lineup_confidence": _safe_float(
            conditions.get(
                "lineup_confidence"
            )
        ),
    }
    output.update(
        stage_features(
            conditions.get("race_stage")
        )
    )
    output.update(
        weather_features(
            conditions.get("weather")
        )
    )
    output.update(
        wind_direction_features(
            conditions.get(
                "wind_direction"
            )
        )
    )

    return output


def _rider_features(
    prefix: str,
    rider: dict[str, Any],
    race_score_mean: float,
    venue: str,
) -> dict[str, float]:
    competition_score = _safe_float(
        rider.get("competition_score")
    )
    output = {
        f"{prefix}_car_number": float(
            _safe_int(
                rider.get("car_number")
            )
        ),
        f"{prefix}_competition_score": (
            competition_score
        ),
        f"{prefix}_score_vs_race_mean": (
            competition_score
            - race_score_mean
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
        f"{prefix}_quinella_rate": (
            _safe_float(
                rider.get("quinella_rate")
            )
        ),
        f"{prefix}_trio_rate": _safe_float(
            rider.get("trio_rate")
        ),
        f"{prefix}_line_position": (
            _safe_float(
                rider.get(
                    "lineup_position"
                ),
                -1.0,
            )
        ),
        f"{prefix}_line_length": _safe_float(
            rider.get("lineup_length"),
            1.0,
        ),
        f"{prefix}_age": _safe_float(
            rider.get("age")
        ),
        f"{prefix}_generation": _safe_float(
            rider.get("generation")
        ),
        f"{prefix}_class_ordinal": (
            class_ordinal(
                rider.get("class_name")
            )
        ),
        f"{prefix}_profile_known": float(
            bool(
                rider.get("cyclist_id")
                or rider.get(
                    "home_prefecture"
                )
                or rider.get(
                    "class_name"
                )
            )
        ),
        f"{prefix}_same_region": (
            same_region_feature(
                rider.get(
                    "home_prefecture"
                ),
                venue,
            )
        ),
    }
    recent_features = dict(
        rider.get(
            "recent_features",
            {},
        )
        or {}
    )

    for name, value in (
        recent_features.items()
    ):
        output[
            f"{prefix}_{name}"
        ] = _safe_float(value)

    recent_starts = _safe_float(
        recent_features.get(
            "recent_starts_10"
        )
    )
    recent_score_mean = _safe_float(
        recent_features.get(
            "recent_score_mean_10"
        )
    )
    output[
        f"{prefix}_score_vs_recent_mean"
    ] = (
        competition_score
        - recent_score_mean
        if recent_starts > 0
        else 0.0
    )

    for name, value in _style_features(
        rider.get("style")
    ).items():
        output[f"{prefix}_{name}"] = value

    for name, value in _comment_features(
        rider.get("comment")
    ).items():
        output[f"{prefix}_{name}"] = value

    return output


def _line_relation_features(
    first: dict[str, Any],
    second: dict[str, Any],
    third: dict[str, Any],
) -> dict[str, float]:
    first_line = first.get("lineup_number")
    second_line = second.get("lineup_number")
    third_line = third.get("lineup_number")

    first_position = first.get(
        "lineup_position"
    )
    second_position = second.get(
        "lineup_position"
    )
    third_position = third.get(
        "lineup_position"
    )

    same_12 = (
        first_line is not None
        and first_line == second_line
    )
    same_23 = (
        second_line is not None
        and second_line == third_line
    )
    same_all = (
        same_12
        and second_line == third_line
    )
    positions_known = all(
        value is not None
        for value in (
            first_position,
            second_position,
            third_position,
        )
    )

    return {
        "same_line_12": float(same_12),
        "same_line_23": float(same_23),
        "same_line_all": float(same_all),
        "exact_line_order": float(
            same_all
            and positions_known
            and second_position
            == first_position + 1
            and third_position
            == second_position + 1
        ),
        "leader_then_second": float(
            same_12
            and first_position == 0
            and second_position == 1
        ),
        "second_over_leader": float(
            same_12
            and first_position == 1
            and second_position == 0
        ),
    }


def _candidate_row(
    *,
    race_id: str,
    race_date: str,
    venue: str,
    race_number: int,
    riders: dict[int, dict[str, Any]],
    race_conditions: dict[str, Any],
    combination: tuple[int, int, int],
    target: int,
) -> dict[str, Any]:
    first_number, second_number, third_number = (
        combination
    )
    first = riders[first_number]
    second = riders[second_number]
    third = riders[third_number]

    competition_scores = [
        _safe_float(
            rider.get("competition_score")
        )
        for rider in riders.values()
    ]
    race_score_mean = float(
        np.mean(competition_scores)
    )
    race_score_std = float(
        np.std(competition_scores)
    )

    row: dict[str, Any] = {
        "race_id": race_id,
        "race_date": race_date,
        "venue": venue,
        "race_number": int(race_number),
        "rider_count": len(riders),
        "combination": (
            f"{first_number}-"
            f"{second_number}-"
            f"{third_number}"
        ),
        "first_car": first_number,
        "second_car": second_number,
        "third_car": third_number,
        "race_score_mean": race_score_mean,
        "race_score_std": race_score_std,
        "target": int(target),
    }
    row.update(
        _race_condition_features(
            venue=venue,
            conditions=race_conditions,
        )
    )

    row.update(
        _rider_features(
            "first",
            first,
            race_score_mean,
            venue,
        )
    )
    row.update(
        _rider_features(
            "second",
            second,
            race_score_mean,
            venue,
        )
    )
    row.update(
        _rider_features(
            "third",
            third,
            race_score_mean,
            venue,
        )
    )
    row.update(
        _line_relation_features(
            first,
            second,
            third,
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
    row["score_diff_23"] = (
        row["second_competition_score"]
        - row["third_competition_score"]
    )
    row["score_sum"] = (
        row["first_competition_score"]
        + row["second_competition_score"]
        + row["third_competition_score"]
    )
    row["win_rate_sum"] = (
        row["first_win_rate"]
        + row["second_win_rate"]
        + row["third_win_rate"]
    )
    row["trio_rate_sum"] = (
        row["first_trio_rate"]
        + row["second_trio_rate"]
        + row["third_trio_rate"]
    )

    return row


def build_independent_training_dataframe(
    database_path: Path = DATABASE_PATH,
    cutoff_date: (
        date
        | datetime
        | str
        | None
    ) = None,
) -> pd.DataFrame:
    if not database_path.exists():
        return pd.DataFrame()

    training_cutoff_date = (
        resolve_independent_training_cutoff_date(
            cutoff_date
        )
    )
    connection = sqlite3.connect(
        database_path
    )
    connection.row_factory = sqlite3.Row

    try:
        races = connection.execute(
            """
            SELECT *
            FROM races
            WHERE
                result_status = '確定'
                AND first_place IS NOT NULL
                AND second_place IS NOT NULL
                AND third_place IS NOT NULL
                AND race_date <= ?
            ORDER BY
                race_date,
                venue,
                race_number
            """,
            (training_cutoff_date,),
        ).fetchall()

        output_rows: list[
            dict[str, Any]
        ] = []
        prepared_races: list[
            dict[str, Any]
        ] = []

        for race_row in races:
            race = dict(race_row)
            race_id = str(race["race_id"])
            rider_rows = connection.execute(
                """
                SELECT *
                FROM riders
                WHERE race_id = ?
                ORDER BY car_number
                """,
                (race_id,),
            ).fetchall()
            riders = {
                int(rider["car_number"]): rider
                for rider in (
                    _normalize_stored_rider(row)
                    for row in rider_rows
                )
                if int(rider["car_number"]) > 0
            }

            if len(riders) < 3:
                continue

            winner = (
                int(race["first_place"]),
                int(race["second_place"]),
                int(race["third_place"]),
            )

            if (
                len(set(winner)) != 3
                or not set(winner).issubset(
                    riders
                )
            ):
                continue

            prepared_races.append(
                {
                    "race": race,
                    "race_id": race_id,
                    "riders": riders,
                    "winner": winner,
                }
            )

        history: dict[
            str,
            list[dict[str, Any]],
        ] = {}

        for race_date_value, date_group in (
            itertools.groupby(
                prepared_races,
                key=lambda item: str(
                    item["race"][
                        "race_date"
                    ]
                ),
            )
        ):
            same_date_races = list(
                date_group
            )

            for prepared in same_date_races:
                race = prepared["race"]
                race_id = str(
                    prepared["race_id"]
                )
                riders = prepared["riders"]
                winner = prepared["winner"]
                venue = str(race["venue"])
                race_conditions = (
                    _normalize_race_conditions(
                        race
                    )
                )
                enriched_riders = {
                    number: {
                        **rider,
                        "recent_features": (
                            _recent_form_features(
                                _rider_history(
                                    history,
                                    rider,
                                ),
                                target_date=(
                                    race_date_value
                                ),
                                venue=venue,
                            )
                        ),
                    }
                    for number, rider
                    in riders.items()
                }

                for combination in (
                    itertools.permutations(
                        sorted(
                            enriched_riders
                        ),
                        3,
                    )
                ):
                    output_rows.append(
                        _candidate_row(
                            race_id=race_id,
                            race_date=(
                                race_date_value
                            ),
                            venue=venue,
                            race_number=int(
                                race[
                                    "race_number"
                                ]
                            ),
                            riders=(
                                enriched_riders
                            ),
                            race_conditions=(
                                race_conditions
                            ),
                            combination=(
                                combination
                            ),
                            target=int(
                                combination
                                == winner
                            ),
                        )
                    )

            # 同じ開催日の結果は、同日中の別レースへ
            # 混入させず、その日の特徴量生成後に追加する。
            for prepared in same_date_races:
                race = prepared["race"]
                race_id = str(
                    prepared["race_id"]
                )
                winner = prepared["winner"]

                for (
                    car_number,
                    rider,
                ) in prepared[
                    "riders"
                ].items():
                    if car_number == winner[0]:
                        finish_position = 1
                    elif car_number == winner[1]:
                        finish_position = 2
                    elif car_number == winner[2]:
                        finish_position = 3
                    else:
                        finish_position = 0

                    observation = {
                        "race_id": race_id,
                        "race_date": str(
                            race["race_date"]
                        ),
                        "venue": str(
                            race["venue"]
                        ),
                        "win": float(
                            finish_position == 1
                        ),
                        "top2": float(
                            finish_position
                            in (1, 2)
                        ),
                        "top3": float(
                            finish_position
                            in (1, 2, 3)
                        ),
                        "form_points": float(
                            {
                                1: 3,
                                2: 2,
                                3: 1,
                            }.get(
                                finish_position,
                                0,
                            )
                        ),
                        "competition_score": (
                            _safe_float(
                                rider.get(
                                    "competition_score"
                                )
                            )
                        ),
                    }
                    _append_rider_history(
                        history,
                        rider,
                        observation,
                    )

        return pd.DataFrame(output_rows)

    finally:
        connection.close()


def _load_history_before_date(
    database_path: Path,
    target_date: str,
) -> dict[
    str,
    list[dict[str, Any]],
]:
    history: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    if (
        not database_path.exists()
        or not str(target_date).strip()
    ):
        return history

    with sqlite3.connect(
        database_path
    ) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                rr.*,
                r.race_id
                    AS history_race_id,
                r.race_date
                    AS history_race_date,
                r.venue
                    AS history_venue,
                r.first_place,
                r.second_place,
                r.third_place
            FROM riders AS rr
            JOIN races AS r
                ON r.race_id = rr.race_id
            WHERE
                r.result_status = '確定'
                AND r.race_date < ?
                AND r.first_place
                    IS NOT NULL
                AND r.second_place
                    IS NOT NULL
                AND r.third_place
                    IS NOT NULL
            ORDER BY
                r.race_date,
                r.venue,
                r.race_number
            """,
            (str(target_date)[:10],),
        ).fetchall()

    for row in rows:
        values = dict(row)
        rider = _normalize_stored_rider(
            row
        )
        car_number = int(
            rider["car_number"]
        )
        first_place = _safe_int(
            values.get("first_place")
        )
        second_place = _safe_int(
            values.get("second_place")
        )
        third_place = _safe_int(
            values.get("third_place")
        )

        if car_number == first_place:
            finish_position = 1
        elif car_number == second_place:
            finish_position = 2
        elif car_number == third_place:
            finish_position = 3
        else:
            finish_position = 0

        _append_rider_history(
            history,
            rider,
            {
                "race_id": str(
                    values[
                        "history_race_id"
                    ]
                ),
                "race_date": str(
                    values[
                        "history_race_date"
                    ]
                ),
                "venue": str(
                    values["history_venue"]
                ),
                "win": float(
                    finish_position == 1
                ),
                "top2": float(
                    finish_position in (1, 2)
                ),
                "top3": float(
                    finish_position
                    in (1, 2, 3)
                ),
                "form_points": float(
                    {
                        1: 3,
                        2: 2,
                        3: 1,
                    }.get(
                        finish_position,
                        0,
                    )
                ),
                "competition_score": (
                    _safe_float(
                        rider.get(
                            "competition_score"
                        )
                    )
                ),
            },
        )

    return history


def build_independent_current_dataframe(
    *,
    riders: list[dict[str, Any]],
    lineup_groups: list[list[int]],
    race_id: str = "current_race",
    race_date: str = "",
    venue: str = "",
    race_number: int = 0,
    race_conditions: (
        dict[str, Any] | None
    ) = None,
    database_path: Path = DATABASE_PATH,
) -> pd.DataFrame:
    lineup = _lineup_metadata(
        lineup_groups
    )
    normalized_riders: dict[
        int,
        dict[str, Any],
    ] = {}
    history = _load_history_before_date(
        database_path,
        str(race_date),
    )
    normalized_conditions = (
        _normalize_race_conditions(
            {
                **(
                    riders[0]
                    if riders
                    else {}
                ),
                **(race_conditions or {}),
            }
        )
    )

    for raw_rider in riders:
        car_number = _safe_int(
            raw_rider.get("車番")
        )

        if car_number <= 0:
            continue

        normalized = _normalize_current_rider(
            raw_rider,
            lineup.get(car_number),
        )
        normalized[
            "recent_features"
        ] = _recent_form_features(
            _rider_history(
                history,
                normalized,
            ),
            target_date=str(race_date),
            venue=str(venue),
        )
        normalized_riders[car_number] = (
            normalized
        )

    if len(normalized_riders) < 3:
        return pd.DataFrame()

    output_rows = [
        _candidate_row(
            race_id=race_id,
            race_date=str(race_date),
            venue=str(venue),
            race_number=int(race_number),
            riders=normalized_riders,
            race_conditions=(
                normalized_conditions
            ),
            combination=combination,
            target=0,
        )
        for combination in itertools.permutations(
            sorted(normalized_riders),
            3,
        )
    ]

    return pd.DataFrame(output_rows)


def get_independent_feature_columns(
    dataframe: pd.DataFrame,
) -> list[str]:
    excluded = set(
        IDENTIFIER_COLUMNS
        + [TARGET_COLUMN]
    )
    columns = [
        column
        for column in dataframe.columns
        if column not in excluded
        and pd.api.types.is_numeric_dtype(
            dataframe[column]
        )
    ]

    forbidden = [
        column
        for column in columns
        if any(
            word in column.lower()
            for word in FORBIDDEN_FEATURE_WORDS
        )
    ]

    if forbidden:
        raise RuntimeError(
            "オッズ非依存モデルへ禁止特徴量が"
            "混入しています: "
            + "、".join(forbidden)
        )

    return columns


def get_independent_training_summary(
    database_path: Path = DATABASE_PATH,
    cutoff_date: (
        date
        | datetime
        | str
        | None
    ) = None,
) -> dict[str, Any]:
    training_cutoff_date = (
        resolve_independent_training_cutoff_date(
            cutoff_date
        )
    )

    if not database_path.exists():
        return {
            "completed_races": 0,
            "excluded_after_cutoff_races": 0,
            "review_races": 0,
            "training_cutoff_date": (
                training_cutoff_date
            ),
        }

    with sqlite3.connect(
        database_path
    ) as connection:
        valid_counts = connection.execute(
            """
            SELECT
                SUM(
                    CASE
                        WHEN race_date <= ?
                        THEN 1
                        ELSE 0
                    END
                ),
                SUM(
                    CASE
                        WHEN race_date > ?
                        THEN 1
                        ELSE 0
                    END
                )
            FROM races
            WHERE
                result_status = '確定'
                AND first_place IS NOT NULL
                AND second_place IS NOT NULL
                AND third_place IS NOT NULL
                AND first_place != second_place
                AND first_place != third_place
                AND second_place != third_place
                AND (
                    SELECT COUNT(*)
                    FROM riders
                    WHERE
                        riders.race_id
                        = races.race_id
                ) >= 3
            """,
            (
                training_cutoff_date,
                training_cutoff_date,
            ),
        ).fetchone()
        review = connection.execute(
            """
            SELECT COUNT(*)
            FROM races
            WHERE result_status = '要確認'
            """
        ).fetchone()[0]

    return {
        "completed_races": int(
            valid_counts[0] or 0
        ),
        "excluded_after_cutoff_races": int(
            valid_counts[1] or 0
        ),
        "review_races": int(review),
        "training_cutoff_date": (
            training_cutoff_date
        ),
    }
