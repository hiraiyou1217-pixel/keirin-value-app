from __future__ import annotations

from typing import Any


def clamp(
    value: float,
    minimum: float = 0.0,
    maximum: float = 100.0,
) -> float:
    return max(minimum, min(maximum, value))


def number_value(
    row: dict[str, Any],
    key: str,
    default: float = 0.0,
) -> float:
    value = row.get(key)

    if value in (None, ""):
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_lineup_metadata(
    lineup_groups: list[list[int]],
) -> dict[int, dict[str, Any]]:
    metadata: dict[int, dict[str, Any]] = {}

    for group_index, group in enumerate(lineup_groups):
        for position, rider in enumerate(group):
            metadata[int(rider)] = {
                "ライン番号": group_index + 1,
                "ライン位置": position,
                "ライン長": len(group),
                "ライン": "-".join(
                    str(value)
                    for value in group
                ),
            }

    return metadata


def calculate_rider_indices(
    riders: list[dict[str, Any]],
    lineup_groups: list[list[int]],
) -> dict[int, dict[str, Any]]:
    """
    出走表データから展開指数を作成する。

    学習済みモデルではなく、説明可能なルールベース指標。
    """
    lineup_metadata = build_lineup_metadata(
        lineup_groups
    )

    competition_scores = {
        int(rider["車番"]): number_value(
            rider,
            "競走得点",
        )
        for rider in riders
        if rider.get("車番") is not None
    }

    score_order = sorted(
        competition_scores,
        key=lambda number: (
            -competition_scores[number],
            number,
        ),
    )

    score_ranks = {
        number: rank
        for rank, number in enumerate(
            score_order,
            start=1,
        )
    }

    results: dict[int, dict[str, Any]] = {}

    for rider in riders:
        try:
            number = int(rider["車番"])
        except (KeyError, TypeError, ValueError):
            continue

        style = str(
            rider.get("脚質", "")
        ).strip()

        b_count = number_value(rider, "B")
        h_count = number_value(rider, "H")
        s_count = number_value(rider, "S")
        win_rate = number_value(rider, "勝率")
        place2_rate = number_value(
            rider,
            "2連対率",
        )
        place3_rate = number_value(
            rider,
            "3連対率",
        )

        lineup = lineup_metadata.get(
            number,
            {
                "ライン番号": None,
                "ライン位置": 0,
                "ライン長": 1,
                "ライン": str(number),
            },
        )

        position = int(
            lineup.get("ライン位置", 0)
        )
        line_length = int(
            lineup.get("ライン長", 1)
        )

        escape_index = 20.0
        escape_index += b_count * 5.0
        escape_index += h_count * 2.5
        escape_index += win_rate * 0.35

        if style == "逃":
            escape_index += 22.0
        elif style == "両":
            escape_index += 10.0
        elif style == "追":
            escape_index -= 10.0

        if position == 0 and line_length >= 2:
            escape_index += 7.0

        makuri_index = 25.0
        makuri_index += b_count * 2.0
        makuri_index += s_count * 1.2
        makuri_index += win_rate * 0.45
        makuri_index += place2_rate * 0.20

        if style == "両":
            makuri_index += 20.0
        elif style == "逃":
            makuri_index += 10.0
        elif style == "追":
            makuri_index -= 6.0

        chase_index = 20.0
        chase_index += s_count * 1.5
        chase_index += place2_rate * 0.30
        chase_index += place3_rate * 0.20

        if style == "追":
            chase_index += 20.0
        elif style == "両":
            chase_index += 8.0

        if position == 1:
            chase_index += 15.0
        elif position == 2:
            chase_index += 8.0
        elif position >= 3:
            chase_index += 4.0

        results[number] = {
            "車番": number,
            "選手名": rider.get(
                "選手名",
                f"{number}番車",
            ),
            "AI印": rider.get("AI印", ""),
            "競走得点": competition_scores.get(
                number,
                0.0,
            ),
            "競走得点順位": score_ranks.get(
                number,
            ),
            "脚質": style,
            "先行指数": round(
                clamp(escape_index),
                1,
            ),
            "捲り指数": round(
                clamp(makuri_index),
                1,
            ),
            "追込指数": round(
                clamp(chase_index),
                1,
            ),
            **lineup,
        }

    return results


