from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
)
from sklearn.model_selection import (
    TimeSeriesSplit,
)

from independent_learning_features import (
    FORBIDDEN_FEATURE_WORDS,
    build_independent_training_dataframe,
    get_independent_feature_columns,
    get_independent_training_summary,
    resolve_independent_training_cutoff_date,
)
from learning_database import (
    DATABASE_PATH,
    initialize_database,
)


MODEL_DIRECTORY = (
    Path(__file__).resolve().parent
    / "models"
)
INDEPENDENT_MODEL_PATH = (
    MODEL_DIRECTORY
    / "keirin_odds_independent_model.joblib"
)
INDEPENDENT_METADATA_PATH = (
    MODEL_DIRECTORY
    / (
        "keirin_odds_independent_"
        "model_metadata.json"
    )
)
MODEL_VERSION = 3


def _positive_class_probability(
    model: HistGradientBoostingClassifier,
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


def normalize_by_race(
    dataframe: pd.DataFrame,
    raw_probabilities: np.ndarray,
) -> np.ndarray:
    normalized = np.zeros(
        len(dataframe),
        dtype=float,
    )

    for indices in dataframe.groupby(
        "race_id",
        sort=False,
    ).groups.values():
        positions = np.asarray(
            list(indices),
            dtype=int,
        )
        values = np.maximum(
            raw_probabilities[positions],
            1e-15,
        )
        total = float(values.sum())

        if total <= 0:
            normalized[positions] = (
                1.0 / len(positions)
            )
        else:
            normalized[positions] = (
                values / total
            )

    return normalized


def chronological_race_splits(
    dataframe: pd.DataFrame,
    split_count: int,
) -> Iterator[
    tuple[np.ndarray, np.ndarray]
]:
    date_order = pd.DataFrame(
        {
            "race_date": sorted(
                dataframe[
                    "race_date"
                ].astype(str).unique()
            )
        }
    )

    splitter = TimeSeriesSplit(
        n_splits=int(split_count)
    )

    for train_dates, validation_dates in (
        splitter.split(date_order)
    ):
        training_date_values = set(
            date_order.iloc[
                train_dates
            ]["race_date"]
        )
        validation_date_values = set(
            date_order.iloc[
                validation_dates
            ]["race_date"]
        )
        train_rows = np.flatnonzero(
            dataframe["race_date"].isin(
                training_date_values
            ).to_numpy()
        )
        validation_rows = np.flatnonzero(
            dataframe["race_date"].isin(
                validation_date_values
            ).to_numpy()
        )

        yield train_rows, validation_rows


def evaluate_independent_predictions(
    dataframe: pd.DataFrame,
    probabilities: np.ndarray,
) -> dict[str, float]:
    evaluation = dataframe[
        [
            "race_id",
            "combination",
            "first_car",
            "target",
        ]
    ].copy()
    evaluation["probability"] = (
        probabilities
    )

    top1_hits = 0
    top5_hits = 0
    top10_hits = 0
    first_place_hits = 0
    winner_ranks: list[int] = []
    winner_probabilities: list[float] = []

    for _, race in evaluation.groupby(
        "race_id",
        sort=False,
    ):
        ordered = race.sort_values(
            [
                "probability",
                "combination",
            ],
            ascending=[
                False,
                True,
            ],
        ).reset_index(drop=True)
        winner_positions = ordered.index[
            ordered["target"] == 1
        ].tolist()

        if not winner_positions:
            continue

        winner_position = int(
            winner_positions[0]
        )
        winner_rank = winner_position + 1
        winner_ranks.append(winner_rank)
        winner_probabilities.append(
            float(
                ordered.loc[
                    winner_position,
                    "probability",
                ]
            )
        )

        top1_hits += int(
            winner_rank <= 1
        )
        top5_hits += int(
            winner_rank <= 5
        )
        top10_hits += int(
            winner_rank <= 10
        )

        actual_first = int(
            ordered.loc[
                winner_position,
                "first_car",
            ]
        )
        first_probabilities = (
            race.groupby("first_car")[
                "probability"
            ]
            .sum()
            .sort_values(
                ascending=False
            )
        )

        if not first_probabilities.empty:
            first_place_hits += int(
                int(
                    first_probabilities
                    .index[0]
                )
                == actual_first
            )

    evaluated_races = len(winner_ranks)
    epsilon = 1e-15
    race_log_loss = (
        float(
            -np.mean(
                np.log(
                    np.maximum(
                        winner_probabilities,
                        epsilon,
                    )
                )
            )
        )
        if winner_probabilities
        else 0.0
    )

    return {
        "evaluated_race_count": float(
            evaluated_races
        ),
        "top1_hit_rate": (
            top1_hits / evaluated_races
            if evaluated_races
            else 0.0
        ),
        "top5_hit_rate": (
            top5_hits / evaluated_races
            if evaluated_races
            else 0.0
        ),
        "top10_hit_rate": (
            top10_hits / evaluated_races
            if evaluated_races
            else 0.0
        ),
        "first_place_hit_rate": (
            first_place_hits
            / evaluated_races
            if evaluated_races
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


def _new_model(
    random_state: int,
) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        loss="log_loss",
        learning_rate=0.05,
        max_iter=250,
        max_leaf_nodes=31,
        min_samples_leaf=50,
        l2_regularization=1.0,
        early_stopping=True,
        class_weight="balanced",
        random_state=int(random_state),
    )


def _backup_existing_models(
    model_path: Path,
    metadata_path: Path,
) -> None:
    existing = [
        path
        for path in (
            model_path,
            metadata_path,
        )
        if path.exists()
    ]

    if not existing:
        return

    backup_directory = (
        model_path.parent
        / "backups"
    )
    backup_directory.mkdir(
        parents=True,
        exist_ok=True,
    )
    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    for path in existing:
        shutil.copy2(
            path,
            backup_directory
            / f"{path.stem}_{timestamp}{path.suffix}",
        )


def train_independent_model(
    *,
    minimum_completed_races: int = 100,
    cross_validation_splits: int = 5,
    training_cutoff_date: (
        str | None
    ) = None,
    database_path: Path = DATABASE_PATH,
    model_path: Path = (
        INDEPENDENT_MODEL_PATH
    ),
    metadata_path: Path = (
        INDEPENDENT_METADATA_PATH
    ),
) -> dict[str, Any]:
    if (
        database_path.resolve()
        == DATABASE_PATH.resolve()
    ):
        initialize_database()

    resolved_cutoff_date = (
        resolve_independent_training_cutoff_date(
            training_cutoff_date
        )
    )
    training_summary = (
        get_independent_training_summary(
            database_path,
            cutoff_date=(
                resolved_cutoff_date
            ),
        )
    )
    dataframe = (
        build_independent_training_dataframe(
            database_path,
            cutoff_date=(
                resolved_cutoff_date
            ),
        )
    )

    if dataframe.empty:
        raise RuntimeError(
            "学習可能な結果確定レースがありません。"
        )

    dataframe = dataframe.reset_index(
        drop=True
    )
    race_count = int(
        dataframe["race_id"].nunique()
    )
    training_start_date = str(
        dataframe["race_date"]
        .astype(str)
        .min()
    )
    training_end_date = str(
        dataframe["race_date"]
        .astype(str)
        .max()
    )

    if race_count < int(
        minimum_completed_races
    ):
        raise RuntimeError(
            f"結果確定レースが{race_count}件です。"
            f"最低{minimum_completed_races}件を"
            "保存してから学習してください。"
        )

    feature_columns = (
        get_independent_feature_columns(
            dataframe
        )
    )

    if not feature_columns:
        raise RuntimeError(
            "学習特徴量がありません。"
        )

    forbidden_features = [
        column
        for column in feature_columns
        if any(
            word in column.lower()
            for word in FORBIDDEN_FEATURE_WORDS
        )
    ]

    if forbidden_features:
        raise RuntimeError(
            "オッズ関連特徴量を検出しました: "
            + "、".join(
                forbidden_features
            )
        )

    X = dataframe[
        feature_columns
    ].astype(float)
    y = dataframe["target"].astype(int)
    race_feature_rows = (
        dataframe.sort_values(
            [
                "race_date",
                "race_id",
            ]
        )
        .drop_duplicates(
            subset=["race_id"]
        )
    )
    rider_feature_rows = (
        dataframe.sort_values(
            [
                "race_date",
                "race_id",
                "first_car",
            ]
        )
        .drop_duplicates(
            subset=[
                "race_id",
                "first_car",
            ]
        )
    )
    feature_coverage = {
        "race_count": race_count,
        "venue_characteristics_races": int(
            race_feature_rows[
                "venue_characteristics_known"
            ].sum()
        ),
        "weather_known_races": int(
            race_feature_rows[
                "weather_known"
            ].sum()
        ),
        "scheduled_start_known_races": int(
            race_feature_rows[
                "scheduled_start_known"
            ].sum()
        ),
        "rider_observations": int(
            len(rider_feature_rows)
        ),
        "profile_known_rider_observations": int(
            rider_feature_rows[
                "first_profile_known"
            ].sum()
        ),
        "recent_history_rider_observations": int(
            rider_feature_rows[
                "first_has_prior_race"
            ].sum()
        ),
    }
    date_count = int(
        dataframe[
            "race_date"
        ].nunique()
    )
    split_count = min(
        int(cross_validation_splits),
        date_count - 1,
    )

    if split_count < 2:
        raise RuntimeError(
            "日付順検証には3開催日以上の"
            "学習データが必要です。"
        )

    out_of_fold_raw = np.full(
        len(dataframe),
        np.nan,
        dtype=float,
    )
    fold_results: list[
        dict[str, Any]
    ] = []

    for fold_number, (
        train_indices,
        validation_indices,
    ) in enumerate(
        chronological_race_splits(
            dataframe,
            split_count,
        ),
        start=1,
    ):
        model = _new_model(
            42 + fold_number
        )
        model.fit(
            X.iloc[train_indices],
            y.iloc[train_indices],
        )
        raw_probabilities = (
            _positive_class_probability(
                model,
                X.iloc[
                    validation_indices
                ],
            )
        )
        out_of_fold_raw[
            validation_indices
        ] = raw_probabilities

        validation_frame = (
            dataframe.iloc[
                validation_indices
            ].reset_index(drop=True)
        )
        normalized = normalize_by_race(
            validation_frame,
            raw_probabilities,
        )
        fold_metrics = (
            evaluate_independent_predictions(
                validation_frame,
                normalized,
            )
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
                    validation_frame[
                        "race_id"
                    ].nunique()
                ),
                **fold_metrics,
            }
        )

    evaluated_mask = ~np.isnan(
        out_of_fold_raw
    )
    evaluation_frame = (
        dataframe.loc[
            evaluated_mask
        ].reset_index(drop=True)
    )
    evaluation_raw = (
        out_of_fold_raw[
            evaluated_mask
        ]
    )
    evaluation_probabilities = (
        normalize_by_race(
            evaluation_frame,
            evaluation_raw,
        )
    )
    evaluation_metrics = (
        evaluate_independent_predictions(
            evaluation_frame,
            evaluation_probabilities,
        )
    )

    final_model = _new_model(42)
    final_model.fit(X, y)

    model_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    metadata_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    _backup_existing_models(
        model_path,
        metadata_path,
    )
    trained_at = datetime.now().isoformat(
        timespec="seconds"
    )
    model_package = {
        "model": final_model,
        "model_version": MODEL_VERSION,
        "model_type": (
            "odds_independent_trifecta"
        ),
        "odds_independent": True,
        "feature_columns": feature_columns,
        "trained_at": trained_at,
        "training_start_date": (
            training_start_date
        ),
        "training_end_date": (
            training_end_date
        ),
        "training_cutoff_date": (
            resolved_cutoff_date
        ),
        "excluded_after_cutoff_race_count": int(
            training_summary[
                "excluded_after_cutoff_races"
            ]
        ),
        "race_count": race_count,
        "row_count": len(dataframe),
        "feature_coverage": (
            feature_coverage
        ),
    }
    temporary_model_path = (
        model_path.with_suffix(
            model_path.suffix + ".tmp"
        )
    )
    joblib.dump(
        model_package,
        temporary_model_path,
    )
    temporary_model_path.replace(
        model_path
    )

    metadata = {
        "trained_at": trained_at,
        "training_start_date": (
            training_start_date
        ),
        "training_end_date": (
            training_end_date
        ),
        "training_cutoff_date": (
            resolved_cutoff_date
        ),
        "excluded_after_cutoff_race_count": int(
            training_summary[
                "excluded_after_cutoff_races"
            ]
        ),
        "model_version": MODEL_VERSION,
        "model_type": (
            "odds_independent_trifecta"
        ),
        "odds_independent": True,
        "race_count": race_count,
        "row_count": len(dataframe),
        "positive_rows": int(y.sum()),
        "feature_count": len(
            feature_columns
        ),
        "feature_groups": [
            "選手属性（選手ID・府県・級班・年齢・期別）",
            "競輪場特性（周長・みなし直線・最大カント）",
            "レース条件（グレード・勝ち上がり・日目・発走・距離・天候・風）",
            "直近成績（直前5走・10走・同場成績）",
            "並び（DOM構造・コメント整合・信頼度）",
        ],
        "feature_coverage": (
            feature_coverage
        ),
        "model_path": str(model_path),
        "excluded_inputs": [
            "3連単オッズ",
            "人気順位",
            "市場確率",
            "払戻金",
            "WINTICKET AI印",
        ],
        **evaluation_metrics,
        "fold_results": fold_results,
        "feature_columns": feature_columns,
    }
    temporary_metadata_path = (
        metadata_path.with_suffix(
            metadata_path.suffix + ".tmp"
        )
    )
    temporary_metadata_path.write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary_metadata_path.replace(
        metadata_path
    )

    return metadata
