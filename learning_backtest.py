from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from learning_database import DATABASE_PATH
from learning_features import (
    build_training_dataframe,
    get_feature_columns,
)


@dataclass
class BacktestRaceResult:
    race_id: str
    race_date: str
    venue: str
    race_number: int
    winning_combination: str
    selected_combinations: str
    selected_count: int
    purchase_amount: int
    payout_amount: int
    profit: int
    hit: bool
    winner_prediction_rank: int
    winner_probability: float
    winner_expected_return: float


def _normalize(
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


def _load_payout_map(
    database_path: Path,
) -> dict[str, dict[str, Any]]:
    if not database_path.exists():
        return {}

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute(
            """
            SELECT
                race_id,
                winning_combination,
                payout_per_100
            FROM races
            WHERE
                result_status = '確定'
                AND winning_combination IS NOT NULL
            """
        ).fetchall()

        return {
            str(row["race_id"]): {
                "winning_combination": str(
                    row["winning_combination"]
                ),
                "payout_per_100": (
                    int(row["payout_per_100"])
                    if row["payout_per_100"]
                    is not None
                    else None
                ),
            }
            for row in rows
        }

    finally:
        connection.close()


def _build_model() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        loss="log_loss",
        learning_rate=0.05,
        max_iter=200,
        max_leaf_nodes=15,
        min_samples_leaf=30,
        l2_regularization=1.0,
        early_stopping=True,
        random_state=42,
    )