def lineup_relation(
    first: int,
    second: int,
    third: int,
    lineup_groups: list[list[int]],
) -> dict[str, bool]:
    exact = False
    first_second = False
    second_third = False
    second_over_first = False

    for group in lineup_groups:
        if first in group and second in group:
            first_index = group.index(first)
            second_index = group.index(second)

            if second_index == first_index + 1:
                first_second = True

            if (
                first_index == 1
                and second_index == 0
            ):
                second_over_first = True

        if second in group and third in group:
            second_index = group.index(second)
            third_index = group.index(third)

            if third_index == second_index + 1:
                second_third = True

        if all(
            number in group
            for number in (first, second, third)
        ):
            indices = [
                group.index(first),
                group.index(second),
                group.index(third),
            ]

            if (
                indices[1] == indices[0] + 1
                and indices[2] == indices[1] + 1
            ):
                exact = True

    return {
        "完全ライン順": exact,
        "1着2着ライン連携": first_second,
        "2着3着ライン連携": second_third,
        "番手差し": second_over_first,
    }


def build_bet_reasons(
    expected_rows: list[dict[str, Any]],
    rider_indices: dict[int, dict[str, Any]],
    lineup_groups: list[list[int]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for row in expected_rows:
        combination = str(
            row.get("組番", "")
        )

        parts = combination.split("-")

        if len(parts) != 3:
            results.append(
                {
                    **row,
                    "購入理由": "",
                }
            )
            continue

        try:
            first, second, third = map(
                int,
                parts,
            )
        except ValueError:
            results.append(
                {
                    **row,
                    "購入理由": "",
                }
            )
            continue

        first_data = rider_indices.get(
            first,
            {},
        )
        second_data = rider_indices.get(
            second,
            {},
        )
        third_data = rider_indices.get(
            third,
            {},
        )

        relation = lineup_relation(
            first,
            second,
            third,
            lineup_groups,
        )

        reasons: list[str] = []

        if relation["完全ライン順"]:
            reasons.append(
                "本線ラインの並び順"
            )
        elif relation["番手差し"]:
            reasons.append(
                "番手差しのライン決着"
            )
        elif relation["1着2着ライン連携"]:
            reasons.append(
                "1着・2着が同ライン"
            )

        if relation["2着3着ライン連携"]:
            reasons.append(
                "2着・3着が同ライン"
            )

        if first_data.get(
            "競走得点順位"
        ) == 1:
            reasons.append(
                "1着候補が競走得点1位"
            )
        elif first_data.get(
            "競走得点順位"
        ) in (2, 3):
            reasons.append(
                "1着候補が競走得点上位"
            )

        first_mark = str(
            first_data.get("AI印", "")
        )

        if first_mark:
            reasons.append(
                f"1着候補がAI{first_mark}"
            )

        if (
            float(
                first_data.get(
                    "先行指数",
                    0,
                )
            ) >= 70
        ):
            reasons.append(
                "1着候補の先行指数が高い"
            )

        if (
            float(
                first_data.get(
                    "捲り指数",
                    0,
                )
            ) >= 70
        ):
            reasons.append(
                "1着候補の捲り指数が高い"
            )

        if (
            float(
                second_data.get(
                    "追込指数",
                    0,
                )
            ) >= 70
        ):
            reasons.append(
                "2着候補の追込指数が高い"
            )

        if (
            int(
                second_data.get(
                    "ライン位置",
                    -1,
                )
            ) == 1
        ):
            reasons.append(
                "2着候補がライン番手"
            )

        if (
            int(
                third_data.get(
                    "ライン位置",
                    -1,
                )
            ) == 2
        ):
            reasons.append(
                "3着候補がライン3番手"
            )

        expected_return = float(
            row.get(
                "期待回収率",
                0,
            )
        )

        if expected_return >= 1.50:
            reasons.append(
                "期待回収率150%以上"
            )
        elif expected_return >= 1.20:
            reasons.append(
                "期待回収率120%以上"
            )
        elif expected_return >= 1.00:
            reasons.append(
                "期待回収率100%以上"
            )

        value_ratio = float(
            row.get(
                "妙味倍率",
                0,
            )
        )

        if value_ratio >= 1.50:
            reasons.append(
                "市場評価よりモデル評価が大幅に高い"
            )
        elif value_ratio >= 1.20:
            reasons.append(
                "市場評価よりモデル評価が高い"
            )

        results.append(
            {
                **row,
                "購入理由": " / ".join(
                    reasons[:6]
                ),
            }
        )

    return results
