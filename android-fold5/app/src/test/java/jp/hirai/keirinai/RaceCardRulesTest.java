package jp.hirai.keirinai;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.util.List;
import org.junit.Test;

public class RaceCardRulesTest {
    @Test
    public void acceptsWinticketRaceCardUrl() {
        assertTrue(
            RaceCardRules.isSupportedRaceCardUrl(
                "https://www.winticket.jp/keirin/"
                    + "aomori/racecard/2026073012/1/1"
            )
        );
    }

    @Test
    public void rejectsNonWinticketOrCatalogUrl() {
        assertFalse(
            RaceCardRules.isSupportedRaceCardUrl(
                "https://example.com/keirin/a/racecard/"
                    + "2026073012/1/1"
            )
        );
        assertFalse(
            RaceCardRules.isSupportedRaceCardUrl(
                "https://www.winticket.jp/keirin/"
                    + "racecard/20260730"
            )
        );
    }

    @Test
    public void normalizesJapaneseHeaders() {
        assertEquals(
            "2連対率",
            RaceCardRules.normalizeHeader(
                "２連\n対率"
            )
        );
    }

    @Test
    public void validatesUniqueCarNumbers() {
        assertEquals(
            "",
            RaceCardRules.validateCarNumbers(
                List.of(1, 2, 3, 4, 5, 6, 7)
            )
        );
        assertEquals(
            "同じ車番が重複しています。",
            RaceCardRules.validateCarNumbers(
                List.of(1, 2, 3, 4, 5, 6, 6)
            )
        );
    }
}
