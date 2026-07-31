from __future__ import annotations

import itertools
import json
import tempfile
import unittest
from pathlib import Path

import android_prediction_import
import learning_database


class AndroidPredictionImportTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.temporary = (
            tempfile.TemporaryDirectory()
        )
        self.original_database_path = (
            learning_database.DATABASE_PATH
        )
        learning_database.DATABASE_PATH = (
            Path(self.temporary.name)
            / "learning.db"
        )
        learning_database.initialize_database()
        self.drive_directory = (
            Path(self.temporary.name)
            / "KeirinAI"
        )
        self.drive_directory.mkdir()

    def tearDown(self) -> None:
        learning_database.DATABASE_PATH = (
            self.original_database_path
        )
        self.temporary.cleanup()

    def payload(
        self,
    ) -> dict[str, object]:
        car_numbers = [1, 2, 3, 4, 5]
        combinations = [
            "-".join(
                str(number)
                for number in combination
            )
            for combination in itertools.permutations(
                car_numbers,
                3,
            )
        ]
        probability = 1.0 / len(
            combinations
        )
        return {
            "format": (
                "keirin_android_prediction_v1"
            ),
            "prediction_id": (
                "mobile-prediction-001"
            ),
            "predicted_at": (
                "2026-07-31T08:00:00+09:00"
            ),
            "source_device": "android",
            "target": {
                "race_date": "2026-07-31",
                "venue": "青森競輪",
                "race_number": 1,
            },
            "combinations": [
                {
                    "combination": combination,
                    "rank": rank,
                    "probability": probability,
                }
                for rank, combination in enumerate(
                    combinations,
                    start=1,
                )
            ],
            "riders": [
                {
                    "car_number": number,
                    "name": f"選手{number}",
                }
                for number in car_numbers
            ],
            "model": {
                "model_version": 3,
                "trained_at": (
                    "2026-07-30T20:00:00"
                ),
                "training_start_date": (
                    "2026-01-01"
                ),
                "training_end_date": (
                    "2026-07-30"
                ),
                "training_cutoff_date": (
                    "2026-07-30"
                ),
            },
            "input_snapshot": {
                "riders": [
                    {
                        "車番": number,
                        "選手名": (
                            f"選手{number}"
                        ),
                    }
                    for number in car_numbers
                ],
                "race_conditions": {
                    "発走時刻": "10:00",
                },
            },
        }

    def write_payload(
        self,
        payload: dict[str, object],
        name: str = (
            "keirin_prediction_001.json"
        ),
    ) -> Path:
        path = self.drive_directory / name
        path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return path

    def test_imports_once_and_evaluates_result(
        self,
    ) -> None:
        riders = [
            {
                "車番": number,
                "選手名": f"選手{number}",
            }
            for number in range(1, 6)
        ]
        race_id = (
            learning_database
            .save_independent_race_snapshot(
                race_date="2026-07-31",
                venue="青森競輪",
                race_number=1,
                race_url=(
                    "https://example.invalid/"
                    "aomori/1"
                ),
                race_title="青森競輪 1R",
                riders=riders,
                lineup_groups=[
                    [1, 2],
                    [3, 4],
                    [5],
                ],
                race_conditions={
                    "発走時刻": "10:00",
                },
            )
        )
        self.write_payload(self.payload())

        first = (
            android_prediction_import
            .import_android_predictions(
                self.drive_directory
            )
        )
        second = (
            android_prediction_import
            .import_android_predictions(
                self.drive_directory
            )
        )

        self.assertEqual(
            first["imported_count"],
            1,
        )
        self.assertEqual(
            first["duplicate_count"],
            0,
        )
        self.assertEqual(
            second["imported_count"],
            0,
        )
        self.assertEqual(
            second["duplicate_count"],
            1,
        )
        self.assertTrue(
            first["records"][0][
                "evaluation_eligible"
            ]
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

        self.assertEqual(
            summary["official_count"],
            1,
        )
        self.assertEqual(
            summary["top1_hit_rate"],
            1.0,
        )
        self.assertEqual(
            summary["maximum_payout"],
            95960,
        )

    def test_rejects_incomplete_combinations(
        self,
    ) -> None:
        payload = self.payload()
        payload["combinations"] = list(
            payload["combinations"]
        )[:-1]
        path = self.write_payload(payload)

        with self.assertRaisesRegex(
            android_prediction_import
            .AndroidPredictionImportError,
            "不足",
        ):
            (
                android_prediction_import
                .prepare_prediction_file(path)
            )

    def test_preserves_pre_race_status_when_imported_after_result(
        self,
    ) -> None:
        riders = [
            {
                "車番": number,
                "選手名": f"選手{number}",
            }
            for number in range(1, 6)
        ]
        race_id = (
            learning_database
            .save_independent_race_snapshot(
                race_date="2026-07-31",
                venue="青森競輪",
                race_number=1,
                race_url=(
                    "https://example.invalid/"
                    "aomori/1"
                ),
                race_title="青森競輪 1R",
                riders=riders,
                lineup_groups=[
                    [1, 2],
                    [3, 4],
                    [5],
                ],
                race_conditions={
                    "発走時刻": "10:00",
                },
            )
        )
        learning_database.save_race_result(
            race_id=race_id,
            first_place=1,
            second_place=2,
            third_place=3,
            payout_per_100=95960,
        )
        self.write_payload(self.payload())

        result = (
            android_prediction_import
            .import_android_predictions(
                self.drive_directory
            )
        )
        summary = (
            learning_database
            .get_independent_evaluation_summary()
        )

        self.assertEqual(
            result["imported_count"],
            1,
        )
        self.assertTrue(
            result["records"][0][
                "evaluation_eligible"
            ]
        )
        self.assertEqual(
            summary["official_count"],
            1,
        )

    def test_keeps_failure_separate(
        self,
    ) -> None:
        path = (
            self.drive_directory
            / "keirin_prediction_bad.json"
        )
        path.write_text(
            "{broken",
            encoding="utf-8",
        )
        result = (
            android_prediction_import
            .import_android_predictions(
                self.drive_directory
            )
        )

        self.assertEqual(
            result["failed_count"],
            1,
        )
        self.assertEqual(
            result["imported_count"],
            0,
        )


if __name__ == "__main__":
    unittest.main()
