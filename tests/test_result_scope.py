from __future__ import annotations

import unittest

import result_dom_worker


class ResultScopeTest(unittest.TestCase):
    def test_extracts_target_race_number_from_url(
        self,
    ) -> None:
        self.assertEqual(
            result_dom_worker
            .extract_race_number_from_url(
                "https://www.winticket.jp/"
                "keirin/toyohashi/raceresult/"
                "2026072845/1/11"
            ),
            11,
        )
        self.assertIsNone(
            result_dom_worker
            .extract_race_number_from_url(
                "https://example.invalid/result"
            )
        )

    def test_cancellation_is_scoped_to_eleventh_race(
        self,
    ) -> None:
        body_text = """
        1R
        2R
        3R
        4R
        5R
        6R
        7R
        8R
        9R
        10R
        11R
        悪天候のため中止
        12R
        第1レース
        着順 1着 2着 3着
        第11レース
        中止
        第12レース
        着順 1着 2着 3着
        """

        self.assertEqual(
            result_dom_worker
            .detect_manual_review_reasons(
                body_text,
                race_number=1,
                has_settled_result=True,
            ),
            [],
        )
        self.assertEqual(
            result_dom_worker
            .detect_manual_review_reasons(
                body_text,
                race_number=11,
            ),
            ["中止の記載があります"],
        )
        self.assertEqual(
            result_dom_worker
            .detect_manual_review_reasons(
                body_text,
                race_number=12,
                has_settled_result=True,
            ),
            [],
        )

    def test_one_race_does_not_match_eleven_race(
        self,
    ) -> None:
        scoped = (
            result_dom_worker
            .extract_race_scoped_text(
                "1R\n確定\n11R\n中止\n12R\n確定",
                1,
            )
        )

        self.assertNotIn("11R", scoped)
        self.assertNotIn("中止", scoped)

    def test_settled_result_suppresses_global_cancellation(
        self,
    ) -> None:
        self.assertEqual(
            result_dom_worker
            .detect_manual_review_reasons(
                "中止のお知らせ",
                race_number=1,
                has_settled_result=True,
            ),
            [],
        )

    def test_target_cancellation_is_never_suppressed(
        self,
    ) -> None:
        self.assertEqual(
            result_dom_worker
            .detect_manual_review_reasons(
                "11R\n中止",
                race_number=11,
                has_settled_result=True,
            ),
            ["中止の記載があります"],
        )

    def test_disqualification_in_target_race_stays_review(
        self,
    ) -> None:
        reasons = (
            result_dom_worker
            .detect_manual_review_reasons(
                "第3レース\n4番失格\n第4レース\n確定",
                race_number=3,
                has_settled_result=True,
            )
        )

        self.assertEqual(
            reasons,
            ["失格の記載があります"],
        )


if __name__ == "__main__":
    unittest.main()
