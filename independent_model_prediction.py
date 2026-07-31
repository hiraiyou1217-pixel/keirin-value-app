from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from independent_learning_features import (
    FORBIDDEN_FEATURE_WORDS,
    build_independent_current_dataframe,
)
from train_independent_model import (
    INDEPENDENT_MODEL_PATH,
)
from learning_database import DATABASE_PATH
from portable_independent_model import (
    apply_probability_calibration,
)


def load_independent_model_package(
    model_path: Path = (
        INDEPENDENT_MODEL_PATH
    ),
) -> dict[str, Any]:
    if not model_path.exists():
        raise FileNotFoundError(
            "オッズ非依存の学習済みモデルが"
            "ありません。先にこのページで"
            "モデルを学習してください。"
        )

    package = joblib.load(model_path)

    if not isinstance(package, dict):
        raise RuntimeError(
            "モデルファイルの形式が不正です。"
        )

    if not package.get(
        "odds_independent"
    ):
        raise RuntimeError(
            "オッズ非依存モデルではありません。"
        )

    if "model" not in package:
        raise RuntimeError(
            "モデル本体がありません。"
        )

    feature_columns = list(
        package.get(
            "feature_columns",
            [],
        )
    )

    if not feature_columns:
        raise RuntimeError(
            "モデルの特徴量一覧がありません。"
        )

    forbidden = [
        column
        for column in feature_columns
        if any(
            word in column.lower()
            for word in FORBIDDEN_FEATURE_WORDS
        )
    ]

    if forbidden:
        raise RuntimeError(
            "保存モデルにオッズ関連特徴量が"
            "含まれています: "
            + "、".join(forbidden)
        )

    return package


def _normalize_probabilities(
    values: np.ndarray,
) -> np.ndarray:
    safe_values = np.maximum(
        values.astype(float),
        1e-15,
    )
    total = float(safe_values.sum())

    if total <= 0:
        return np.full(
            len(safe_values),
            1.0 / len(safe_values),
        )

    return safe_values / total


def _positive_class_probability(
    model: Any,
    X: pd.DataFrame,
) -> np.ndarray:
    probabilities = model.predict_proba(X)
    classes = list(model.classes_)

    if 1 not in classes:
        raise RuntimeError(
            "学習モデルに的中クラスがありません。"
        )

    return probabilities[
        :,
        classes.index(1),
    ]


def _build_rider_probabilities(
    dataframe: pd.DataFrame,
    probabilities: np.ndarray,
    riders: list[dict[str, Any]],
) -> pd.DataFrame:
    temporary = dataframe[
        [
            "first_car",
            "second_car",
            "third_car",
        ]
    ].copy()
    temporary["probability"] = (
        probabilities
    )
    rider_names: dict[int, str] = {}

    for rider in riders:
        try:
            car_number = int(
                float(
                    rider.get("車番", 0)
                )
            )
        except (TypeError, ValueError):
            continue

        if car_number <= 0:
            continue

        rider_names[car_number] = str(
            rider.get("選手名") or ""
        )
    car_numbers = sorted(rider_names)
    output: list[dict[str, Any]] = []

    for car_number in car_numbers:
        first_probability = float(
            temporary.loc[
                temporary["first_car"]
                == car_number,
                "probability",
            ].sum()
        )
        second_probability = float(
            temporary.loc[
                temporary["second_car"]
                == car_number,
                "probability",
            ].sum()
        )
        third_probability = float(
            temporary.loc[
                temporary["third_car"]
                == car_number,
                "probability",
            ].sum()
        )
        output.append(
            {
                "車番": car_number,
                "選手名": rider_names[
                    car_number
                ],
                "1着確率": first_probability,
                "2着確率": second_probability,
                "3着確率": third_probability,
                "3着内確率": min(
                    1.0,
                    first_probability
                    + second_probability
                    + third_probability,
                ),
            }
        )

    return (
        pd.DataFrame(output)
        .sort_values(
            [
                "1着確率",
                "3着内確率",
                "車番",
            ],
            ascending=[
                False,
                False,
                True,
            ],
        )
        .reset_index(drop=True)
    )


