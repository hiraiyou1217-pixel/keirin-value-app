from __future__ import annotations

from math import exp
from typing import Any


def extract_rider_numbers(
    odds_rows: list[dict[str, Any]],
) -> list[int]:
    riders: set[int] = set()

    for row in odds_rows:
        combination = str(row.get("組番", ""))

        for value in combination.split("-"):
            if value.isdigit():
                rider = int(value)

                if 1 <= rider <= 9:
                    riders.add(rider)

    return sorted(riders)


def score_to_weights(
    scores: dict[int, float],
    temperature: float = 1.0,
) -> dict[int, float]:
    if not scores:
        return {}

    safe_temperature = max(float(temperature), 0.05)
    mean_score = sum(scores.values()) / len(scores)

    weights: dict[int, float] = {}

    for rider, score in scores.items():
        scaled = (float(score) - mean_score) / safe_temperature

        # expのオーバーフローを防止
        scaled = max(-30.0, min(30.0, scaled))
        weights[rider] = exp(scaled)

    return weights


def trifecta_probability(
    first: int,
    second: int,
    third: int,
    weights: dict[int, float],
) -> float:
    if len({first, second, third}) != 3:
        return 0.0

    if not all(
        rider in weights
        for rider in (first, second, third)
    ):
        return 0.0

    total = sum(weights.values())

    if total <= 0:
        return 0.0

    first_weight = weights[first]
    remaining_after_first = total - first_weight

    if remaining_after_first <= 0:
        return 0.0

    second_weight = weights[second]
    remaining_after_second = (
        remaining_after_first - second_weight
    )

    if remaining_after_second <= 0:
        return 0.0

    third_weight = weights[third]

    return (
        first_weight / total
        * second_weight / remaining_after_first
        * third_weight / remaining_after_second
    )


def calculate_market_probabilities(
    odds_rows: list[dict[str, Any]],
) -> dict[str, float]:
    inverse_odds: dict[str, float] = {}

    for row in odds_rows:
        combination = str(row.get("組番", ""))
        odds = float(row.get("オッズ", 0))

        if odds > 1.0:
            inverse_odds[combination] = 1.0 / odds

    total = sum(inverse_odds.values())

    if total <= 0:
        return {}

    return {
        combination: value / total
        for combination, value in inverse_odds.items()
    }


def fractional_kelly_fraction(
    probability: float,
    odds: float,
    fraction: float = 0.25,
) -> float:
    if probability <= 0 or odds <= 1:
        return 0.0

    net_odds = odds - 1.0
    losing_probability = 1.0 - probability

    full_kelly = (
        net_odds * probability - losing_probability
    ) / net_odds

    return max(0.0, full_kelly * fraction)


def calculate_expected_values(
    odds_rows: list[dict[str, Any]],
    scores: dict[int, float],
    temperature: float = 1.0,
    bankroll: int = 10_000,
    kelly_fraction: float = 0.25,
) -> list[dict[str, Any]]:
    weights = score_to_weights(
        scores,
        temperature=temperature,
    )

    market_probabilities = (
        calculate_market_probabilities(odds_rows)
    )

    results: list[dict[str, Any]] = []

    for row in odds_rows:
        combination = str(row.get("組番", ""))
        odds = float(row.get("オッズ", 0))
        popularity = int(row.get("人気", 9999))

        parts = combination.split("-")

        if len(parts) != 3:
            continue

        try:
            first, second, third = (
                int(parts[0]),
                int(parts[1]),
                int(parts[2]),
            )
        except ValueError:
            continue

        model_probability = trifecta_probability(
            first,
            second,
            third,
            weights,
        )

        market_probability = market_probabilities.get(
            combination,
            0.0,
        )

        expected_return = model_probability * odds
        expected_profit = expected_return - 1.0

        fair_odds = (
            1.0 / model_probability
            if model_probability > 0
            else 0.0
        )

        value_ratio = (
            model_probability / market_probability
            if market_probability > 0
            else 0.0
        )

        kelly = fractional_kelly_fraction(
            model_probability,
            odds,
            fraction=kelly_fraction,
        )

        suggested_bet = int(
            bankroll * kelly // 100 * 100
        )

        results.append(
            {
                "人気": popularity,
                "組番": combination,
                "オッズ": odds,
                "モデル確率": model_probability,
                "市場確率": market_probability,
                "フェアオッズ": fair_odds,
                "期待回収率": expected_return,
                "期待利益率": expected_profit,
                "妙味倍率": value_ratio,
                "参考購入額": suggested_bet,
            }
        )

    return sorted(
        results,
        key=lambda item: (
            -item["期待回収率"],
            item["人気"],
        ),
    )
