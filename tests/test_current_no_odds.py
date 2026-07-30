from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import current_race_snapshot
from lineup_from_comments import (
    infer_lineup_from_comments,
)


class CurrentRaceWithoutOddsTest(
    unittest.TestCase
):
    def test_prediction_context_does_not_mix_stale_session(
        self,
    ) -> None:
        context = (
            current_race_snapshot
            .resolve_prediction_context(
                {
                    "saved_at": (
                        "2026-07-30T12:00:00"
                    ),
                    "race_date": "2026-07-30",
                    "venue": "青森競輪",
                    "race_number": 1,
                    "race_url": "aomori-url",
                    "race_title": "青森競輪 1R",
                    "riders": [
                        {
                            "車番": 1,
                            "選手名": "青森選手",
                        }
                    ],
                    "lineup_groups": [[1]],
                    "odds_complete": False,
                },
                {
                    "selected_date": (
                        "2026-07-29"
                    ),
                    "selected_venue": "伊東競輪",
                    "selected_race_number": 9,
                    "selected_race_url": (
                        "ito-url"
                    ),
                    "rider_data": [
                        {
                            "車番": 9,
                            "選手名": "伊東選手",
                        }
                    ],
                    "lineup_groups": [[9]],
                },
            )
        )

        self.assertEqual(
            context["source"],
            "snapshot",
        )
        self.assertEqual(
            context["race_date"],
            "2026-07-30",
        )
        self.assertEqual(
            context["venue"],
            "青森競輪",
        )
        self.assertEqual(
            context["race_number"],
            1,
        )
        self.assertEqual(
            context["riders"][0][
                "選手名"
            ],
            "青森選手",
        )
        self.assertEqual(
            context["lineup_groups"],
            [[1]],
        )

    def test_prediction_context_uses_session_only_without_snapshot(
        self,
    ) -> None:
        context = (
            current_race_snapshot
            .resolve_prediction_context(
                {},
                {
                    "selected_date": (
                        "2026-07-29"
                    ),
                    "selected_venue": "伊東競輪",
                    "selected_race_number": 9,
                    "rider_data": [
                        {
                            "車番": 9,
                            "選手名": "伊東選手",
                        }
                    ],
                    "lineup_groups": [[9]],
                },
            )
        )

        self.assertEqual(
            context["source"],
            "session",
        )
        self.assertEqual(
            context["venue"],
            "伊東競輪",
        )
        self.assertEqual(
            context["riders"][0][
                "選手名"
            ],
            "伊東選手",
        )

    def test_prediction_page_prefers_snapshot_over_stale_session(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            original_path = (
                current_race_snapshot
                .SNAPSHOT_PATH
            )
            current_race_snapshot.SNAPSHOT_PATH = (
                Path(temporary)
                / "current.json"
            )

            try:
                (
                    current_race_snapshot
                    .save_current_race_snapshot(
                        odds_rows=[],
                        riders=[
                            {
                                "車番": 1,
                                "選手名": "青森選手1",
                            },
                            {
                                "車番": 2,
                                "選手名": "青森選手2",
                            },
                            {
                                "車番": 3,
                                "選手名": "青森選手3",
                            },
                        ],
                        lineup_groups=[
                            [1, 2],
                            [3],
                        ],
                        odds_logs=[],
                        race_date=(
                            "2026-07-30"
                        ),
                        venue="青森競輪",
                        race_number=1,
                        race_url="aomori-url",
                        race_title=(
                            "青森競輪 1R"
                        ),
                    )
                )
                app = AppTest.from_file(
                    (
                        "pages/"
                        "6_オッズ非依存AI.py"
                    ),
                    default_timeout=30,
                )
                app.session_state[
                    "selected_date"
                ] = "2026-07-29"
                app.session_state[
                    "selected_venue"
                ] = "伊東競輪"
                app.session_state[
                    "selected_race_number"
                ] = 9
                app.session_state[
                    "rider_data"
                ] = [
                    {
                        "車番": 9,
                        "選手名": "伊東選手",
                    }
                ]
                app.session_state[
                    "lineup_groups"
                ] = [[9]]
                app.run()

                self.assertEqual(
                    len(app.exception),
                    0,
                )
                rendered_text = "\n".join(
                    str(item.value)
                    for item in app.markdown
                )
                self.assertIn(
                    (
                        "予測対象：2026-07-30 "
                        "青森競輪 1R"
                    ),
                    rendered_text,
                )
                self.assertNotIn(
                    "伊東競輪 9R",
                    rendered_text,
                )

            finally:
                current_race_snapshot.SNAPSHOT_PATH = (
                    original_path
                )

    def test_matches_one_character_surname_without_space(
        self,
    ) -> None:
        groups, logs = (
            infer_lineup_from_comments(
                [
                    {
                        "車番": 1,
                        "選手名": "中秀平",
                        "コメント": "自力。",
                    },
                    {
                        "車番": 5,
                        "選手名": "鶴岡與之",
                        "コメント": "中君。",
                    },
                    {
                        "車番": 7,
                        "選手名": "田中智也",
                        "コメント": "単騎。",
                    },
                ]
            )
        )

        self.assertEqual(
            groups,
            [
                [1, 5],
                [7],
            ],
        )
        self.assertTrue(
            any(
                "5番 → 1番" in log
                for log in logs
            )
        )

    def test_does_not_guess_ambiguous_surname(
        self,
    ) -> None:
        groups, _ = infer_lineup_from_comments(
            [
                {
                    "車番": 1,
                    "選手名": "田中一郎",
                    "コメント": "自力。",
                },
                {
                    "車番": 2,
                    "選手名": "田中二郎",
                    "コメント": "自力。",
                },
                {
                    "車番": 3,
                    "選手名": "佐藤三郎",
                    "コメント": "田中君。",
                },
            ]
        )

        self.assertEqual(
            groups,
            [
                [1],
                [2],
                [3],
            ],
        )

    def test_saves_riders_and_lineup_when_odds_are_hidden(
        self,
    ) -> None:
        catalog = {
            "青森競輪": [
                {
                    "race_number": 1,
                    "url": (
                        "https://example.invalid/"
                        "racecard/1"
                    ),
                }
            ]
        }
        riders = [
            {
                "車番": 1,
                "選手名": "中 秀平",
                "AI印": "",
                "競走得点": 74.24,
                "脚質": "逃",
                "S": 20,
                "H": 19,
                "B": 15,
                "勝率": 21.2,
                "2連対率": 45.4,
                "3連対率": 66.6,
                "コメント": "自力。",
            },
            {
                "車番": 2,
                "選手名": "鶴岡 與之",
                "AI印": "",
                "競走得点": 81.28,
                "脚質": "追",
                "S": 0,
                "H": 0,
                "B": 0,
                "勝率": 17.8,
                "2連対率": 17.8,
                "3連対率": 25.0,
                "コメント": "中君。",
            },
            {
                "車番": 3,
                "選手名": "田中 智也",
                "AI印": "",
                "競走得点": 69.47,
                "脚質": "追",
                "S": 4,
                "H": 0,
                "B": 0,
                "勝率": 0.0,
                "2連対率": 4.7,
                "3連対率": 33.3,
                "コメント": "単騎。",
            },
        ]

        with tempfile.TemporaryDirectory() as temporary:
            original_path = (
                current_race_snapshot
                .SNAPSHOT_PATH
            )
            current_race_snapshot.SNAPSHOT_PATH = (
                Path(temporary)
                / "current.json"
            )

            try:
                with (
                    patch(
                        "race_catalog."
                        "fetch_race_catalog",
                        return_value=(
                            catalog,
                            [],
                        ),
                    ),
                    patch(
                        "odds_browser."
                        "fetch_all_trifecta_odds_browser",
                        return_value=(
                            [],
                            [
                                "DOM取得Workerで"
                                "エラーが発生しました。"
                            ],
                        ),
                    ),
                    patch(
                        "racecard_browser."
                        "fetch_racecard_data_browser",
                        return_value=(
                            riders,
                            [],
                        ),
                    ),
                    patch(
                        "lineup_browser."
                        "fetch_lineup_browser",
                        return_value=(
                            [
                                [1],
                                [2],
                                [3],
                            ],
                            [],
                        ),
                    ),
                ):
                    app = AppTest.from_file(
                        "main.py",
                        default_timeout=30,
                    ).run()
                    next(
                        button
                        for button in app.button
                        if button.label
                        == "この日の開催一覧を取得"
                    ).click().run()
                    next(
                        button
                        for button in app.button
                        if button.label
                        == "レースデータを取得"
                    ).click().run()

                self.assertEqual(
                    len(app.exception),
                    0,
                )
                self.assertTrue(
                    any(
                        "オッズ非依存AI用として"
                        "保存しました"
                        in information.value
                        for information in app.info
                    )
                )
                snapshot = (
                    current_race_snapshot
                    .load_current_race_snapshot()
                )
                self.assertEqual(
                    snapshot["venue"],
                    "青森競輪",
                )
                self.assertEqual(
                    snapshot["race_number"],
                    1,
                )
                self.assertEqual(
                    snapshot["odds_rows"],
                    [],
                )
                self.assertFalse(
                    snapshot["odds_complete"]
                )
                self.assertEqual(
                    len(snapshot["riders"]),
                    3,
                )
                self.assertEqual(
                    snapshot["lineup_groups"],
                    [
                        [1, 2],
                        [3],
                    ],
                )

            finally:
                current_race_snapshot.SNAPSHOT_PATH = (
                    original_path
                )


if __name__ == "__main__":
    unittest.main()
