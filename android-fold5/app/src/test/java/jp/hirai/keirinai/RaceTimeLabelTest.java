package jp.hirai.keirinai;

import static org.junit.Assert.assertEquals;

import java.time.ZoneId;
import java.time.ZonedDateTime;
import org.junit.Test;

public class RaceTimeLabelTest {
    private static final ZoneId JAPAN =
        ZoneId.of("Asia/Tokyo");

    @Test
    public void showsMinutesUntilStart() {
        ZonedDateTime now = ZonedDateTime.of(
            2026,
            7,
            31,
            10,
            0,
            0,
            0,
            JAPAN
        );

        assertEquals(
            "10:35発走予定・あと35分",
            RaceTimeLabel.schedule(
                "20260731",
                "10:35",
                now
            )
        );
    }

    @Test
    public void showsHoursAndElapsedTime() {
        ZonedDateTime now = ZonedDateTime.of(
            2026,
            7,
            31,
            10,
            0,
            0,
            0,
            JAPAN
        );

        assertEquals(
            "12:15発走予定・あと2時間15分",
            RaceTimeLabel.schedule(
                "20260731",
                "12:15",
                now
            )
        );
        assertEquals(
            "09:59発走予定・時刻経過",
            RaceTimeLabel.schedule(
                "20260731",
                "09:59",
                now
            )
        );
    }

    @Test
    public void returnsBlankWhenNoLiteralTime() {
        assertEquals(
            "",
            RaceTimeLabel.schedule(
                "20260731",
                ""
            )
        );
    }
}
