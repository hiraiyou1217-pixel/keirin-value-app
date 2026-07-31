package jp.hirai.keirinai;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertThrows;

import java.util.List;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import org.junit.Test;

public class RaceCatalogSelectionTest {
    private JSONObject race(
        String venue,
        int raceNumber,
        String slug,
        String cupId
    ) throws JSONException {
        return new JSONObject()
            .put("venue", venue)
            .put("raceNumber", raceNumber)
            .put(
                "url",
                "https://www.winticket.jp/"
                    + "keirin/"
                    + slug
                    + "/racecard/"
                    + cupId
                    + "/1/"
                    + raceNumber
            );
    }

    @Test
    public void groupsByVenueThenRaceNumber()
        throws JSONException {
        JSONArray source = new JSONArray()
            .put(
                race(
                    "青森競輪",
                    3,
                    "aomori",
                    "2026073112"
                )
            )
            .put(
                race(
                    "伊東競輪",
                    2,
                    "ito",
                    "2026073137"
                )
            )
            .put(
                race(
                    "青森競輪",
                    1,
                    "aomori",
                    "2026073112"
                )
            );

        RaceCatalogSelection catalog =
            RaceCatalogSelection.from(source);

        assertEquals(
            List.of("伊東競輪", "青森競輪"),
            catalog.venues()
        );
        assertEquals(3, catalog.raceCount());
        assertEquals(
            1,
            catalog.racesForVenue(
                "青森競輪"
            ).get(0).raceNumber()
        );
        assertEquals(
            3,
            catalog.racesForVenue(
                "青森競輪"
            ).get(1).raceNumber()
        );
        assertEquals(
            "https://www.winticket.jp/"
                + "keirin/aomori/racecard/"
                + "2026073112/1/1",
            catalog.racesForVenue(
                "青森競輪"
            ).get(0).url()
        );
    }

    @Test
    public void rejectsDuplicateVenueAndRace()
        throws JSONException {
        JSONArray source = new JSONArray()
            .put(
                race(
                    "青森競輪",
                    1,
                    "aomori",
                    "2026073112"
                )
            )
            .put(
                race(
                    "青森競輪",
                    1,
                    "aomori",
                    "2026073112"
                )
            );

        assertThrows(
            JSONException.class,
            () -> RaceCatalogSelection.from(
                source
            )
        );
    }

    @Test
    public void rejectsCatalogPageUrl()
        throws JSONException {
        JSONArray source = new JSONArray()
            .put(
                new JSONObject()
                    .put(
                        "venue",
                        "青森競輪"
                    )
                    .put("raceNumber", 1)
                    .put(
                        "url",
                        "https://www.winticket.jp/"
                            + "keirin/racecard/"
                            + "20260731"
                    )
            );

        assertThrows(
            JSONException.class,
            () -> RaceCatalogSelection.from(
                source
            )
        );
    }
}
