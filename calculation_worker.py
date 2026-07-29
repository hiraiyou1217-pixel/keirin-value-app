from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import Any

from advanced_probability_model import (
    calculate_expected_values_v2,
)
from probability_model import allocate_bet_budget
from race_analysis import (
    build_bet_reasons,
    calculate_rider_indices,
)


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    odds = payload.get("odds", [])
    scores_raw = payload.get("scores", {})
    riders = payload.get("riders", [])
    lineup_groups = payload.get("lineup_groups", [])

    scores = {
        int(number): float(score)
        for number, score in scores_raw.items()
    }

    settings = payload.get("settings", {})

    expected_values = calculate_expected_values_v2(
        odds,
        scores=scores,
        riders=riders,
        model_mode=str(
            settings.get(
                "model_mode",
                "バランス型",
            )
        ),
        bankroll=int(
            settings.get("bankroll", 10_000)
        ),
        kelly_fraction=float(
            settings.get("kelly_fraction", 0.25)
        ),
        lineup_groups=lineup_groups,
        market_blend=float(
            settings.get("market_blend", 0.55)
        ),
        maximum_expected_return=float(
            settings.get(
                "maximum_expected_return",
                3.0,
            )
        ),
    )

    rider_indices = calculate_rider_indices(
        riders,
        lineup_groups,
    )

    expected_values = build_bet_reasons(
        expected_values,
        rider_indices,
        lineup_groups,
    )

    bet_plan = allocate_bet_budget(
        expected_values,
        budget=int(
            settings.get("betting_budget", 10_000)
        ),
        minimum_expected_return=float(
            settings.get(
                "minimum_expected_return",
                1.05,
            )
        ),
        maximum_bets=int(
            settings.get("maximum_bets", 8)
        ),
        minimum_unit=int(
            settings.get("minimum_unit", 100)
        ),
        maximum_bet_ratio=max(
            0.05,
            min(
                0.50,
                float(
                    settings.get(
                        "maximum_bet_ratio",
                        0.20,
                    )
                ),
            ),
        ),
        maximum_odds=float(
            settings.get("maximum_odds", 300.0)
        ),
        maximum_popularity=int(
            settings.get(
                "maximum_popularity",
                120,
            )
        ),
        minimum_model_probability=float(
            settings.get(
                "minimum_model_probability",
                0.001,
            )
        ),
    )

    return {
        "success": True,
        "expected_values": expected_values,
        "bet_plan": bet_plan,
        "candidate_count": len(bet_plan),
        "message": (
            f"{len(bet_plan)}点の買い目プランを作成しました。"
            if bet_plan
            else "買い目候補は0件です。"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        required=True,
    )
    parser.add_argument(
        "--output",
        required=True,
    )

    arguments = parser.parse_args()

    input_path = Path(arguments.input)
    output_path = Path(arguments.output)

    try:
        payload = json.loads(
            input_path.read_text(encoding="utf-8")
        )

        result = execute(payload)

    except Exception as exc:
        result = {
            "success": False,
            "expected_values": [],
            "bet_plan": [],
            "candidate_count": 0,
            "message": (
                f"{type(exc).__name__}: {exc}"
            ),
            "traceback": traceback.format_exc(),
        }

    output_path.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
