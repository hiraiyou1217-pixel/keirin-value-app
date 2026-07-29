from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
)
from sklearn.metrics import (
    log_loss,
    roc_auc_score,
)
from sklearn.model_selection import GroupKFold

from learning_features import (
    build_training_dataframe,
    get_feature_columns,
)


MODEL_DIRECTORY = (
    Path(__file__).resolve().parent
    / "models"
)

MODEL_PATH = (
    MODEL_DIRECTORY
    / "keirin_baseline_model.joblib"
)

METADATA_PATH = (
    MODEL_DIRECTORY
    / "keirin_baseline_model_metadata.json"
)


def normalize_by_race(
    dataframe: pd.DataFrame,
    raw_probabilities: np.ndarray,
) -> np.ndarray:
    normalized = np.zeros(
        len(dataframe),
        dtype=float,
    )

    temporary = dataframe[
        ["race_id"]
    ].copy()

    temporary["raw_probability"] = np.maximum(
        raw_probabilities,
        1e-12,
    )

    for _, indices in temporary.groupby(
        "race_id"
    ).groups.items():
        group_indices = np.asarray(
            list(indices),
            dtype=int,
        )

        values = temporary.loc[
            group_indices,
            "raw_probability",
        ].to_numpy(dtype=float)

        total = float(values.sum())

        if total <= 0:
            normalized[group_indices] = (
                1.0 / len(group_indices)
            )
        else:
            normalized[group_indices] = (
                values / total
            )

    return normalized


def evaluate_race_predictions(
    dataframe: pd.DataFrame,
    probabilities: np.ndarray,
) -> dict[str, float]:
    evaluation = dataframe[
        [
            "race_id",
            "combination",
            "target",
            "odds",
        ]
    ].copy()

    evaluation["probability"] = probabilities

    race_count = evaluation[
        "race_id"
    ].nunique()

    top1_hits = 0
    top3_hits = 0
    winner_ranks: list[int] = []
    winning_probabilities: list[float] = []

    for _, race in evaluation.groupby(
        "race_id"
    ):
        ordered = race.sort_values(
            "probability",
            ascending=False,
        ).reset_index(drop=True)

        winner_positions = ordered.index[
            ordered["target"] == 1
        ].tolist()

        if not winner_positions:
            continue

        winner_rank = int(
            winner_positions[0]
        ) + 1

        winner_ranks.append(winner_rank)

        winner_probability = float(
            ordered.loc[
                winner_positions[0],
                "probability",
            ]
        )

        winning_probabilities.append(
            winner_probability
        )

        if winner_rank == 1:
            top1_hits += 1

        if winner_rank <= 3:
            top3_hits += 1

    epsilon = 1e-15

    race_log_loss = float(
        -np.mean(
            np.log(
                np.maximum(
                    winning_probabilities,
                    epsilon,
                )
            )
        )
    )

    return {
        "race_count": float(race_count),
        "top1_hit_rate": (
            top1_hits / race_count
            if race_count
            else 0.0
        ),
        "top3_hit_rate": (
            top3_hits / race_count
            if race_count
            else 0.0
        ),
        "mean_winner_rank": (
            float(np.mean(winner_ranks))
            if winner_ranks
            else 0.0
        ),
        "median_winner_rank": (
            float(np.median(winner_ranks))
            if winner_ranks
            else 0.0
        ),
        "race_log_loss": race_log_loss,
    }


def train_baseline_model(
    *,
    minimum_completed_races: int = 30,
    cross_validation_splits: int = 5,
) -> dict[str, Any]:
    dataframe = build_training_dataframe()

    if dataframe.empty:
        raise RuntimeError(
            "学習可能な結果確定レースがありません。"
        )

    race_count = int(
        dataframe["race_id"].nunique()
    )

    if race_count < minimum_completed_races:
        raise RuntimeError(
            f"結果確定レースが{race_count}件です。"
            f"最低{minimum_completed_races}件を"
            "保存してから学習してください。"
        )

    feature_columns = get_feature_columns(
        dataframe
    )

    X = dataframe[
        feature_columns
    ].astype(float)

    y = dataframe[
        "target"
    ].astype(int)

    groups = dataframe["race_id"]

    split_count = min(
        int(cross_validation_splits),
        race_count,
    )

    if split_count < 2:
        raise RuntimeError(
            "交差検証には2レース以上必要です。"
        )

    group_kfold = GroupKFold(
        n_splits=split_count
    )

    out_of_fold_raw = np.zeros(
        len(dataframe),
        dtype=float,
    )

    fold_results: list[dict[str, Any]] = []

    for fold_number, (
        train_indices,
        validation_indices,
    ) in enumerate(
        group_kfold.split(
            X,
            y,
            groups=groups,
        ),
        start=1,
    ):
        model = HistGradientBoostingClassifier(
            loss="log_loss",
            learning_rate=0.05,
            max_iter=250,
            max_leaf_nodes=15,
            min_samples_leaf=30,
            l2_regularization=1.0,
            early_stopping=True,
            random_state=42 + fold_number,
        )

        model.fit(
            X.iloc[train_indices],
            y.iloc[train_indices],
        )

        raw_probabilities = model.predict_proba(
            X.iloc[validation_indices]
        )[:, 1]

        out_of_fold_raw[
            validation_indices
        ] = raw_probabilities

        fold_auc = roc_auc_score(
            y.iloc[validation_indices],
            raw_probabilities,
        )

        fold_results.append(
            {
                "fold": fold_number,
                "train_races": int(
                    dataframe.iloc[
                        train_indices
                    ]["race_id"].nunique()
                ),
                "validation_races": int(
                    dataframe.iloc[
                        validation_indices
                    ]["race_id"].nunique()
                ),
                "roc_auc": float(fold_auc),
            }
        )

    normalized_probabilities = normalize_by_race(
        dataframe,
        out_of_fold_raw,
    )

    overall_auc = float(
        roc_auc_score(
            y,
            out_of_fold_raw,
        )
    )

    binary_log_loss = float(
        log_loss(
            y,
            np.clip(
                out_of_fold_raw,
                1e-15,
                1 - 1e-15,
            ),
            labels=[0, 1],
        )
    )

    race_metrics = evaluate_race_predictions(
        dataframe,
        normalized_probabilities,
    )

    final_model = HistGradientBoostingClassifier(
        loss="log_loss",
        learning_rate=0.05,
        max_iter=250,
        max_leaf_nodes=15,
        min_samples_leaf=30,
        l2_regularization=1.0,
        early_stopping=True,
        random_state=42,
    )

    final_model.fit(X, y)

    MODEL_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    model_package = {
        "model": final_model,
        "feature_columns": feature_columns,
        "trained_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "race_count": race_count,
        "row_count": len(dataframe),
    }

    joblib.dump(
        model_package,
        MODEL_PATH,
    )

    metadata = {
        "trained_at": model_package[
            "trained_at"
        ],
        "race_count": race_count,
        "row_count": len(dataframe),
        "positive_rows": int(y.sum()),
        "feature_count": len(
            feature_columns
        ),
        "model_path": str(MODEL_PATH),
        "roc_auc": overall_auc,
        "binary_log_loss": binary_log_loss,
        **race_metrics,
        "fold_results": fold_results,
        "feature_columns": feature_columns,
    }

    METADATA_PATH.write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return metadata
