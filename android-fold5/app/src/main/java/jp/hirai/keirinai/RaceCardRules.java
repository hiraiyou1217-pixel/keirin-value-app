package jp.hirai.keirinai;

import java.net.URI;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

final class RaceCardRules {
    private RaceCardRules() {
    }

    static boolean isSupportedRaceCardUrl(String value) {
        if (value == null || value.isBlank()) {
            return false;
        }

        try {
            URI uri = URI.create(value.trim());
            String host = uri.getHost();
            String path = uri.getPath();

            return "https".equalsIgnoreCase(uri.getScheme())
                && host != null
                && (
                    host.equals("www.winticket.jp")
                    || host.equals("winticket.jp")
                )
                && path != null
                && path.matches(
                    "^/keirin/[^/]+/racecard/"
                        + "\\d{10,}/\\d{1,2}/\\d{1,2}/?$"
                );
        } catch (IllegalArgumentException exception) {
            return false;
        }
    }

    static String normalizeHeader(String value) {
        if (value == null) {
            return "";
        }

        return value
            .replace("\n", "")
            .replace(" ", "")
            .replace("　", "")
            .replace("２", "2")
            .replace("３", "3")
            .replace("二", "2")
            .replace("三", "3")
            .trim()
            .toLowerCase(Locale.JAPAN);
    }

    static String validateCarNumbers(List<Integer> values) {
        if (values == null || values.size() < 5 || values.size() > 9) {
            return "選手数が5〜9人ではありません。";
        }

        Set<Integer> unique = new HashSet<>();

        for (Integer value : values) {
            if (value == null || value < 1 || value > 9) {
                return "車番に1〜9以外の値があります。";
            }

            if (!unique.add(value)) {
                return "同じ車番が重複しています。";
            }
        }

        return "";
    }
}
