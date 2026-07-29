from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from learning_features import (
    build_current_race_dataframe,
)
from train_learning_model import MODEL_PATH


def load_model_package(
    model_path: Path = MODEL_PATH,
) -> dict[str, Any]:
    if not model_path.exists():
        raise FileNotFoundError(
            "学習済みモデルがありません。"
            "先に「モデル学習」ページで"
            "基準モデルを学習してください。"
        )

    package = joblib.load(model_path)

    if not isinstance(package, dict):
        raise RuntimeError(
            "モデルファイルの形式が不正です。"
        )

    if "model" not in package:
        raise RuntimeError(
            "モデル本体が保存されていません。"
        )

    if "feature_columns" not in package:
        raise RuntimeError(
            "特徴量一覧が保存されていません。"
        )

    return package


def normalize_probabilities(
    probabilities: np.ndarray,
) -> np.ndarray:
    safe_probabilities = np.maximum(
        probabilities.astype(float),
        1e-15,
    )

    total = float(
        safe_probabilities.sum()
    )

    if total <= 0:
        return np.full(
            len(safe_probabilities),
            1.0 / len(safe_probabilities),
        )

    return safe_probabilities / total


def predict_current_race(
    *,
    odds_rows: list[dict[str, Any]],
    riders: list[dict[str, Any]],
    lineup_groups: list[list[int]],
    race_id: str = "current_race",
    race_date: str = "",
    venue: str = "",
    race_number: int = 0,
    market_blend: float = 0.25,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    package = load_model_package()

    model = package["model"]
    feature_columns = list(
        package["feature_columns"]
    )

    dataframe = build_current_race_dataframe(
        odds_rows=odds_rows,
        riders=riders,
        lineup_groups=lineup_groups,
        race_id=race_id,
        race_date=race_date,
        venue=venue,
        race_number=race_number,
    )

    if dataframe.empty:
        raise RuntimeError(
            "現在レースの特徴量を作成できませんでした。"
        )

    for column in feature_columns:
        if column not in dataframe.columns:
            dataframe[column] = 0.0

    X = dataframe[
        feature_columns
    ].astype(float)

    raw_model_probabilities = (
        model.predict_proba(X)[:, 1]
    )

    model_probabilities = normalize_probabilities(
        raw_model_probabilities
    )

    market_raw = (
        1.0
        / dataframe["odds"].astype(float)
    ).to_numpy()

    market_probabilities = normalize_probabilities(
        market_raw
    )

    safe_market_blend = max(
        0.0,
        min(0.90, float(market_blend)),
    )

    blended_raw = (
        np.power(
            np.maximum(
                model_probabilities,
                1e-15,
            ),
            1.0 - safe_market_blend,
        )
        * np.power(
            np.maximum(
                market_probabilities,
                1e-15,
            ),
            safe_market_blend,
        )
    )

    final_probabilities = normalize_probabilities(
        blended_raw
    )

    output = dataframe[
        [
            "combination",
            "popularity",
            "odds",
        ]
    ].copy()

    output["学習モデル確率"] = (
        model_probabilities
    )

    output["市場確率"] = (
        market_probabilities
    )

    output["最終確率"] = (
        final_probabilities
    )

    output["フェアオッズ"] = np.where(
        final_probabilities > 0,
        1.0 / final_probabilities,
        np.nan,
    )

    output["期待回収率"] = (
        final_probabilities
        * output["odds"].astype(float)
    )

    output["期待利益率"] = (
        output["期待回収率"] - 1.0
    )

    output["市場比"] = np.where(
        market_probabilities > 0,
        final_probabilities
        / market_probabilities,
        0.0,
    )

    output = output.sort_values(
        [
            "最終確率",
            "期待回収率",
        ],
        ascending=[
            False,
            False,
        ],
    ).reset_index(drop=True)

    output.insert(
        0,
        "予測順位",
        range(1, len(output) + 1),
    )

    metadata = {
        "trained_at": package.get(
            "trained_at",
            "",
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
        "prediction_count": len(output),
        "market_blend": safe_market_blend,
    }

    return output, metadata
