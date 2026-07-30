from __future__ import annotations

import itertools
from datetime import date, timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest

import pandas as pd

import independent_learning_features
import independent_model_prediction
import learning_database
import learning_features
import train_independent_model


class IndependentAiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = (
            tempfile.TemporaryDirectory()
        )
        self.root = Path(
            self.temporary.name
        )
        self.database_path = (
            self.root / "test.db"
        )
        self.original_database_path = (
            learning_database.DATABASE_PATH
        )
        learning_database.DATABASE_PATH = (
            self.database_path
        )

    def tearDown(self) -> None:
        learning_database.DATABASE_PATH = (
            self.original_database_path
        )
        self.temporary.cleanup()

    @staticmethod
    def riders(
        offset: int = 0,
    ) -> list[dict[str, object]]:
        comments = {
            1: "自力で先行します",
            2: "番手でマーク",
            3: "単騎で前々へ",
        }

        return [
            {
                "車番": number,
                "選手名": f"選手{number}",
                "選手ID": f"00010{number}",
                "府県": (
                    "青森"
                    if number == 1
                    else "東京"
                ),
                "級班": "A1",
                "年齢": 25 + number,
                "期別": 110 + number,
                "AI印": (
                    "本命"
                    if number == 1
                    else ""
                ),
                "競走得点": (
                    88.0
                    + number
                    + offset * 0.1
                ),
                "脚質": (
                    "逃"
                    if number == 1
                    else "追"
                ),
                "S": number,
                "H": number + offset,
                "B": number * 2,
                "勝率": (
                    10.0
                    + number
                    + offset
                ),
                "2連対率": (
                    20.0 + number
                ),
                "3連対率": (
                    30.0 + number
                ),
                "コメント": comments[
                    number
                ],
                "レースグレード": "F1",
                "レース区分": "A級予選",
                "レース級別": "A級",
                "開催日目": 1,
                "発走時刻": "10:30",
                "距離m": 2000,
                "周回数": 5,
                "天候": "晴",
                "気温C": 20.0,
                "風向": "北",
                "風速mps": 1.5,
                "並び取得方式": (
                    "DOM構造＋コメント確認"
                ),
                "並び信頼度": 0.95,
            }
            for number in (1, 2, 3)
        ]

    @staticmethod
    def odds(
        multiplier: float = 1.0,
    ) -> list[dict[str, object]]:
        return [
            {
                "組番": "-".join(
                    str(value)
                    for value in combination
                ),
                "人気": popularity,
                "オッズ": (
                    (10.0 + popularity)
                    * multiplier
                ),
            }
            for popularity, combination
            in enumerate(
                itertools.permutations(
                    (1, 2, 3),
                    3,
                ),
                start=1,
            )
        ]

    @staticmethod
    def evaluation_riders(
    ) -> list[dict[str, object]]:
        return [
            {
                "車番": number,
                "選手名": f"評価選手{number}",
                "AI印": "",
                "競走得点": 90.0 + number,
                "脚質": (
                    "逃"
                    if number == 1
                    else "追"
                ),
                "S": number,
                "H": number,
                "B": number,
                "勝率": 10.0 + number,
                "2連対率": 20.0 + number,
                "3連対率": 30.0 + number,
                "コメント": "",
            }
            for number in range(1, 6)
        ]

    @staticmethod
    def evaluation_prediction_rows(
        winning_rank: int = 27,
    ) -> list[dict[str, object]]:
        combinations = [
            "-".join(
                str(value)
                for value in combination
            )
            for combination in (
                itertools.permutations(
                    range(1, 6),
                    3,
                )
            )
        ]
        winner = "1-2-3"
        combinations.remove(winner)
        combinations.insert(
            int(winning_rank) - 1,
            winner,
        )
        probability = (
            1.0 / len(combinations)
        )

        return [
            {
                "予測順位": rank,
                "combination": combination,
                "AI確率": probability,
            }
            for rank, combination in enumerate(
                combinations,
                start=1,
            )
        ]

    def populate_races(
        self,
        race_count: int = 8,
    ) -> None:
        winners = list(
            itertools.permutations(
                (1, 2, 3),
                3,
            )
        )
        start = date(2026, 1, 1)

        for index in range(race_count):
            race_date = (
                start
                + timedelta(days=index)
            ).isoformat()
            race_id = (
                learning_database
                .save_race_snapshot(
                    race_date=race_date,
                    venue="テスト競輪",
                    race_number=(
                        index % 12
                    )
                    + 1,
                    race_url=(
                        "https://example.invalid/"
                        f"race/{index}"
                    ),
                    race_title=(
                        f"テスト {index + 1}R"
                    ),
                    riders=self.riders(
                        index
                    ),
                    odds_rows=self.odds(
                        index + 1
                    ),
                    lineup_groups=[
                        [1, 2],
                        [3],
                    ],
                    odds_complete=True,
                )
            )
            winner = winners[
                index % len(winners)
            ]
            learning_database.save_race_result(
                race_id=race_id,
                first_place=winner[0],
                second_place=winner[1],
                third_place=winner[2],
                payout_per_100=(
                    1000 + index
                ),
            )

    def test_features_ignore_odds_popularity_and_ai_marks(
        self,
    ) -> None:
        self.populate_races(3)
        before = (
            independent_learning_features
            .build_independent_training_dataframe(
                self.database_path
            )
        )
        feature_columns = (
            independent_learning_features
            .get_independent_feature_columns(
                before
            )
        )

        self.assertEqual(
            len(before),
            18,
        )
        self.assertTrue(
            all(
                group["target"].sum()
                == 1
                for _, group in (
                    before.groupby("race_id")
                )
            )
        )

        for column in feature_columns:
            lowered = column.lower()
            self.assertNotIn(
                "odds",
                lowered,
            )
            self.assertNotIn(
                "popularity",
                lowered,
            )
            self.assertNotIn(
                "market",
                lowered,
            )
            self.assertNotIn(
                "ai_mark",
                lowered,
            )
            self.assertNotIn(
                "payout",
                lowered,
            )

        with sqlite3.connect(
            self.database_path
        ) as connection:
            connection.execute(
                """
                UPDATE odds
                SET
                    odds = odds * 999,
                    popularity = (
                        1000 - popularity
                    )
                """
            )
            connection.execute(
                """
                UPDATE riders
                SET ai_mark = '単穴'
                """
            )
            connection.execute(
                """
                UPDATE races
                SET payout_per_100 = 999999
                """
            )

        after = (
            independent_learning_features
            .build_independent_training_dataframe(
                self.database_path
            )
        )
        pd.testing.assert_frame_equal(
            before,
            after,
        )

    def test_night_snapshot_is_only_used_by_independent_ai(
        self,
    ) -> None:
        race_id = (
            learning_database
            .save_independent_race_snapshot(
                race_date="2026-01-01",
                venue="テスト競輪",
                race_number=1,
                race_url=(
                    "https://example.invalid/"
                    "night-race"
                ),
                race_title="夜間取得",
                riders=self.riders(),
                lineup_groups=[
                    [1, 2],
                    [3],
                ],
            )
        )
        learning_database.save_race_result(
            race_id=race_id,
            first_place=1,
            second_place=2,
            third_place=3,
            payout_per_100=1230,
        )

        independent_frame = (
            independent_learning_features
            .build_independent_training_dataframe(
                self.database_path
            )
        )
        expected_value_frame = (
            learning_features
            .build_training_dataframe(
                self.database_path
            )
        )

        self.assertEqual(
            len(independent_frame),
            6,
        )
        self.assertTrue(
            expected_value_frame.empty
        )

    def test_excludes_races_after_training_cutoff(
        self,
    ) -> None:
        self.populate_races(4)
        dataframe = (
            independent_learning_features
            .build_independent_training_dataframe(
                self.database_path,
                cutoff_date="2026-01-03",
            )
        )
        summary = (
            independent_learning_features
            .get_independent_training_summary(
                self.database_path,
                cutoff_date="2026-01-03",
            )
        )

        self.assertEqual(
            dataframe[
                "race_id"
            ].nunique(),
            3,
        )
        self.assertEqual(
            set(
                dataframe[
                    "race_date"
                ].unique()
            ),
            {
                "2026-01-01",
                "2026-01-02",
                "2026-01-03",
            },
        )
        self.assertEqual(
            summary["completed_races"],
            3,
        )
        self.assertEqual(
            summary[
                "excluded_after_cutoff_races"
            ],
            1,
        )
        self.assertEqual(
            summary[
                "training_cutoff_date"
            ],
            "2026-01-03",
        )

    def test_recent_form_uses_only_prior_dates(
        self,
    ) -> None:
        self.populate_races(3)
        dataframe = (
            independent_learning_features
            .build_independent_training_dataframe(
                self.database_path,
                cutoff_date="2026-01-03",
            )
        )
        first_rider_by_date = (
            dataframe[
                dataframe["first_car"] == 1
            ]
            .sort_values("race_date")
            .drop_duplicates("race_date")
        )

        self.assertEqual(
            first_rider_by_date[
                "first_recent_starts_10"
            ].tolist(),
            [0.0, 1.0, 2.0],
        )
        self.assertEqual(
            first_rider_by_date[
                "first_has_prior_race"
            ].tolist(),
            [0.0, 1.0, 1.0],
        )

        current = (
            independent_learning_features
            .build_independent_current_dataframe(
                riders=self.riders(10),
                lineup_groups=[
                    [1, 2],
                    [3],
                ],
                race_date="2026-01-04",
                venue="青森競輪",
                race_number=1,
                race_conditions={
                    "レースグレード": "F1",
                    "レース区分": "A級予選",
                    "発走時刻": "10:30",
                },
                database_path=(
                    self.database_path
                ),
            )
        )
        current_first = current[
            current["first_car"] == 1
        ].iloc[0]

        self.assertEqual(
            current_first[
                "first_recent_starts_10"
            ],
            3.0,
        )
        self.assertEqual(
            current_first[
                "venue_characteristics_known"
            ],
            1.0,
        )
        self.assertEqual(
            current_first[
                "first_profile_known"
            ],
            1.0,
        )
        self.assertEqual(
            current_first[
                "lineup_confidence"
            ],
            0.95,
        )

    def test_same_date_results_do_not_leak(
        self,
    ) -> None:
        self.populate_races(2)
        race_id = (
            learning_database
            .save_independent_race_snapshot(
                race_date="2026-01-02",
                venue="青森競輪",
                race_number=9,
                race_url=(
                    "https://example.invalid/"
                    "same-date"
                ),
                race_title="同日別レース",
                riders=self.riders(20),
                lineup_groups=[
                    [1, 2],
                    [3],
                ],
            )
        )
        learning_database.save_race_result(
            race_id=race_id,
            first_place=1,
            second_place=2,
            third_place=3,
            payout_per_100=4320,
        )
        dataframe = (
            independent_learning_features
            .build_independent_training_dataframe(
                self.database_path,
                cutoff_date="2026-01-02",
            )
        )
        same_date_first = dataframe[
            (
                dataframe["race_date"]
                == "2026-01-02"
            )
            & (
                dataframe["first_car"]
                == 1
            )
        ]

        self.assertEqual(
            set(
                same_date_first[
                    "first_recent_starts_10"
                ]
            ),
            {1.0},
        )

    def test_trains_and_predicts_without_odds(
        self,
    ) -> None:
        self.populate_races(8)
        model_path = (
            self.root
            / "independent.joblib"
        )
        metadata_path = (
            self.root
            / "independent.json"
        )
        metadata = (
            train_independent_model
            .train_independent_model(
                minimum_completed_races=6,
                cross_validation_splits=2,
                training_cutoff_date=(
                    "2026-01-08"
                ),
                database_path=(
                    self.database_path
                ),
                model_path=model_path,
                metadata_path=(
                    metadata_path
                ),
            )
        )

        self.assertTrue(
            metadata[
                "odds_independent"
            ]
        )
        self.assertEqual(
            metadata["race_count"],
            8,
        )
        self.assertTrue(
            model_path.exists()
        )
        self.assertTrue(
            metadata_path.exists()
        )

        for feature in metadata[
            "feature_columns"
        ]:
            lowered = feature.lower()
            self.assertFalse(
                any(
                    word in lowered
                    for word in (
                        "odds",
                        "popularity",
                        "market",
                        "ai_mark",
                        "payout",
                    )
                )
            )

        (
            combinations,
            riders,
            prediction_metadata,
        ) = (
            independent_model_prediction
            .predict_independent_race(
                riders=self.riders(10),
                lineup_groups=[
                    [1, 2],
                    [3],
                ],
                race_id="current",
                race_date="2026-02-01",
                venue="テスト競輪",
                race_number=1,
                race_conditions={
                    "レースグレード": "F1",
                    "レース区分": "A級予選",
                    "発走時刻": "10:30",
                },
                database_path=(
                    self.database_path
                ),
                model_path=model_path,
            )
        )

        self.assertEqual(
            len(combinations),
            6,
        )
        self.assertAlmostEqual(
            float(
                combinations[
                    "AI確率"
                ].sum()
            ),
            1.0,
            places=10,
        )
        self.assertNotIn(
            "オッズ",
            combinations.columns,
        )
        self.assertNotIn(
            "人気",
            combinations.columns,
        )
        self.assertEqual(len(riders), 3)
        self.assertAlmostEqual(
            float(
                riders["1着確率"].sum()
            ),
            1.0,
            places=10,
        )
        self.assertAlmostEqual(
            float(
                riders["2着確率"].sum()
            ),
            1.0,
            places=10,
        )
        self.assertAlmostEqual(
            float(
                riders["3着確率"].sum()
            ),
            1.0,
            places=10,
        )
        self.assertTrue(
            prediction_metadata[
                "odds_independent"
            ]
        )
        self.assertEqual(
            metadata[
                "training_start_date"
            ],
            "2026-01-01",
        )
        self.assertEqual(
            metadata[
                "training_end_date"
            ],
            "2026-01-08",
        )
        self.assertEqual(
            metadata[
                "training_cutoff_date"
            ],
            "2026-01-08",
        )
        self.assertEqual(
            metadata[
                "excluded_after_cutoff_race_count"
            ],
            0,
        )
        self.assertEqual(
            prediction_metadata[
                "training_start_date"
            ],
            "2026-01-01",
        )
        self.assertEqual(
            prediction_metadata[
                "training_end_date"
            ],
            "2026-01-08",
        )
        self.assertEqual(
            prediction_metadata[
                "training_cutoff_date"
            ],
            "2026-01-08",
        )

    def test_freezes_first_prediction_and_self_evaluates_result(
        self,
    ) -> None:
        race_id = (
            learning_database
            .save_independent_race_snapshot(
                race_date="2026-07-10",
                venue="青森競輪",
                race_number=1,
                race_url=(
                    "https://example.invalid/"
                    "aomori/1"
                ),
                race_title="青森競輪 1R",
                riders=(
                    self.evaluation_riders()
                ),
                lineup_groups=[
                    [1, 2],
                    [3, 4],
                    [5],
                ],
            )
        )
        rows = (
            self.evaluation_prediction_rows(
                winning_rank=27
            )
        )
        metadata = {
            "model_version": 1,
            "trained_at": (
                "2026-07-09T20:00:00"
            ),
            "training_start_date": (
                "2026-01-01"
            ),
            "training_end_date": (
                "2026-07-09"
            ),
            "training_cutoff_date": (
                "2026-07-09"
            ),
            "excluded_after_cutoff_race_count": 2,
            "prediction_count": len(rows),
        }
        first = (
            learning_database
            .save_independent_prediction(
                race_date="2026-07-10",
                venue="青森競輪",
                race_number=1,
                prediction_rows=rows,
                model_metadata=metadata,
                input_snapshot={
                    "riders": (
                        self.evaluation_riders()
                    ),
                },
                predicted_at=(
                    "2026-07-10T08:00:00"
                ),
            )
        )
        duplicate = (
            learning_database
            .save_independent_prediction(
                race_date="2026-07-10",
                venue="青森競輪",
                race_number=1,
                prediction_rows=rows,
                model_metadata=metadata,
                predicted_at=(
                    "2026-07-10T09:00:00"
                ),
            )
        )
        second_model = {
            **metadata,
            "trained_at": (
                "2026-07-09T21:00:00"
            ),
        }
        second = (
            learning_database
            .save_independent_prediction(
                race_date="2026-07-10",
                venue="青森競輪",
                race_number=1,
                prediction_rows=rows,
                model_metadata=second_model,
                predicted_at=(
                    "2026-07-10T09:30:00"
                ),
            )
        )

        self.assertTrue(first["created"])
        self.assertTrue(
            first["evaluation_eligible"]
        )
        self.assertFalse(
            duplicate["created"]
        )
        self.assertTrue(second["created"])
        self.assertFalse(
            second["evaluation_eligible"]
        )
        self.assertIn(
            "初回のみ",
            second["eligibility_reason"],
        )

        learning_database.save_race_result(
            race_id=race_id,
            first_place=1,
            second_place=2,
            third_place=3,
            payout_per_100=95960,
        )
        summary = (
            learning_database
            .get_independent_evaluation_summary()
        )
        holes = (
            learning_database
            .get_independent_hole_hits()
        )
        history = (
            learning_database
            .get_recent_independent_evaluations()
        )

        self.assertEqual(
            summary["official_count"],
            1,
        )
        self.assertEqual(
            summary["reference_count"],
            1,
        )
        self.assertEqual(
            summary["top20_hit_rate"],
            0.0,
        )
        self.assertEqual(
            summary["top30_hit_rate"],
            1.0,
        )
        self.assertEqual(
            summary["mean_winner_rank"],
            27.0,
        )
        self.assertEqual(
            summary["maximum_payout"],
            95960,
        )
        self.assertEqual(len(holes), 1)
        self.assertEqual(
            holes[0]["winning_rank"],
            27,
        )
        self.assertEqual(len(history), 2)

        with learning_database.get_connection() as connection:
            frozen = connection.execute(
                """
                SELECT predicted_rank
                FROM independent_prediction_rows
                WHERE
                    run_id = ?
                    AND combination = '1-2-3'
                """,
                (first["run_id"],),
            ).fetchone()
            frozen_run = connection.execute(
                """
                SELECT
                    training_cutoff_date,
                    excluded_after_cutoff_race_count
                FROM independent_prediction_runs
                WHERE run_id = ?
                """,
                (first["run_id"],),
            ).fetchone()

        self.assertEqual(
            frozen["predicted_rank"],
            27,
        )
        self.assertEqual(
            frozen_run[
                "training_cutoff_date"
            ],
            "2026-07-09",
        )
        self.assertEqual(
            frozen_run[
                "excluded_after_cutoff_race_count"
            ],
            2,
        )
        detail = (
            learning_database
            .get_independent_prediction_detail(
                first["run_id"]
            )
        )

        self.assertIsNotNone(detail)
        self.assertEqual(
            len(detail["prediction_rows"]),
            60,
        )
        self.assertAlmostEqual(
            detail["probability_sum"],
            1.0,
        )
        winner_row = next(
            row
            for row in detail[
                "prediction_rows"
            ]
            if row["combination"]
            == "1-2-3"
        )
        self.assertEqual(
            winner_row["predicted_rank"],
            27,
        )
        self.assertTrue(
            winner_row["is_winner"]
        )
        self.assertEqual(
            len(
                detail[
                    "rider_probabilities"
                ]
            ),
            5,
        )
        self.assertEqual(
            {
                rider["rider_name"]
                for rider in detail[
                    "rider_probabilities"
                ]
            },
            {
                f"評価選手{number}"
                for number in range(1, 6)
            },
        )

        for rider in detail[
            "rider_probabilities"
        ]:
            self.assertAlmostEqual(
                rider[
                    "first_probability"
                ],
                0.2,
            )
            self.assertAlmostEqual(
                rider[
                    "second_probability"
                ],
                0.2,
            )
            self.assertAlmostEqual(
                rider[
                    "third_probability"
                ],
                0.2,
            )
            self.assertAlmostEqual(
                rider[
                    "top3_probability"
                ],
                0.6,
            )
        self.assertIsNone(
            learning_database
            .get_independent_prediction_detail(
                "missing-run"
            )
        )

    def test_excludes_training_period_prediction_from_official_score(
        self,
    ) -> None:
        race_id = (
            learning_database
            .save_independent_race_snapshot(
                race_date="2026-07-09",
                venue="伊東競輪",
                race_number=9,
                race_url=(
                    "https://example.invalid/"
                    "ito/9"
                ),
                race_title="伊東競輪 9R",
                riders=(
                    self.evaluation_riders()
                ),
                lineup_groups=[
                    [1, 2],
                    [3, 4],
                    [5],
                ],
            )
        )
        rows = (
            self.evaluation_prediction_rows(
                winning_rank=27
            )
        )
        record = (
            learning_database
            .save_independent_prediction(
                race_date="2026-07-09",
                venue="伊東競輪",
                race_number=9,
                prediction_rows=rows,
                model_metadata={
                    "model_version": 1,
                    "trained_at": (
                        "2026-07-10T08:00:00"
                    ),
                    "training_start_date": (
                        "2026-01-01"
                    ),
                    "training_end_date": (
                        "2026-07-09"
                    ),
                    "prediction_count": (
                        len(rows)
                    ),
                },
                predicted_at=(
                    "2026-07-10T09:00:00"
                ),
            )
        )
        summary_before_result = (
            learning_database
            .get_independent_evaluation_summary()
        )
        learning_database.save_race_result(
            race_id=race_id,
            first_place=1,
            second_place=2,
            third_place=3,
            payout_per_100=12340,
        )
        summary = (
            learning_database
            .get_independent_evaluation_summary()
        )

        self.assertFalse(
            record["evaluation_eligible"]
        )
        self.assertIn(
            "学習期間内",
            record["eligibility_reason"],
        )
        self.assertIn(
            "開催日より後",
            record["eligibility_reason"],
        )
        self.assertIn(
            "当日除外",
            record["eligibility_reason"],
        )
        self.assertEqual(
            summary_before_result[
                "reference_count"
            ],
            1,
        )
        self.assertEqual(
            summary_before_result[
                "pending_count"
            ],
            0,
        )
        self.assertEqual(
            summary["official_count"],
            0,
        )
        self.assertEqual(
            summary["reference_count"],
            1,
        )

    def test_uses_scheduled_start_for_official_evaluation(
        self,
    ) -> None:
        learning_database.save_independent_race_snapshot(
            race_date="2026-07-11",
            venue="青森競輪",
            race_number=2,
            race_url=(
                "https://example.invalid/"
                "aomori/2"
            ),
            race_title="青森競輪 2R",
            riders=self.evaluation_riders(),
            lineup_groups=[
                [1, 2],
                [3, 4],
                [5],
            ],
            race_conditions={
                "発走時刻": "09:00",
            },
        )
        rows = (
            self.evaluation_prediction_rows(
                winning_rank=10
            )
        )
        metadata = {
            "model_version": 1,
            "trained_at": (
                "2026-07-10T20:00:00"
            ),
            "training_start_date": (
                "2026-01-01"
            ),
            "training_end_date": (
                "2026-07-10"
            ),
            "training_cutoff_date": (
                "2026-07-10"
            ),
            "prediction_count": len(rows),
        }
        before_start = (
            learning_database
            .save_independent_prediction(
                race_date="2026-07-11",
                venue="青森競輪",
                race_number=2,
                prediction_rows=rows,
                model_metadata=metadata,
                predicted_at=(
                    "2026-07-11T08:59:00"
                ),
            )
        )
        after_start = (
            learning_database
            .save_independent_prediction(
                race_date="2026-07-11",
                venue="青森競輪",
                race_number=2,
                prediction_rows=rows,
                model_metadata={
                    **metadata,
                    "trained_at": (
                        "2026-07-10T21:00:00"
                    ),
                },
                predicted_at=(
                    "2026-07-11T09:01:00"
                ),
            )
        )

        self.assertTrue(
            before_start[
                "evaluation_eligible"
            ]
        )
        self.assertFalse(
            after_start[
                "evaluation_eligible"
            ]
        )
        self.assertIn(
            "発走時刻以後",
            after_start[
                "eligibility_reason"
            ],
        )

    def test_marks_prediction_review_when_result_needs_review(
        self,
    ) -> None:
        race_id = (
            learning_database
            .save_independent_race_snapshot(
                race_date="2026-07-11",
                venue="青森競輪",
                race_number=2,
                race_url=(
                    "https://example.invalid/"
                    "aomori/2"
                ),
                race_title="青森競輪 2R",
                riders=(
                    self.evaluation_riders()
                ),
                lineup_groups=[
                    [1, 2],
                    [3, 4],
                    [5],
                ],
            )
        )
        rows = (
            self.evaluation_prediction_rows(
                winning_rank=27
            )
        )
        record = (
            learning_database
            .save_independent_prediction(
                race_date="2026-07-11",
                venue="青森競輪",
                race_number=2,
                prediction_rows=rows,
                model_metadata={
                    "model_version": 1,
                    "trained_at": (
                        "2026-07-10T20:00:00"
                    ),
                    "training_start_date": (
                        "2026-01-01"
                    ),
                    "training_end_date": (
                        "2026-07-10"
                    ),
                    "training_cutoff_date": (
                        "2026-07-10"
                    ),
                    "prediction_count": (
                        len(rows)
                    ),
                },
                predicted_at=(
                    "2026-07-11T08:00:00"
                ),
            )
        )

        saved = (
            learning_database
            .save_race_review(
                race_id=race_id,
                reason="同着のため要確認",
            )
        )
        summary = (
            learning_database
            .get_independent_evaluation_summary()
        )
        history = (
            learning_database
            .get_recent_independent_evaluations()
        )

        self.assertTrue(
            record["evaluation_eligible"]
        )
        self.assertTrue(saved)
        self.assertEqual(
            summary["official_count"],
            0,
        )
        self.assertEqual(
            summary["review_count"],
            1,
        )
        self.assertEqual(
            history[0]["result_status"],
            "要確認",
        )
        self.assertIsNone(
            history[0]["winning_rank"]
        )


if __name__ == "__main__":
    unittest.main()
