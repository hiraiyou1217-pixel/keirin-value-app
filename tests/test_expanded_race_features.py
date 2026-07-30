from __future__ import annotations

import unittest

from lineup_dom_worker import (
    group_lineup_geometry,
)
from lineup_from_comments import (
    select_authoritative_lineup,
)
from race_metadata import (
    get_venue_characteristics,
    parse_race_conditions,
    parse_rider_profile,
)


class ExpandedRaceFeatureTest(
    unittest.TestCase
):
    def test_parses_rider_profile_and_id(
        self,
    ) -> None:
        profile = parse_rider_profile(
            "中秀平\n神奈川 A3 27歳 127期",
            (
                "https://www.winticket.jp/"
                "keirin/cyclist/015890"
            ),
        )

        self.assertEqual(
            profile["選手名"],
            "中秀平",
        )
        self.assertEqual(
            profile["選手ID"],
            "015890",
        )
        self.assertEqual(
            profile["府県"],
            "神奈川",
        )
        self.assertEqual(
            profile["級班"],
            "A3",
        )
        self.assertEqual(
            profile["年齢"],
            27,
        )
        self.assertEqual(
            profile["期別"],
            127,
        )

    def test_parses_race_conditions(
        self,
    ) -> None:
        conditions = parse_race_conditions(
            page_title=(
                "青森競輪 F2（2026年7月30日)"
                "1レース 出走表"
            ),
            body_text=(
                "1R\n"
                "A級チ予選\n"
                "発走 08:30 締切 08:25\n"
                "2026年7月30日 "
                "1,625m (4周) "
                "曇23.0℃西1.0m/s\n"
                "青森競輪 F2 初日"
            ),
            racecard_url=(
                "https://www.winticket.jp/"
                "keirin/aomori/racecard/"
                "2026073012/1/1"
            ),
        )

        self.assertEqual(
            conditions["レースグレード"],
            "F2",
        )
        self.assertEqual(
            conditions["レース区分"],
            "A級チ予選",
        )
        self.assertEqual(
            conditions["レース級別"],
            "A級3班",
        )
        self.assertEqual(
            conditions["開催日目"],
            1,
        )
        self.assertEqual(
            conditions["発走時刻"],
            "08:30",
        )
        self.assertEqual(
            conditions["距離m"],
            1625,
        )
        self.assertEqual(
            conditions["周回数"],
            4,
        )
        self.assertEqual(
            conditions["天候"],
            "曇",
        )
        self.assertEqual(
            conditions["気温C"],
            23.0,
        )
        self.assertEqual(
            conditions["風向"],
            "西",
        )
        self.assertEqual(
            conditions["風速mps"],
            1.0,
        )

    def test_knows_aomori_bank_traits(
        self,
    ) -> None:
        traits = get_venue_characteristics(
            "青森競輪"
        )

        self.assertEqual(
            traits["bank_length_m"],
            400.0,
        )
        self.assertEqual(
            traits["home_straight_m"],
            58.9,
        )
        self.assertEqual(
            traits["max_cant_degrees"],
            32.25,
        )
        self.assertEqual(
            traits[
                "venue_characteristics_known"
            ],
            1.0,
        )

    def test_groups_lineup_by_dom_geometry(
        self,
    ) -> None:
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
            group_lineup_geometry(
                items,
                [1, 2, 3, 4, 5, 6, 7],
            ),
            [
                [1, 5, 7],
                [2, 6],
                [3, 4],
            ],
        )

    def test_uses_high_confidence_when_dom_and_comments_agree(
        self,
    ) -> None:
        groups, metadata, _ = (
            select_authoritative_lineup(
                [
                    [1, 5, 7],
                    [2, 6],
                    [3, 4],
                ],
                [
                    [1, 5],
                    [7],
                    [2, 6],
                    [3, 4],
                ],
                [1, 2, 3, 4, 5, 6, 7],
            )
        )

        self.assertEqual(
            groups,
            [
                [1, 5, 7],
                [2, 6],
                [3, 4],
            ],
        )
        self.assertEqual(
            metadata["並び信頼度"],
            0.95,
        )


if __name__ == "__main__":
    unittest.main()
