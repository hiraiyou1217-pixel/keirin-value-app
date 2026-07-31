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
from sklearn.linear_model import (
    LogisticRegression,
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
from portable_independent_model import (
    apply_probability_calibration,
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
MODEL_VERSION = 4


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
    top30_hits = 0
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
        top30_hits += int(
            winner_rank <= 30
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
        "top30_hit_rate": (
            top30_hits / evaluated_races
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


def fit_probability_calibration(
    raw_probabilities: np.ndarray,
    targets: np.ndarray,
) -> dict[str, Any]:
    clipped = np.clip(
        np.asarray(
            raw_probabilities,
            dtype=float,
        ),
        1e-15,
        1.0 - 1e-15,
    )
    labels = np.asarray(
        targets,
        dtype=int,
    )

    if (
        len(clipped) == 0
        or len(np.unique(labels)) < 2
    ):
        return {
            "method": "identity",
            "sample_count": int(
                len(clipped)
            ),
            "reason": (
                "校正に必要な2クラスが"
                "揃っていません。"
            ),
        }

    logits = np.log(
        clipped / (1.0 - clipped)
    ).reshape(-1, 1)
    calibrator = LogisticRegression(
        C=1.0,
        solver="lbfgs",
        max_iter=1000,
        random_state=42,
    )
    calibrator.fit(logits, labels)
    coefficient = float(
        calibrator.coef_[0][0]
    )

    if coefficient <= 0.0:
        return {
            "method": "identity",
            "sample_count": int(
                len(clipped)
            ),
            "positive_count": int(
                labels.sum()
            ),
            "reason": (
                "校正係数が正でないため"
                "順位反転を避けて未校正を採用"
            ),
        }

    return {
        "method": "platt_logit",
        "coefficient": coefficient,
        "intercept": float(
            calibrator.intercept_[0]
        ),
        "sample_count": int(
            len(clipped)
        ),
        "positive_count": int(
            labels.sum()
        ),
    }


def calibration_quality(
    targets: np.ndarray,
    before: np.ndarray,
    after: np.ndarray,
) -> dict[str, float]:
    labels = np.asarray(
        targets,
        dtype=float,
    )
    before_values = np.clip(
        np.asarray(before, dtype=float),
        1e-15,
        1.0 - 1e-15,
    )
    after_values = np.clip(
        np.asarray(after, dtype=float),
        1e-15,
        1.0 - 1e-15,
    )

    def binary_log_loss(
        values: np.ndarray,
    ) -> float:
        return float(
            -np.mean(
                labels * np.log(values)
                + (
                    1.0 - labels
                )
                * np.log(1.0 - values)
            )
        )

    return {
        "binary_log_loss_before": (
            binary_log_loss(
                before_values
            )
        ),
        "binary_log_loss_after": (
            binary_log_loss(
                after_values
            )
        ),
        "brier_score_before": float(
            np.mean(
                (
                    before_values
                    - labels
                )
                ** 2
            )
        ),
        "brier_score_after": float(
            np.mean(
                (
                    after_values
                    - labels
                )
                ** 2
            )
        ),
    }


def evaluate_segmented_predictions(
    dataframe: pd.DataFrame,
    probabilities: np.ndarray,
) -> dict[str, list[dict[str, Any]]]:
    race_rows = (
        dataframe.reset_index(drop=True)
        .drop_duplicates("race_id")
        .set_index("race_id")
    )
    grade_names = {
        0: "不明",
        1: "F2",
        2: "F1",
        3: "G3",
        4: "G2",
        5: "G1",
        6: "GP",
    }
    conditions: dict[
        str,
        dict[str, str]
    ] = {
        "競輪場": {
            race_id: str(row["venue"])
            for race_id, row
            in race_rows.iterrows()
        },
        "出走数": {
            race_id: (
                f"{int(row['rider_count'])}車"
            )
            for race_id, row
            in race_rows.iterrows()
        },
        "グレード": {
            race_id: grade_names.get(
                int(
                    round(
                        float(
                            row[
                                "race_grade_ordinal"
                            ]
                        )
                    )
                ),
                "不明",
            )
            for race_id, row
            in race_rows.iterrows()
        },
        "発走帯": {
            race_id: (
                "時刻不明"
                if not bool(
                    row[
                        "scheduled_start_known"
                    ]
                )
                else (
                    "午前"
                    if float(
                        row[
                            "scheduled_start_hour"
                        ]
                    )
                    < 12
                    else (
                        "午後"
                        if float(
                            row[
                                "scheduled_start_hour"
                            ]
                        )
                        < 17
                        else "ナイター"
                    )
                )
            )
            for race_id, row
            in race_rows.iterrows()
        },
        "並び信頼度": {
            race_id: (
                "高"
                if float(
                    row["lineup_confidence"]
                )
                >= 0.85
                else (
                    "中"
                    if float(
                        row[
                            "lineup_confidence"
                        ]
                    )
                    >= 0.60
                    else "低"
                )
            )
            for race_id, row
            in race_rows.iterrows()
        },
    }
    output: dict[
        str,
        list[dict[str, Any]]
    ] = {}
    race_ids = dataframe[
        "race_id"
    ].astype(str)

    for dimension, labels in (
        conditions.items()
    ):
        rows: list[dict[str, Any]] = []

        for label in sorted(
            set(labels.values())
        ):
            selected_races = {
                race_id
                for race_id, value
                in labels.items()
                if value == label
            }
            mask = race_ids.isin(
                selected_races
            ).to_numpy()
            metrics = (
                evaluate_independent_predictions(
                    dataframe.loc[
                        mask
                    ].reset_index(drop=True),
                    np.asarray(
                        probabilities
                    )[mask],
                )
            )
            rows.append(
                {
                    "condition": label,
                    **metrics,
                }
            )

        output[dimension] = rows

    return output


def decide_model_promotion(
    candidate: dict[str, Any],
    incumbent: dict[str, Any] | None,
) -> dict[str, Any]:
    if not incumbent:
        return {
            "promoted": True,
            "decision": "initial_model",
            "reason": (
                "有効な現行モデルがないため"
                "初回モデルとして採用"
            ),
            "checks": {},
        }

    required = (
        "race_log_loss",
        "mean_winner_rank",
        "top10_hit_rate",
    )

    if any(
        key not in incumbent
        for key in required
    ):
        return {
            "promoted": True,
            "decision": (
                "incumbent_metrics_missing"
            ),
            "reason": (
                "現行モデルに比較指標がないため"
                "検証済み候補を採用"
            ),
            "checks": {},
        }

    candidate_loss = float(
        candidate["race_log_loss"]
    )
    incumbent_loss = float(
        incumbent["race_log_loss"]
    )
    candidate_rank = float(
        candidate["mean_winner_rank"]
    )
    incumbent_rank = float(
        incumbent["mean_winner_rank"]
    )
    candidate_top10 = float(
        candidate["top10_hit_rate"]
    )
    incumbent_top10 = float(
        incumbent["top10_hit_rate"]
    )
    checks = {
        "log_loss_guardrail": (
            candidate_loss
            <= incumbent_loss * 1.02
        ),
        "winner_rank_guardrail": (
            candidate_rank
            <= incumbent_rank + 1.0
        ),
        "top10_guardrail": (
            candidate_top10
            >= incumbent_top10 - 0.01
        ),
        "at_least_one_improvement": (
            candidate_loss < incumbent_loss
            or candidate_rank
            < incumbent_rank
            or candidate_top10
            > incumbent_top10
        ),
    }
    promoted = all(checks.values())

    return {
        "promoted": promoted,
        "decision": (
            "promote"
            if promoted
            else "keep_incumbent"
        ),
        "reason": (
            "主要3指標の悪化上限を守り、"
            "少なくとも1指標が改善"
            if promoted
            else (
                "現行モデルより客観指標が"
                "改善しなかったため候補保存"
            )
        ),
        "checks": checks,
        "candidate": {
            key: float(candidate[key])
            for key in required
        },
        "incumbent": {
            key: float(incumbent[key])
            for key in required
        },
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
    uncalibrated_probabilities = (
        normalize_by_race(
            evaluation_frame,
            evaluation_raw,
        )
    )
    probability_calibration = (
        fit_probability_calibration(
            evaluation_raw,
            evaluation_frame[
                "target"
            ].to_numpy(),
        )
    )
    calibrated_raw = np.asarray(
        apply_probability_calibration(
            evaluation_raw,
            probability_calibration,
        ),
        dtype=float,
    )
    evaluation_probabilities = (
        normalize_by_race(
            evaluation_frame,
            calibrated_raw,
        )
    )
    uncalibrated_metrics = (
        evaluate_independent_predictions(
            evaluation_frame,
            uncalibrated_probabilities,
        )
    )
    evaluation_metrics = (
        evaluate_independent_predictions(
            evaluation_frame,
            evaluation_probabilities,
        )
    )
    calibration_metrics = (
        calibration_quality(
            evaluation_frame[
                "target"
            ].to_numpy(),
            evaluation_raw,
            calibrated_raw,
        )
    )
    segmented_metrics = (
        evaluate_segmented_predictions(
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
        "probability_calibration": (
            probability_calibration
        ),
    }

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
        "uncalibrated_evaluation": (
            uncalibrated_metrics
        ),
        "probability_calibration": (
            probability_calibration
        ),
        "calibration_metrics": (
            calibration_metrics
        ),
        "segmented_evaluation": (
            segmented_metrics
        ),
        "fold_results": fold_results,
        "feature_columns": feature_columns,
    }

    incumbent_metadata: (
        dict[str, Any] | None
    ) = None

    if (
        model_path.exists()
        and metadata_path.exists()
    ):
        try:
            loaded_incumbent = json.loads(
                metadata_path.read_text(
                    encoding="utf-8"
                )
            )

            if isinstance(
                loaded_incumbent,
                dict,
            ):
                incumbent_metadata = (
                    loaded_incumbent
                )
        except (
            OSError,
            json.JSONDecodeError,
        ):
            incumbent_metadata = None

    promotion = decide_model_promotion(
        metadata,
        incumbent_metadata,
    )
    metadata["promotion"] = promotion
    metadata["promoted"] = bool(
        promotion["promoted"]
    )
    model_package["promotion"] = promotion

    if metadata["promoted"]:
        _backup_existing_models(
            model_path,
            metadata_path,
        )
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
    else:
        candidate_directory = (
            model_path.parent
            / "candidates"
        )
        candidate_directory.mkdir(
            parents=True,
            exist_ok=True,
        )
        candidate_stamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )
        candidate_model_path = (
            candidate_directory
            / (
                f"{model_path.stem}_"
                f"{candidate_stamp}"
                f"{model_path.suffix}"
            )
        )
        candidate_metadata_path = (
            candidate_directory
            / (
                f"{metadata_path.stem}_"
                f"{candidate_stamp}"
                f"{metadata_path.suffix}"
            )
        )
        metadata["model_path"] = str(
            candidate_model_path
        )
        metadata["candidate_metadata_path"] = str(
            candidate_metadata_path
        )
        metadata["active_model_path"] = str(
            model_path
        )
        joblib.dump(
            model_package,
            candidate_model_path,
        )
        candidate_metadata_path.write_text(
            json.dumps(
                metadata,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    return metadata
