from __future__ import annotations

from statistics import mean, pstdev
from typing import Any


def clamp(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    return max(minimum, min(maximum, value))


def numeric_value(
    rider: dict[str, Any],
    key: str,
    default: float = 0.0,
) -> float:
    value = rider.get(key)

    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def z_scores(
    values: dict[int, float],
) -> dict[int, float]:
    if not values:
        return {}

    average = mean(values.values())
    deviation = pstdev(values.values())

    if deviation < 0.000001:
        return {
            rider: 0.0
            for rider in values
        }

    return {
        rider: (value - average) / deviation
        for rider, value in values.items()
    }


def build_automatic_scores(
    riders: list[dict[str, Any]],
) -> dict[int, float]:
    if not riders:
        return {}

    race_scores = {
        int(rider["車番"]): numeric_value(
            rider,
            "競走得点",
            0.0,
        )
        for rider in riders
    }

    available_race_scores = {
        rider: score
        for rider, score in race_scores.items()
        if score > 0
    }

    race_score_z = z_scores(
        available_race_scores
    )

    result: dict[int, float] = {}

    for rider in riders:
        number = int(rider["車番"])

        # 中立値
        score = 50.0

        # 競走得点：最大±15点
        score += clamp(
            race_score_z.get(number, 0.0) * 7.5,
            -15.0,
            15.0,
        )

        b_count = numeric_value(rider, "B")
        h_count = numeric_value(rider, "H")
        s_count = numeric_value(rider, "S")

        win_rate = numeric_value(
            rider,
            "勝率",
        )

        place2_rate = numeric_value(
            rider,
            "2連対率",
        )

        place3_rate = numeric_value(
            rider,
            "3連対率",
        )

        style = str(
            rider.get("脚質", "")
        )

        # 先行力
        score += clamp(b_count * 0.45, 0.0, 5.0)
        score += clamp(h_count * 0.20, 0.0, 2.5)

        # 位置取り・スタート
        score += clamp(s_count * 0.15, 0.0, 2.0)

        # 成績率
        score += clamp(win_rate * 0.08, 0.0, 6.0)
        score += clamp(place2_rate * 0.04, 0.0, 4.0)
        score += clamp(place3_rate * 0.02, 0.0, 3.0)

        # 脚質は小さな補正に限定
        if style == "両":
            score += 1.0
        elif style == "逃":
            score += 0.5
        elif style == "追":
            score += 0.0

        result[number] = round(
            clamp(score, 20.0, 85.0),
            1,
        )

    return result