def predict_independent_race(
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
    model_path: Path = (
        INDEPENDENT_MODEL_PATH
    ),
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    dict[str, Any],
]:
    package = load_independent_model_package(
        model_path
    )
    dataframe = (
        build_independent_current_dataframe(
            riders=riders,
            lineup_groups=lineup_groups,
            race_id=race_id,
            race_date=race_date,
            venue=venue,
            race_number=race_number,
            race_conditions=(
                race_conditions
            ),
            database_path=database_path,
        )
    )

    if dataframe.empty:
        raise RuntimeError(
            "現在レースの出走前特徴量を"
            "作成できませんでした。"
        )

    feature_columns = list(
        package["feature_columns"]
    )

    for column in feature_columns:
        if column not in dataframe.columns:
            dataframe[column] = 0.0

    X = dataframe[
        feature_columns
    ].astype(float)
    raw_probabilities = (
        _positive_class_probability(
            package["model"],
            X,
        )
    )
    calibrated_probabilities = np.asarray(
        apply_probability_calibration(
            raw_probabilities,
            package.get(
                "probability_calibration"
            ),
        ),
        dtype=float,
    )
    probabilities = (
        _normalize_probabilities(
            calibrated_probabilities
        )
    )
    combination_output = dataframe[
        ["combination"]
    ].copy()
    combination_output["AI確率"] = (
        probabilities
    )
    combination_output = (
        combination_output.sort_values(
            [
                "AI確率",
                "combination",
            ],
            ascending=[
                False,
                True,
            ],
        )
        .reset_index(drop=True)
    )
    combination_output.insert(
        0,
        "予測順位",
        range(
            1,
            len(combination_output) + 1,
        ),
    )
    rider_output = (
        _build_rider_probabilities(
            dataframe,
            probabilities,
            riders,
        )
    )
    rider_feature_rows = (
        dataframe.sort_values(
            [
                "first_car",
                "combination",
            ]
        )
        .drop_duplicates(
            subset=["first_car"]
        )
    )
    first_feature_row = dataframe.iloc[
        0
    ]
    feature_coverage = {
        "rider_count": int(
            len(rider_feature_rows)
        ),
        "profile_rider_count": int(
            rider_feature_rows[
                "first_profile_known"
            ].sum()
        ),
        "recent_history_rider_count": int(
            rider_feature_rows[
                "first_has_prior_race"
            ].sum()
        ),
        "venue_characteristics_known": bool(
            first_feature_row[
                "venue_characteristics_known"
            ]
        ),
        "scheduled_start_known": bool(
            first_feature_row[
                "scheduled_start_known"
            ]
        ),
        "weather_known": bool(
            first_feature_row[
                "weather_known"
            ]
        ),
        "lineup_confidence": float(
            first_feature_row[
                "lineup_confidence"
            ]
        ),
    }
    metadata = {
        "trained_at": package.get(
            "trained_at",
            "",
        ),
        "model_version": package.get(
            "model_version",
            "",
        ),
        "training_start_date": package.get(
            "training_start_date",
            "",
        ),
        "training_end_date": package.get(
            "training_end_date",
            "",
        ),
        "training_cutoff_date": package.get(
            "training_cutoff_date",
            "",
        ),
        "excluded_after_cutoff_race_count": int(
            package.get(
                "excluded_after_cutoff_race_count",
                0,
            )
        ),
        "training_race_count": int(
            package.get(
                "race_count",
                0,
            )
        ),
        "training_row_count": int(
            package.get(
                "row_count",
                0,
            )
        ),
        "feature_count": len(
            feature_columns
        ),
        "prediction_count": len(
            combination_output
        ),
        "odds_independent": True,
        "probability_calibration": (
            package.get(
                "probability_calibration",
                {"method": "identity"},
            )
        ),
        "race_id": race_id,
        "feature_coverage": (
            feature_coverage
        ),
    }

    return (
        combination_output,
        rider_output,
        metadata,
    )
