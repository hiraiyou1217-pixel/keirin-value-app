package jp.hirai.keirinai;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.time.Instant;
import org.json.JSONObject;
import org.junit.Test;

public class PredictionHistoryTest {
    @Test
    public void keepsUnsentPredictionPastCutoff()
        throws Exception {
        JSONObject record = new JSONObject()
            .put(
                "predicted_at",
                "2026-07-20T08:00:00+09:00"
            );

        assertTrue(
            PredictionHistory.shouldRetain(
                record,
                Instant.parse(
                    "2026-07-28T00:00:00Z"
                )
            )
        );
    }

    @Test
    public void removesOnlyUploadedOldPrediction()
        throws Exception {
        JSONObject oldRecord = new JSONObject()
            .put(
                "predicted_at",
                "2026-07-20T08:00:00+09:00"
            )
            .put(
                "cloud_uploaded_at",
                "2026-07-20T08:01:00+09:00"
            );
        JSONObject recentRecord = new JSONObject()
            .put(
                "predicted_at",
                "2026-07-30T08:00:00+09:00"
            )
            .put(
                "cloud_uploaded_at",
                "2026-07-30T08:01:00+09:00"
            );
        Instant cutoff = Instant.parse(
            "2026-07-28T00:00:00Z"
        );

        assertFalse(
            PredictionHistory.shouldRetain(
                oldRecord,
                cutoff
            )
        );
        assertTrue(
            PredictionHistory.shouldRetain(
                recentRecord,
                cutoff
            )
        );
    }

    @Test
    public void makesSafeDeterministicFileName() {
        assertEquals(
            "keirin_prediction_a_b-c.json",
            DrivePredictionSync.fileName(
                "a/b-c"
            )
        );
    }
}
