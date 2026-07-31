package jp.hirai.keirinai;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class RaceCatalogSelection {
    public static final class RaceEntry {
        private final String venue;
        private final int raceNumber;
        private final String url;
        private final String startTime;

        private RaceEntry(
            String venue,
            int raceNumber,
            String url,
            String startTime
        ) {
            this.venue = venue;
            this.raceNumber = raceNumber;
            this.url = url;
            this.startTime = startTime;
        }

        public String venue() {
            return venue;
        }

        public int raceNumber() {
            return raceNumber;
        }

        public String url() {
            return url;
        }

        public String startTime() {
            return startTime;
        }
    }

    private final LinkedHashMap<
        String,
        List<RaceEntry>
    > racesByVenue;
    private final int raceCount;

    private RaceCatalogSelection(
        LinkedHashMap<
            String,
            List<RaceEntry>
        > racesByVenue,
        int raceCount
    ) {
        this.racesByVenue = racesByVenue;
        this.raceCount = raceCount;
    }

    public static RaceCatalogSelection from(
        JSONArray races
    ) throws JSONException {
        if (races == null || races.length() == 0) {
            throw new JSONException(
                "開催レースがありません。"
            );
        }

        Map<String, List<RaceEntry>> grouped =
            new java.util.TreeMap<>();
        Set<String> acquired = new HashSet<>();
        int count = 0;

        for (
            int index = 0;
            index < races.length();
            index++
        ) {
            JSONObject source =
                races.optJSONObject(index);

            if (source == null) {
                throw new JSONException(
                    "開催レースの形式が不正です。"
                );
            }

            String venue = source.optString(
                "venue",
                ""
            ).trim();
            int raceNumber = source.optInt(
                "raceNumber",
                0
            );
            String url = source.optString(
                "url",
                ""
            ).trim();
            String startTime = source.optString(
                "startTime",
                ""
            ).trim();

            if (venue.isBlank()) {
                throw new JSONException(
                    "開催場名がありません。"
                );
            }

            if (
                raceNumber < 1
                || raceNumber > 12
            ) {
                throw new JSONException(
                    "R番号が範囲外です: "
                        + raceNumber
                );
            }

            if (
                !RaceCardRules
                    .isSupportedRaceCardUrl(url)
            ) {
                throw new JSONException(
                    "個別出走表URLが不正です。"
                );
            }

            if (
                !startTime.isBlank()
                && !startTime.matches(
                    "(?:[01]\\d|2[0-3]):[0-5]\\d"
                )
            ) {
                throw new JSONException(
                    "発走時刻の形式が不正です: "
                        + startTime
                );
            }

            String key =
                venue + "\u0000" + raceNumber;

            if (!acquired.add(key)) {
                throw new JSONException(
                    venue
                        + " "
                        + raceNumber
                        + "Rが重複しています。"
                );
            }

            grouped.computeIfAbsent(
                venue,
                ignored -> new ArrayList<>()
            ).add(
                new RaceEntry(
                    venue,
                    raceNumber,
                    url,
                    startTime
                )
            );
            count++;
        }

        LinkedHashMap<
            String,
            List<RaceEntry>
        > ordered = new LinkedHashMap<>();

        for (
            Map.Entry<
                String,
                List<RaceEntry>
            > group : grouped.entrySet()
        ) {
            List<RaceEntry> venueRaces =
                new ArrayList<>(
                    group.getValue()
                );
            venueRaces.sort(
                java.util.Comparator.comparingInt(
                    RaceEntry::raceNumber
                )
            );
            ordered.put(
                group.getKey(),
                List.copyOf(venueRaces)
            );
        }

        return new RaceCatalogSelection(
            ordered,
            count
        );
    }

    public List<String> venues() {
        return List.copyOf(
            racesByVenue.keySet()
        );
    }

    public List<RaceEntry> racesForVenue(
        String venue
    ) {
        List<RaceEntry> races =
            racesByVenue.get(venue);

        if (races == null) {
            return List.of();
        }

        return races;
    }

    public int raceCount() {
        return raceCount;
    }
}
