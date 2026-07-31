package jp.hirai.keirinai;

import android.content.Context;
import android.util.AtomicFile;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeParseException;
import java.time.temporal.ChronoUnit;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Set;
import java.util.UUID;

public final class PredictionHistory {
    public static final int RETENTION_DAYS = 3;
    public static final String FORMAT =
        "keirin_android_prediction_v1";
    private static final String FILENAME =
        "prediction_history.jsonl";

    private PredictionHistory() {
    }

    public static JSONObject append(
        Context context,
        JSONObject prediction
    ) throws IOException, JSONException {
        JSONObject stored = new JSONObject(
            prediction.toString()
        );
        stored.put("format", FORMAT);
        stored.put(
            "prediction_id",
            UUID.randomUUID().toString()
        );
        stored.put(
            "predicted_at",
            OffsetDateTime.now().toString()
        );
        stored.put(
            "source_device",
            "android"
        );

        List<JSONObject> records =
            readRecords(context);
        records.add(stored);
        writeRecords(context, records);
        return stored;
    }

    public static List<JSONObject> pending(
        Context context
    ) throws IOException {
        List<JSONObject> output =
            new ArrayList<>();

        for (
            JSONObject record
            : readRecords(context)
        ) {
            if (
                record.optString(
                    "cloud_uploaded_at",
                    ""
                ).isBlank()
            ) {
                output.add(record);
            }
        }

        return output;
    }

    public static void markUploaded(
        Context context,
        Set<String> predictionIds
    ) throws IOException {
        if (predictionIds.isEmpty()) {
            return;
        }

        String uploadedAt =
            OffsetDateTime.now().toString();
        List<JSONObject> records =
            readRecords(context);

        for (JSONObject record : records) {
            if (
                predictionIds.contains(
                    record.optString(
                        "prediction_id",
                        ""
                    )
                )
            ) {
                try {
                    record.put(
                        "cloud_uploaded_at",
                        uploadedAt
                    );
                } catch (
                    JSONException exception
                ) {
                    throw new IOException(
                        "同期済み状態を保存できません。",
                        exception
                    );
                }
            }
        }

        writeRecords(context, records);
    }

    public static int cleanup(
        Context context
    ) throws IOException {
        List<JSONObject> records =
            readRecords(context);
        List<JSONObject> retained =
            new ArrayList<>();
        Instant cutoff = Instant.now().minus(
            RETENTION_DAYS,
            ChronoUnit.DAYS
        );

        for (JSONObject record : records) {
            if (
                shouldRetain(
                    record,
                    cutoff
                )
            ) {
                retained.add(record);
            }
        }

        writeRecords(context, retained);
        return records.size() - retained.size();
    }

    static boolean shouldRetain(
        JSONObject record,
        Instant cutoff
    ) {
        if (
            record.optString(
                "cloud_uploaded_at",
                ""
            ).isBlank()
        ) {
            return true;
        }

        Instant predictedAt = parseInstant(
            record.optString(
                "predicted_at",
                ""
            )
        );
        return predictedAt == null
            || !predictedAt.isBefore(cutoff);
    }

    public static String summary(
        Context context
    ) throws IOException {
        List<JSONObject> records =
            readRecords(context);
        int pendingCount = 0;
        Deque<String> latest =
            new ArrayDeque<>();

        for (JSONObject row : records) {
            if (
                row.optString(
                    "cloud_uploaded_at",
                    ""
                ).isBlank()
            ) {
                pendingCount += 1;
            }

            JSONObject target =
                row.optJSONObject("target");
            String predictedAt =
                row.optString(
                    "predicted_at",
                    ""
                );
            String label = target == null
                ? "対象不明"
                : (
                    target.optString(
                        "race_date",
                        ""
                    )
                    + " "
                    + target.optString(
                        "venue",
                        ""
                    )
                    + " "
                    + target.optInt(
                        "race_number",
                        0
                    )
                    + "R"
                );
            latest.addLast(
                predictedAt + "  " + label
            );

            if (latest.size() > 5) {
                latest.removeFirst();
            }
        }

        StringBuilder output =
            new StringBuilder(
                "端末内予測履歴: "
                    + records.size()
                    + "件"
                    + "\n未送信: "
                    + pendingCount
                    + "件"
                    + " / Drive送信済み: "
                    + (
                        records.size()
                        - pendingCount
                    )
                    + "件"
                    + "\n送信済み履歴は"
                    + RETENTION_DAYS
                    + "日後に端末から削除"
            );

        if (!latest.isEmpty()) {
            output.append("\n直近5件");

            for (String item : latest) {
                output.append("\n").append(item);
            }
        }

        return output.toString();
    }

    private static List<JSONObject> readRecords(
        Context context
    ) throws IOException {
        File source = file(context);
        List<JSONObject> records =
            new ArrayList<>();

        if (!source.exists()) {
            return records;
        }

        try (
            BufferedReader reader =
                new BufferedReader(
                    new InputStreamReader(
                        new FileInputStream(
                            source
                        ),
                        StandardCharsets.UTF_8
                    )
                )
        ) {
            String line;

            while (
                (line = reader.readLine())
                != null
            ) {
                if (line.isBlank()) {
                    continue;
                }

                try {
                    JSONObject record =
                        new JSONObject(line);
                    ensureIdentity(record);
                    records.add(record);
                } catch (
                    JSONException exception
                ) {
                    throw new IOException(
                        "端末内予測履歴に"
                            + "読取不能な行があります。",
                        exception
                    );
                }
            }
        }

        return records;
    }

    private static void ensureIdentity(
        JSONObject record
    ) throws JSONException {
        if (
            record.optString(
                "format",
                ""
            ).isBlank()
        ) {
            record.put("format", FORMAT);
        }

        if (
            record.optString(
                "prediction_id",
                ""
            ).isBlank()
        ) {
            String identitySource =
                record.toString();
            record.put(
                "prediction_id",
                UUID.nameUUIDFromBytes(
                    identitySource.getBytes(
                        StandardCharsets.UTF_8
                    )
                ).toString()
            );
        }
    }

    private static void writeRecords(
        Context context,
        List<JSONObject> records
    ) throws IOException {
        AtomicFile target = new AtomicFile(
            file(context)
        );
        FileOutputStream stream = null;
        BufferedWriter writer = null;

        try {
            stream = target.startWrite();
            writer = new BufferedWriter(
                new OutputStreamWriter(
                    stream,
                    StandardCharsets.UTF_8
                )
            );

            for (
                JSONObject record
                : records
            ) {
                writer.write(
                    record.toString()
                );
                writer.newLine();
            }

            writer.flush();
            target.finishWrite(stream);
        } catch (IOException exception) {
            if (stream != null) {
                target.failWrite(stream);
            }

            throw exception;
        }
    }

    private static Instant parseInstant(
        String value
    ) {
        if (value == null || value.isBlank()) {
            return null;
        }

        try {
            return OffsetDateTime.parse(
                value
            ).toInstant();
        } catch (
            DateTimeParseException ignored
        ) {
            try {
                return LocalDateTime.parse(
                    value
                ).atZone(
                    ZoneId.systemDefault()
                ).toInstant();
            } catch (
                DateTimeParseException alsoIgnored
            ) {
                return null;
            }
        }
    }

    private static File file(
        Context context
    ) {
        return new File(
            context.getFilesDir(),
            FILENAME
        );
    }
}
