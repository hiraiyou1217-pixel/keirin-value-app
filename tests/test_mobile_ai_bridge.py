from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = (
    ROOT
    / "android-fold5"
    / "app"
    / "src"
    / "main"
    / "python"
    / "mobile_ai_bridge.py"
)


def _load_bridge():
    spec = importlib.util.spec_from_file_location(
        "mobile_ai_bridge_test",
        BRIDGE_PATH,
    )
    module = importlib.util.module_from_spec(
        spec
    )
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MobileAiBridgeTest(unittest.TestCase):
    def test_parses_target_without_guessing(
        self,
    ) -> None:
        bridge = _load_bridge()
        target = bridge._target_details(
            "https://www.winticket.jp/keirin/"
            "aomori/racecard/2026073012/1/9"
        )

        self.assertEqual(
            target["race_date"],
            "2026-07-30",
        )
        self.assertEqual(
            target["venue"],
            "青森競輪",
        )
        self.assertEqual(
            target["race_number"],
            9,
        )

    def test_groups_geometry(
        self,
    ) -> None:
        bridge = _load_bridge()
        items = [
            {
                "number": number,
                "x": x,
                "y": 100,
                "width": 20,
                "height": 20,
                "groupKey": "",
            }
            for number, x in (
                (1, 0),
                (5, 24),
                (7, 48),
                (2, 90),
                (6, 114),
                (3, 160),
                (4, 184),
            )
        ]

        self.assertEqual(
            bridge.group_lineup_geometry(
                items,
                [1, 2, 3, 4, 5, 6, 7],
            ),
            [
                [1, 5, 7],
                [2, 6],
                [3, 4],
            ],
        )

    def test_predicts_all_combinations_locally(
        self,
    ) -> None:
        bridge = _load_bridge()

        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            database_path = directory / "learning.db"
            model_path = directory / "model.json"

            with sqlite3.connect(
                database_path
            ) as connection:
                connection.executescript(
                    """
                    CREATE TABLE races (
                        race_id TEXT,
                        race_date TEXT,
                        venue TEXT,
                        race_number INTEGER,
                        result_status TEXT,
                        first_place INTEGER,
                        second_place INTEGER,
                        third_place INTEGER
                    );
                    CREATE TABLE riders (
                        race_id TEXT
                    );
                    """
                )

            model_path.write_text(
                json.dumps(
                    {
                        "format": (
                            "keirin_hgb_binary_v1"
                        ),
                        "odds_independent": True,
                        "feature_columns": [
                            "first_car",
                            "second_car",
                            "third_car",
                        ],
                        "feature_count": 3,
                        "baseline": 0.0,
                        "trees": [
                            [
                                [
                                    0.0,
                                    0,
                                    0.0,
                                    False,
                                    0,
                                    0,
                                    True,
                                ]
                            ]
                        ],
                        "metadata": {
                            "training_end_date": (
                                "2026-07-29"
                            )
                        },
                    }
                ),
                encoding="utf-8",
            )
            riders = [
                {
                    "carNumber": number,
                    "name": f"検証選手{number}",
                    "profile": (
                        f"東京 A3 30歳 "
                        f"{120 + number}期"
                    ),
                    "score": 70 + number,
                    "style": (
                        "逃"
                        if number == 1
                        else "追"
                    ),
                    "s": number,
                    "h": number,
                    "b": number,
                    "winRate": 10.0,
                    "secondRate": 20.0,
                    "thirdRate": 30.0,
                    "comment": (
                        "自力。"
                        if number == 1
                        else "単騎。"
                    ),
                }
                for number in range(1, 8)
            ]
            lineup_items = [
                {
                    "number": number,
                    "x": x,
                    "y": 100,
                    "width": 20,
                    "height": 20,
                    "groupKey": "",
                }
                for number, x in (
                    (1, 0),
                    (5, 24),
                    (7, 48),
                    (2, 90),
                    (6, 114),
                    (3, 160),
                    (4, 184),
                )
            ]
            payload = {
                "pageTitle": (
                    "青森競輪 F2 1レース 出走表"
                ),
                "pageUrl": (
                    "https://www.winticket.jp/"
                    "keirin/aomori/racecard/"
                    "2026073012/1/1"
                ),
                "bodyText": (
                    "A級チャレンジ予選\n"
                    "発走 10:00\n"
                    "1,625m (4周) 晴 "
                    "25.0℃ 北 1.0m/s"
                ),
                "riders": riders,
                "lineupItems": lineup_items,
            }
            result = json.loads(
                bridge.predict_race(
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                    ),
                    str(model_path),
                    str(database_path),
                )
            )

        self.assertEqual(
            len(result["combinations"]),
            210,
        )
        self.assertAlmostEqual(
            sum(
                row["probability"]
                for row in result[
                    "combinations"
                ]
            ),
            1.0,
            places=12,
        )
        self.assertEqual(
            result["lineup_groups"],
            [
                [1, 5, 7],
                [2, 6],
                [3, 4],
            ],
        )
        self.assertEqual(
            len(result["riders"]),
            7,
        )


if __name__ == "__main__":
    unittest.main()
