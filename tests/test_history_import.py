from __future__ import annotations

import itertools
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import history_catalog
import history_import_worker
import learning_database
import odds_http


class CatalogParserTest(unittest.TestCase):
    def test_discovers_and_deduplicates_result_urls(
        self,
    ) -> None:
        html = """
        <a href="/keirin/toyohashi/raceresult/2026072545/4/1">1R</a>
        <a href="/keirin/toyohashi/raceresult/2026072545/4/1">1R duplicate</a>
        <a href="/keirin/toride/raceresult/2026072623/3/2?x=1">2R</a>
        <a href="/keirin/toride/racecard/2026072623/3/3">not result</a>
        """

        entries = (
            history_catalog
            .parse_result_catalog_html(
                html,
                "2026-07-28",
            )
        )

        self.assertEqual(len(entries), 2)
        self.assertEqual(
            {
                (
                    item["venue"],
                    item["race_number"],
                )
                for item in entries
            },
            {
                ("豊橋競輪", 1),
                ("取手競輪", 2),
            },
        )
        self.assertTrue(
            all(
                "/racecard/"
                in item["racecard_url"]
                for item in entries
            )
        )

    def test_maps_iwakidaira_slug_to_japanese_venue(
        self,
    ) -> None:
        html = """
        <a href="/keirin/iwakidaira/raceresult/2026072213/1/1">
            1R
        </a>
        """

        entries = (
            history_catalog
            .parse_result_catalog_html(
                html,
                "2026-07-22",
            )
        )

        self.assertEqual(len(entries), 1)
        self.assertEqual(
            entries[0]["venue"],
            "いわき平競輪",
        )


class OddsHttpParserTest(unittest.TestCase):
    def test_extracts_exact_trifecta_from_preloaded_state(
        self,
    ) -> None:
        html = """
        <script>
        window.__PRELOADED_STATE__ = {
            "queries": [{
                "state": {
                    "data": {
                        "trifecta": [
                            {
                                "type": 2,
                                "key": [1, 2, 3],
                                "odds": 5.9,
                                "popularityOrder": 2
                            },
                            {
                                "type": 2,
                                "key": [1, 3, 2],
                                "oddsStr": "8.4",
                                "popularityOrder": 4
                            }
                        ],
                        "trio": [
                            {
                                "type": 3,
                                "key": [1, 2, 3],
                                "odds": 2.1,
                                "popularityOrder": 1
                            }
                        ]
                    }
                }
            }]
        };
        window.__CONFIG__ = {};
        </script>
        """

        blobs = odds_http.extract_json_blobs(
            html
        )
        output: dict[
            str,
            dict[str, object],
        ] = {}

        for blob in blobs:
            odds_http.extract_trifecta_arrays(
                blob,
                output,
            )

        self.assertEqual(
            output,
            {
                "1-2-3": {
                    "組番": "1-2-3",
                    "オッズ": 5.9,
                    "人気": 2,
                },
                "1-3-2": {
                    "組番": "1-3-2",
                    "オッズ": 8.4,
                    "人気": 4,
                },
            },
        )