def run_walk_forward_backtest(
    *,
    database_path: Path = DATABASE_PATH,
    minimum_training_races: int = 30,
    maximum_test_races: int = 100,
    market_blend: float = 0.25,
    minimum_expected_return: float = 1.10,
    maximum_odds: float = 300.0,
    maximum_bets_per_race: int = 5,
    stake_per_bet: int = 100,
) -> dict[str, Any]:
    dataframe = build_training_dataframe(
        database_path
    )

    if dataframe.empty:
        raise RuntimeError(
            "結果確定済みの学習データがありません。"
        )

    payout_map = _load_payout_map(
        database_path
    )

    race_information = (
        dataframe[
            [
                "race_id",
                "race_date",
                "venue",
                "race_number",
            ]
        ]
        .drop_duplicates("race_id")
        .sort_values(
            [
                "race_date",
                "venue",
                "race_number",
            ]
        )
        .reset_index(drop=True)
    )

    total_races = len(race_information)

    if total_races <= minimum_training_races:
        raise RuntimeError(
            f"結果確定レースが{total_races}件です。"
            f"最低でも{minimum_training_races + 1}件"
            "必要です。"
        )

    test_races = race_information.iloc[
        minimum_training_races:
    ].copy()

    if maximum_test_races > 0:
        test_races = test_races.tail(
            int(maximum_test_races)
        )

    feature_columns = get_feature_columns(
        dataframe
    )

    safe_market_blend = max(
        0.0,
        min(0.90, float(market_blend)),
    )

    results: list[BacktestRaceResult] = []
    skipped_no_payout = 0
    skipped_invalid = 0

    for _, test_race in test_races.iterrows():
        test_race_id = str(
            test_race["race_id"]
        )

        test_date = str(
            test_race["race_date"]
        )

        # 開催日がテスト対象より前のレースだけで学習する。
        training_race_ids = race_information.loc[
            race_information["race_date"] < test_date,
            "race_id",
        ].astype(str)

        if (
            training_race_ids.nunique()
            < minimum_training_races
        ):
            continue

        training_rows = dataframe[
            dataframe["race_id"].astype(str).isin(
                set(training_race_ids)
            )
        ].copy()

        test_rows = dataframe[
            dataframe["race_id"].astype(str)
            == test_race_id
        ].copy()

        if training_rows.empty or test_rows.empty:
            skipped_invalid += 1
            continue

        # 100円あたりの確定払戻がないレースは、
        # 実収支を正しく計算できないため除外する。
        payout_information = payout_map.get(
            test_race_id,
            {},
        )

        payout_per_100 = payout_information.get(
            "payout_per_100"
        )

        winning_combination = str(
            payout_information.get(
                "winning_combination",
                "",
            )
        )

        if (
            payout_per_100 is None
            or not winning_combination
        ):
            skipped_no_payout += 1
            continue

        X_train = training_rows[
            feature_columns
        ].astype(float)

        y_train = training_rows[
            "target"
        ].astype(int)

        X_test = test_rows[
            feature_columns
        ].astype(float)

        if y_train.nunique() < 2:
            skipped_invalid += 1
            continue

        model = _build_model()
        model.fit(X_train, y_train)

        raw_model_probability = (
            model.predict_proba(X_test)[:, 1]
        )

        model_probability = _normalize(
            raw_model_probability
        )

        odds_values = test_rows[
            "odds"
        ].astype(float).to_numpy()

        market_probability = _normalize(
            1.0 / odds_values
        )

        blended_raw = (
            np.power(
                np.maximum(
                    model_probability,
                    1e-15,
                ),
                1.0 - safe_market_blend,
            )
            * np.power(
                np.maximum(
                    market_probability,
                    1e-15,
                ),
                safe_market_blend,
            )
        )

        final_probability = _normalize(
            blended_raw
        )

        prediction = test_rows[
            [
                "combination",
                "popularity",
                "odds",
            ]
        ].copy()

        prediction["model_probability"] = (
            model_probability
        )

        prediction["market_probability"] = (
            market_probability
        )

        prediction["final_probability"] = (
            final_probability
        )

        prediction["expected_return"] = (
            prediction["final_probability"]
            * prediction["odds"].astype(float)
        )

        probability_order = prediction.sort_values(
            "final_probability",
            ascending=False,
        ).reset_index(drop=True)

        winner_positions = probability_order.index[
            probability_order["combination"]
            == winning_combination
        ].tolist()

        if winner_positions:
            winner_position = winner_positions[0]
            winner_rank = int(
                winner_position + 1
            )

            winner_probability = float(
                probability_order.loc[
                    winner_position,
                    "final_probability",
                ]
            )

            winner_expected_return = float(
                probability_order.loc[
                    winner_position,
                    "expected_return",
                ]
            )
        else:
            winner_rank = 0
            winner_probability = 0.0
            winner_expected_return = 0.0

        candidates = prediction[
            (
                prediction["expected_return"]
                >= float(
                    minimum_expected_return
                )
            )
            & (
                prediction["odds"]
                <= float(maximum_odds)
            )
        ].copy()

        candidates = candidates.sort_values(
            [
                "expected_return",
                "final_probability",
            ],
            ascending=[
                False,
                False,
            ],
        ).head(
            int(maximum_bets_per_race)
        )

        selected_combinations = (
            candidates["combination"]
            .astype(str)
            .tolist()
        )

        selected_count = len(
            selected_combinations
        )

        purchase_amount = (
            selected_count
            * int(stake_per_bet)
        )

        hit = (
            winning_combination
            in selected_combinations
        )

        payout_amount = 0

        if hit:
            payout_amount = int(
                int(payout_per_100)
                * (
                    int(stake_per_bet)
                    / 100
                )
            )

        profit = (
            payout_amount
            - purchase_amount
        )

        results.append(
            BacktestRaceResult(
                race_id=test_race_id,
                race_date=test_date,
                venue=str(
                    test_race["venue"]
                ),
                race_number=int(
                    test_race["race_number"]
                ),
                winning_combination=(
                    winning_combination
                ),
                selected_combinations=(
                    " / ".join(
                        selected_combinations
                    )
                ),
                selected_count=selected_count,
                purchase_amount=purchase_amount,
                payout_amount=payout_amount,
                profit=profit,
                hit=bool(hit),
                winner_prediction_rank=(
                    winner_rank
                ),
                winner_probability=(
                    winner_probability
                ),
                winner_expected_return=(
                    winner_expected_return
                ),
            )
        )

    result_dataframe = pd.DataFrame(
        [
            asdict(result)
            for result in results
        ]
    )

    if result_dataframe.empty:
        raise RuntimeError(
            "バックテスト対象レースがありません。"
            "確定払戻を登録したレースを"
            "増やしてください。"
        )

    total_purchase = int(
        result_dataframe[
            "purchase_amount"
        ].sum()
    )

    total_payout = int(
        result_dataframe[
            "payout_amount"
        ].sum()
    )

    total_profit = (
        total_payout - total_purchase
    )

    betting_races = int(
        (
            result_dataframe[
                "selected_count"
            ] > 0
        ).sum()
    )

    hit_count = int(
        result_dataframe["hit"].sum()
    )

    return_rate = (
        total_payout / total_purchase
        if total_purchase > 0
        else 0.0
    )

    hit_rate = (
        hit_count / betting_races
        if betting_races > 0
        else 0.0
    )

    top1_rate = float(
        (
            result_dataframe[
                "winner_prediction_rank"
            ] == 1
        ).mean()
    )

    top3_rate = float(
        (
            result_dataframe[
                "winner_prediction_rank"
            ].between(1, 3)
        ).mean()
    )

    summary = {
        "evaluated_races": len(
            result_dataframe
        ),
        "betting_races": betting_races,
        "hit_count": hit_count,
        "hit_rate": hit_rate,
        "total_purchase": total_purchase,
        "total_payout": total_payout,
        "total_profit": total_profit,
        "return_rate": return_rate,
        "top1_rate": top1_rate,
        "top3_rate": top3_rate,
        "mean_winner_rank": float(
            result_dataframe[
                "winner_prediction_rank"
            ]
            .replace(0, np.nan)
            .mean()
        ),
        "skipped_no_payout": (
            skipped_no_payout
        ),
        "skipped_invalid": skipped_invalid,
        "minimum_training_races": int(
            minimum_training_races
        ),
        "market_blend": (
            safe_market_blend
        ),
        "minimum_expected_return": float(
            minimum_expected_return
        ),
        "maximum_odds": float(
            maximum_odds
        ),
        "maximum_bets_per_race": int(
            maximum_bets_per_race
        ),
        "stake_per_bet": int(
            stake_per_bet
        ),
    }

    return {
        "summary": summary,
        "races": result_dataframe,
    }
