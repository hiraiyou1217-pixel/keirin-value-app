package jp.hirai.keirinai;

import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;

public final class RaceTimeLabel {
    private static final ZoneId JAPAN =
        ZoneId.of("Asia/Tokyo");
    private static final DateTimeFormatter DATE =
        DateTimeFormatter.BASIC_ISO_DATE;
    private static final DateTimeFormatter TIME =
        DateTimeFormatter.ofPattern("HH:mm");

    private RaceTimeLabel() {
    }

    public static String schedule(
        String dateText,
        String startTime
    ) {
        return schedule(
            dateText,
            startTime,
            ZonedDateTime.now(JAPAN)
        );
    }

    static String schedule(
        String dateText,
        String startTime,
        ZonedDateTime now
    ) {
        if (
            dateText == null
            || startTime == null
            || dateText.isBlank()
            || startTime.isBlank()
        ) {
            return "";
        }

        try {
            LocalDate date = LocalDate.parse(
                dateText,
                DATE
            );
            LocalTime time = LocalTime.parse(
                startTime,
                TIME
            );
            ZonedDateTime target =
                LocalDateTime.of(
                    date,
                    time
                ).atZone(JAPAN);

            if (now.isAfter(target)) {
                return startTime
                    + "発走予定・時刻経過";
            }

            long minutes = Duration.between(
                now,
                target
            ).toMinutes();

            if (minutes == 0) {
                return startTime
                    + "発走予定・まもなく";
            }

            if (minutes < 60) {
                return startTime
                    + "発走予定・あと"
                    + minutes
                    + "分";
            }

            long hours = minutes / 60;
            long remaining = minutes % 60;

            if (remaining == 0) {
                return startTime
                    + "発走予定・あと"
                    + hours
                    + "時間";
            }

            return startTime
                + "発走予定・あと"
                + hours
                + "時間"
                + remaining
                + "分";
        } catch (
            DateTimeParseException exception
        ) {
            return startTime;
        }
    }
}