class WorkerOddsFallbackTest(unittest.TestCase):
    @staticmethod
    def riders() -> list[dict[str, object]]:
        return [
            {
                "車番": number,
            }
            for number in (1, 2, 3)
        ]

    @staticmethod
    def odds() -> list[dict[str, object]]:
        return [
            {
                "組番": "-".join(
                    str(value)
                    for value in combination
                ),
                "人気": popularity,
                "オッズ": float(
                    10 + popularity
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
    def entry() -> dict[str, object]:
        return {
            "racecard_url": (
                "https://www.winticket.jp/"
                "keirin/test/racecard/"
                "2026072201/1/1"
            ),
        }

    @patch.object(
        history_import_worker,
        "fetch_lineup_browser",
        return_value=(
            [[1, 2], [3]],
            [],
        ),
    )
    @patch.object(
        history_import_worker,
        "fetch_all_trifecta_odds_browser",
    )
    @patch.object(
        history_import_worker,
        "fetch_trifecta_odds_http",
    )
    @patch.object(
        history_import_worker,
        "fetch_racecard_data_browser",
    )
    def test_uses_complete_http_odds_without_dom(
        self,
        racecard_mock,
        http_mock,
        dom_mock,
        _lineup_mock,
    ) -> None:
        racecard_mock.return_value = (
            self.riders(),
            [],
        )
        http_mock.return_value = (
            self.odds(),
            [],
        )

        _, odds_rows, _, odds_complete = (
            history_import_worker
            ._collect_learning_snapshot(
                self.entry()
            )
        )

        self.assertEqual(len(odds_rows), 6)
        self.assertTrue(odds_complete)
        dom_mock.assert_not_called()

    @patch.object(
        history_import_worker,
        "fetch_lineup_browser",
        return_value=(
            [[1, 2], [3]],
            [],
        ),
    )
    @patch.object(
        history_import_worker,
        "fetch_all_trifecta_odds_browser",
    )
    @patch.object(
        history_import_worker,
        "fetch_trifecta_odds_http",
        return_value=([], []),
    )
    @patch.object(
        history_import_worker,
        "fetch_racecard_data_browser",
    )
    def test_falls_back_to_dom_when_http_is_incomplete(
        self,
        racecard_mock,
        _http_mock,
        dom_mock,
        _lineup_mock,
    ) -> None:
        racecard_mock.return_value = (
            self.riders(),
            [],
        )
        dom_mock.return_value = (
            self.odds(),
            [],
        )

        _, odds_rows, _, odds_complete = (
            history_import_worker
            ._collect_learning_snapshot(
                self.entry()
            )
        )

        self.assertEqual(len(odds_rows), 6)
        self.assertTrue(odds_complete)
        dom_mock.assert_called_once()

    @patch.object(
        history_import_worker,
        "fetch_lineup_browser",
        return_value=(
            [[1, 2], [3]],
            [],
        ),
    )
    @patch.object(
        history_import_worker,
        "fetch_all_trifecta_odds_browser",
    )
    @patch.object(
        history_import_worker,
        "fetch_trifecta_odds_http",
        return_value=([], []),
    )
    @patch.object(
        history_import_worker,
        "fetch_racecard_data_browser",
    )
    def test_continues_without_odds_for_independent_ai(
        self,
        racecard_mock,
        _http_mock,
        dom_mock,
        lineup_mock,
    ) -> None:
        racecard_mock.return_value = (
            self.riders(),
            [],
        )
        dom_mock.return_value = (
            self.odds()[:-1],
            [],
        )

        (
            riders,
            odds_rows,
            lineup_groups,
            odds_complete,
        ) = (
            history_import_worker
            ._collect_learning_snapshot(
                self.entry()
            )
        )

        self.assertEqual(len(riders), 3)
        self.assertEqual(odds_rows, [])
        self.assertEqual(
            lineup_groups,
            [[1, 2], [3]],
        )
        self.assertFalse(odds_complete)
        lineup_mock.assert_called_once()


class LearningDatabaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = (
            tempfile.TemporaryDirectory()
        )
        self.original_path = (
            learning_database.DATABASE_PATH
        )
        learning_database.DATABASE_PATH = (
            Path(self.temporary.name)
            / "test.db"
        )

    def tearDown(self) -> None:
        learning_database.DATABASE_PATH = (
            self.original_path
        )
        self.temporary.cleanup()

    @staticmethod
    def riders() -> list[dict[str, object]]:
        return [
            {
                "車番": number,
                "選手名": f"選手{number}",
                "AI印": "",
                "競走得点": 90.0 + number,
                "脚質": "追",
                "S": 0,
                "H": 0,
                "B": 0,
                "勝率": 10.0,
                "2連対率": 20.0,
                "3連対率": 30.0,
                "コメント": "",
            }
            for number in (1, 2, 3)
        ]

    @staticmethod
    def odds() -> list[dict[str, object]]:
        return [
            {
                "組番": "-".join(
                    str(value)
                    for value in combination
                ),
                "人気": popularity,
                "オッズ": float(
                    10 + popularity
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

    def test_idempotent_natural_key_and_results(
        self,
    ) -> None:
        race_id = (
            learning_database
            .save_race_snapshot(
                race_date="2026-07-28",
                venue="豊橋競輪",
                race_number=1,
                race_url=(
                    "https://www.winticket.jp/"
                    "keirin/toyohashi/racecard/"
                    "2026072545/4/1"
                ),
                race_title="テスト",
                riders=self.riders(),
                odds_rows=self.odds(),
                lineup_groups=[
                    [1, 2],
                    [3],
                ],
                odds_complete=True,
            )
        )

        second_id = (
            learning_database
            .save_race_snapshot(
                race_date="2026-07-28",
                venue="豊橋",
                race_number=1,
                race_url=(
                    "https://www.winticket.jp/"
                    "keirin/toyohashi/racecard/"
                    "2026072545/4/1?updated"
                ),
                race_title="更新",
                riders=self.riders(),
                odds_rows=self.odds(),
                lineup_groups=[
                    [1, 2],
                    [3],
                ],
                odds_complete=True,
            )
        )

        self.assertEqual(race_id, second_id)
        summary = (
            learning_database
            .get_database_summary()
        )
        self.assertEqual(
            summary["race_count"],
            1,
        )
        self.assertEqual(
            summary["odds_count"],
            6,
        )

        learning_database.save_race_review(
            race_id=race_id,
            reason="同着の記載があります",
        )
        self.assertEqual(
            learning_database
            .get_database_summary()[
                "review_count"
            ],
            1,
        )

        learning_database.save_race_result(
            race_id=race_id,
            first_place=1,
            second_place=2,
            third_place=3,
            payout_per_100=1230,
        )
        self.assertEqual(
            learning_database
            .get_database_summary()[
                "completed_count"
            ],
            1,
        )

    def test_rejects_incomplete_odds(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            learning_database.save_race_snapshot(
                race_date="2026-07-28",
                venue="取手競輪",
                race_number=2,
                race_url="https://example.invalid",
                race_title="不完全",
                riders=self.riders(),
                odds_rows=self.odds()[:-1],
                lineup_groups=[
                    [1, 2],
                    [3],
                ],
                odds_complete=True,
            )

        self.assertEqual(
            learning_database
            .get_database_summary()[
                "race_count"
            ],
            0,
        )

    def test_independent_snapshot_upgrades_without_duplicate(
        self,
    ) -> None:
        race_arguments = {
            "race_date": "2026-07-28",
            "venue": "前橋競輪",
            "race_number": 6,
            "race_url": (
                "https://www.winticket.jp/"
                "keirin/maebashi/racecard/"
                "2026072211/1/6"
            ),
            "race_title": "前橋競輪 6R",
            "riders": self.riders(),
            "lineup_groups": [
                [1, 2],
                [3],
            ],
        }
        race_id = (
            learning_database
            .save_independent_race_snapshot(
                **race_arguments
            )
        )
        learning_database.save_race_result(
            race_id=race_id,
            first_place=1,
            second_place=2,
            third_place=3,
            payout_per_100=1230,
        )

        with learning_database.get_connection() as connection:
            before = connection.execute(
                """
                SELECT odds_complete, result_status
                FROM races
                WHERE race_id = ?
                """,
                (race_id,),
            ).fetchone()
            before_odds = connection.execute(
                """
                SELECT COUNT(*)
                FROM odds
                WHERE race_id = ?
                """,
                (race_id,),
            ).fetchone()[0]

        self.assertEqual(
            before["odds_complete"],
            0,
        )
        self.assertEqual(
            before["result_status"],
            "確定",
        )
        self.assertEqual(before_odds, 0)
        self.assertEqual(
            learning_database
            .get_database_summary()[
                "independent_only_count"
            ],
            1,
        )
        complete, _ = (
            learning_database
            .race_has_complete_learning_data(
                race_id
            )
        )
        self.assertFalse(complete)

        upgraded_id = (
            learning_database
            .save_race_snapshot(
                **race_arguments,
                odds_rows=self.odds(),
                odds_complete=True,
            )
        )

        with learning_database.get_connection() as connection:
            after = connection.execute(
                """
                SELECT
                    COUNT(*) AS race_count,
                    MAX(odds_complete)
                        AS odds_complete,
                    MAX(result_status)
                        AS result_status
                FROM races
                WHERE race_id = ?
                """,
                (race_id,),
            ).fetchone()
            after_odds = connection.execute(
                """
                SELECT COUNT(*)
                FROM odds
                WHERE race_id = ?
                """,
                (race_id,),
            ).fetchone()[0]

        self.assertEqual(upgraded_id, race_id)
        self.assertEqual(after["race_count"], 1)
        self.assertEqual(
            after["odds_complete"],
            1,
        )
        self.assertEqual(
            after["result_status"],
            "確定",
        )
        self.assertEqual(after_odds, 6)
        self.assertEqual(
            learning_database
            .get_database_summary()[
                "independent_only_count"
            ],
            0,
        )

        protected_id = (
            learning_database
            .save_independent_race_snapshot(
                **race_arguments
            )
        )

        with learning_database.get_connection() as connection:
            protected = connection.execute(
                """
                SELECT odds_complete
                FROM races
                WHERE race_id = ?
                """,
                (race_id,),
            ).fetchone()
            protected_odds = connection.execute(
                """
                SELECT COUNT(*)
                FROM odds
                WHERE race_id = ?
                """,
                (race_id,),
            ).fetchone()[0]

        self.assertEqual(protected_id, race_id)
        self.assertEqual(
            protected["odds_complete"],
            1,
        )
        self.assertEqual(protected_odds, 6)

    @patch.object(
        history_import_worker,
        "fetch_race_result",
    )
    @patch.object(
        history_import_worker,
        "_collect_learning_snapshot",
    )
    def test_reimports_only_missing_enriched_features(
        self,
        snapshot_mock,
        result_mock,
    ) -> None:
        race_id = (
            learning_database
            .save_race_snapshot(
                race_date="2026-07-28",
                venue="青森競輪",
                race_number=3,
                race_url=(
                    "https://example.invalid/"
                    "aomori/3"
                ),
                race_title="青森競輪 3R",
                riders=self.riders(),
                odds_rows=self.odds(),
                lineup_groups=[
                    [1, 2],
                    [3],
                ],
                odds_complete=True,
            )
        )
        learning_database.save_race_result(
            race_id=race_id,
            first_place=1,
            second_place=2,
            third_place=3,
            payout_per_100=1230,
        )

        with learning_database.get_connection() as connection:
            connection.execute(
                """
                UPDATE races
                SET feature_version = 0
                WHERE race_id = ?
                """,
                (race_id,),
            )

        enriched_riders = self.riders()

        for number, rider in enumerate(
            enriched_riders,
            start=1,
        ):
            rider.update(
                {
                    "選手ID": f"00020{number}",
                    "府県": "青森",
                    "級班": "A3",
                    "年齢": 30 + number,
                    "期別": 120 + number,
                    "レースグレード": "F2",
                    "レース区分": "A級チ予選",
                    "発走時刻": "09:30",
                    "並び取得方式": (
                        "DOM構造＋コメント確認"
                    ),
                    "並び信頼度": 0.95,
                }
            )

        snapshot_mock.return_value = (
            enriched_riders,
            [],
            [[1, 2], [3]],
            False,
        )
        result_mock.return_value = (
            {
                "success": True,
                "status": "settled",
                "finish_order": [1, 2, 3],
                "winning_combination": "1-2-3",
                "payout_per_100": 1230,
            },
            [],
        )
        entry = {
            "race_date": "2026-07-28",
            "venue": "青森競輪",
            "race_number": 3,
            "racecard_url": (
                "https://example.invalid/"
                "aomori/3"
            ),
            "result_url": (
                "https://example.invalid/"
                "aomori/result/3"
            ),
        }
        category, detail = (
            history_import_worker
            ._process_entry(entry)
        )

        self.assertEqual(category, "success")
        self.assertEqual(
            detail["data_scope"],
            "full",
        )
        snapshot_mock.assert_called_once()

        with learning_database.get_connection() as connection:
            race = connection.execute(
                """
                SELECT
                    feature_version,
                    odds_complete,
                    scheduled_start_time
                FROM races
                WHERE race_id = ?
                """,
                (race_id,),
            ).fetchone()
            odds_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM odds
                WHERE race_id = ?
                """,
                (race_id,),
            ).fetchone()[0]
            rider = connection.execute(
                """
                SELECT cyclist_id, age
                FROM riders
                WHERE
                    race_id = ?
                    AND car_number = 1
                """,
                (race_id,),
            ).fetchone()

        self.assertEqual(
            race["feature_version"],
            1,
        )
        self.assertEqual(
            race["odds_complete"],
            1,
        )
        self.assertEqual(
            race["scheduled_start_time"],
            "09:30",
        )
        self.assertEqual(odds_count, 6)
        self.assertEqual(
            rider["cyclist_id"],
            "000201",
        )
        self.assertEqual(rider["age"], 31)

    @patch.object(
        history_import_worker,
        "fetch_race_result",
    )
    @patch.object(
        history_import_worker,
        "_collect_learning_snapshot",
    )
    def test_worker_saves_night_race_as_independent(
        self,
        snapshot_mock,
        result_mock,
    ) -> None:
        snapshot_mock.return_value = (
            self.riders(),
            [],
            [[1, 2], [3]],
            False,
        )
        result_mock.return_value = (
            {
                "success": True,
                "status": "settled",
                "finish_order": [1, 2, 3],
                "winning_combination": "1-2-3",
                "payout_per_100": 1230,
            },
            [],
        )
        entry = {
            "race_date": "2026-07-28",
            "venue": "前橋競輪",
            "race_number": 6,
            "racecard_url": (
                "https://www.winticket.jp/"
                "keirin/maebashi/racecard/"
                "2026072211/1/6"
            ),
            "result_url": (
                "https://www.winticket.jp/"
                "keirin/maebashi/raceresult/"
                "2026072211/1/6"
            ),
        }

        category, detail = (
            history_import_worker
            ._process_entry(entry)
        )

        self.assertEqual(category, "success")
        self.assertEqual(
            detail["status"],
            "saved_independent",
        )
        self.assertEqual(
            detail["data_scope"],
            "independent",
        )
        race = (
            learning_database
            .get_race_by_identity(
                race_date="2026-07-28",
                venue="前橋競輪",
                race_number=6,
            )
        )
        self.assertIsNotNone(race)
        self.assertEqual(
            race["odds_complete"],
            0,
        )
        self.assertEqual(
            race["result_status"],
            "確定",
        )

    @patch.object(
        history_import_worker,
        "fetch_race_result",
    )
    @patch.object(
        history_import_worker,
        "_collect_learning_snapshot",
    )
    def test_rechecks_existing_review_and_saves_result(
        self,
        snapshot_mock,
        result_mock,
    ) -> None:
        race_id = (
            learning_database
            .save_race_snapshot(
                race_date="2026-07-28",
                venue="豊橋競輪",
                race_number=10,
                race_url=(
                    "https://www.winticket.jp/"
                    "keirin/toyohashi/racecard/"
                    "2026072845/1/10"
                ),
                race_title="豊橋競輪 10R",
                riders=self.riders(),
                odds_rows=self.odds(),
                lineup_groups=[
                    [1, 2],
                    [3],
                ],
                odds_complete=True,
            )
        )
        learning_database.save_race_review(
            race_id=race_id,
            reason="中止の記載があります",
        )
        result_mock.return_value = (
            {
                "success": True,
                "status": "settled",
                "finish_order": [1, 2, 3],
                "winning_combination": "1-2-3",
                "payout_per_100": 1230,
            },
            [],
        )
        entry = {
            "race_date": "2026-07-28",
            "venue": "豊橋競輪",
            "race_number": 10,
            "racecard_url": (
                "https://www.winticket.jp/"
                "keirin/toyohashi/racecard/"
                "2026072845/1/10"
            ),
            "result_url": (
                "https://www.winticket.jp/"
                "keirin/toyohashi/raceresult/"
                "2026072845/1/10"
            ),
        }

        category, detail = (
            history_import_worker
            ._process_entry(entry)
        )

        self.assertEqual(category, "success")
        self.assertEqual(
            detail["status"],
            "saved",
        )
        result_mock.assert_called_once()
        snapshot_mock.assert_not_called()

        race = (
            learning_database
            .get_race_by_identity(
                race_date="2026-07-28",
                venue="豊橋競輪",
                race_number=10,
            )
        )
        self.assertIsNotNone(race)
        self.assertEqual(
            race["result_status"],
            "確定",
        )
        self.assertEqual(
            race["winning_combination"],
            "1-2-3",
        )
        self.assertIsNone(
            race["review_reason"]
        )

    def test_matches_url_missing_race_by_identity(
        self,
    ) -> None:
        race_id = (
            learning_database
            .save_race_snapshot(
                race_date="2026-07-28",
                venue="取手",
                race_number=2,
                race_url="",
                race_title="URL未登録",
                riders=self.riders(),
                odds_rows=self.odds(),
                lineup_groups=[
                    [1, 2],
                    [3],
                ],
                odds_complete=True,
            )
        )
        racecard_url = (
            "https://www.winticket.jp/"
            "keirin/toride/racecard/"
            "2026072623/3/2"
        )
        result_url = racecard_url.replace(
            "/racecard/",
            "/raceresult/",
        )

        matched_id = (
            learning_database
            .update_race_urls_by_identity(
                race_date="2026-07-28",
                venue="取手競輪",
                race_number=2,
                race_url=racecard_url,
                result_url=result_url,
            )
        )
        race = (
            learning_database
            .get_race_by_identity(
                race_date="2026-07-28",
                venue="取手競輪",
                race_number=2,
            )
        )

        self.assertEqual(matched_id, race_id)
        self.assertIsNotNone(race)
        self.assertEqual(
            race["race_url"],
            racecard_url,
        )
        self.assertEqual(
            race["result_url"],
            result_url,
        )

    def test_migrates_legacy_duplicate_races(
        self,
    ) -> None:
        learning_database.initialize_database()
        race_key = (
            learning_database.build_race_key(
                "2026-07-28",
                "伊東競輪",
                1,
            )
        )

        with learning_database.get_connection() as connection:
            connection.execute(
                "DROP INDEX idx_races_race_key"
            )

            base_values = (
                race_key,
                "2026-07-28",
                "伊東競輪",
                1,
                "",
                "",
                "テスト",
                3,
                "[]",
                "2026-07-29T00:00:00",
                "2026-07-29T00:00:00",
            )

            connection.execute(
                """
                INSERT INTO races (
                    race_id,
                    race_key,
                    race_date,
                    venue,
                    race_number,
                    race_url,
                    result_url,
                    race_title,
                    rider_count,
                    lineup_json,
                    odds_complete,
                    collected_at,
                    updated_at,
                    result_status
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    "legacy-result",
                    *base_values[:9],
                    0,
                    *base_values[9:],
                    "確定",
                ),
            )
            connection.execute(
                """
                UPDATE races
                SET
                    first_place = 1,
                    second_place = 2,
                    third_place = 3,
                    winning_combination = '1-2-3',
                    payout_per_100 = 1230
                WHERE race_id = 'legacy-result'
                """
            )

            connection.execute(
                """
                INSERT INTO races (
                    race_id,
                    race_key,
                    race_date,
                    venue,
                    race_number,
                    race_url,
                    result_url,
                    race_title,
                    rider_count,
                    lineup_json,
                    odds_complete,
                    collected_at,
                    updated_at,
                    result_status
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    "legacy-odds",
                    *base_values[:9],
                    1,
                    *base_values[9:],
                    "未確定",
                ),
            )

        learning_database.initialize_database()

        with learning_database.get_connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    result_status,
                    odds_complete,
                    winning_combination
                FROM races
                WHERE race_key = ?
                """,
                (race_key,),
            ).fetchall()
            indexes = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA index_list(races)"
                ).fetchall()
            }

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["result_status"],
            "確定",
        )
        self.assertEqual(
            rows[0]["odds_complete"],
            1,
        )
        self.assertEqual(
            rows[0]["winning_combination"],
            "1-2-3",
        )
        self.assertIn(
            "idx_races_race_key",
            indexes,
        )

    def test_backs_up_legacy_database_before_migration(
        self,
    ) -> None:
        database_path = (
            learning_database.DATABASE_PATH
        )

        with sqlite3.connect(
            database_path
        ) as connection:
            connection.execute(
                """
                CREATE TABLE races (
                    race_id TEXT PRIMARY KEY,
                    race_date TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    race_number INTEGER NOT NULL,
                    race_url TEXT,
                    race_title TEXT,
                    rider_count INTEGER NOT NULL,
                    lineup_json TEXT NOT NULL,
                    odds_complete INTEGER NOT NULL DEFAULT 0,
                    collected_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result_status TEXT NOT NULL DEFAULT '未確定',
                    first_place INTEGER,
                    second_place INTEGER,
                    third_place INTEGER,
                    winning_combination TEXT,
                    payout_per_100 INTEGER
                )
                """
            )
            connection.execute(
                """
                INSERT INTO races (
                    race_id,
                    race_date,
                    venue,
                    race_number,
                    race_url,
                    race_title,
                    rider_count,
                    lineup_json,
                    odds_complete,
                    collected_at,
                    updated_at
                )
                VALUES (
                    'legacy',
                    '2026-07-28',
                    '豊橋競輪',
                    1,
                    '',
                    '旧DB',
                    0,
                    '[]',
                    0,
                    '2026-07-28T00:00:00',
                    '2026-07-28T00:00:00'
                )
                """
            )

        learning_database.initialize_database()

        backups = list(
            (
                database_path.parent
                / "backups"
            ).glob(
                "keirin_learning_"
                "before_history_import_*.db"
            )
        )

        self.assertEqual(len(backups), 1)

        with sqlite3.connect(
            backups[0]
        ) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM races"
            ).fetchone()[0]

        self.assertEqual(count, 1)

    def test_migrates_iwakidaira_alias_without_losing_result(
        self,
    ) -> None:
        learning_database.initialize_database()

        race_id = (
            learning_database
            .save_race_snapshot(
                race_date="2026-07-22",
                venue="いわき平競輪",
                race_number=1,
                race_url=(
                    "https://www.winticket.jp/"
                    "keirin/iwakidaira/racecard/"
                    "2026072213/1/1"
                ),
                race_title="テスト",
                riders=self.riders(),
                odds_rows=self.odds(),
                lineup_groups=[
                    [1, 2],
                    [3],
                ],
                odds_complete=True,
            )
        )
        with learning_database.get_connection() as connection:
            connection.execute(
                """
                UPDATE races
                SET
                    venue = 'iwakidaira競輪',
                    race_key = (
                        '2026-07-22|iwakidaira|01'
                    ),
                    result_status = '確定',
                    first_place = 3,
                    second_place = 6,
                    third_place = 4,
                    winning_combination = '3-6-4',
                    payout_per_100 = 95960
                WHERE race_id = ?
                """,
                (race_id,),
            )
            connection.execute(
                "PRAGMA user_version=2"
            )

        learning_database.initialize_database()

        with learning_database.get_connection() as connection:
            row = connection.execute(
                """
                SELECT
                    venue,
                    race_key,
                    result_status,
                    winning_combination,
                    payout_per_100
                FROM races
                WHERE race_id = ?
                """,
                (race_id,),
            ).fetchone()
            schema_version = connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]

        self.assertIsNotNone(row)
        self.assertEqual(
            row["venue"],
            "いわき平競輪",
        )
        self.assertEqual(
            row["race_key"],
            "2026-07-22|いわき平|01",
        )
        self.assertEqual(
            row["result_status"],
            "確定",
        )
        self.assertEqual(
            row["winning_combination"],
            "3-6-4",
        )
        self.assertEqual(
            row["payout_per_100"],
            95960,
        )
        self.assertEqual(schema_version, 7)

    def test_migrates_iwakidaira_race_title(
        self,
    ) -> None:
        learning_database.initialize_database()

        race_id = (
            learning_database
            .save_race_snapshot(
                race_date="2026-07-22",
                venue="いわき平競輪",
                race_number=1,
                race_url=(
                    "https://www.winticket.jp/"
                    "keirin/iwakidaira/racecard/"
                    "2026072213/1/1"
                ),
                race_title=(
                    "いわき平競輪 1R"
                ),
                riders=self.riders(),
                odds_rows=self.odds(),
                lineup_groups=[
                    [1, 2],
                    [3],
                ],
                odds_complete=True,
            )
        )

        with learning_database.get_connection() as connection:
            connection.execute(
                """
                UPDATE races
                SET race_title = 'iwakidaira競輪 1R'
                WHERE race_id = ?
                """,
                (race_id,),
            )
            connection.execute(
                "PRAGMA user_version=3"
            )

        learning_database.initialize_database()

        with learning_database.get_connection() as connection:
            row = connection.execute(
                """
                SELECT
                    venue,
                    race_title
                FROM races
                WHERE race_id = ?
                """,
                (race_id,),
            ).fetchone()
            schema_version = connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]

        self.assertIsNotNone(row)
        self.assertEqual(
            row["venue"],
            "いわき平競輪",
        )
        self.assertEqual(
            row["race_title"],
            "いわき平競輪 1R",
        )
        self.assertEqual(schema_version, 7)


class WorkerSelfTest(unittest.TestCase):
    def test_worker_self_test(self) -> None:
        worker_path = (
            Path(__file__).resolve().parents[1]
            / "history_import_worker.py"
        )
        completed = subprocess.run(
            [
                sys.executable,
                str(worker_path),
                "--self-test",
            ],
            cwd=str(worker_path.parent),
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(
            completed.returncode,
            0,
            msg=(
                completed.stdout
                + completed.stderr
            ),
        )
        self.assertIn(
            '"success": true',
            completed.stdout,
        )


if __name__ == "__main__":
    unittest.main()
