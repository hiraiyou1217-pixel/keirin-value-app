package jp.hirai.keirinai;

import android.content.Context;

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
import java.time.OffsetDateTime;
import java.util.ArrayDeque;
import java.util.Deque;

public final class PredictionHistory {
    private static final String FILENAME =
        "prediction_history.jsonl";

    private PredictionHistory() {
    }

    public static void append(
        Context context,
        JSONObject prediction
    ) throws IOException, JSONException {
        JSONObject stored = new JSONObject(
            prediction.toString()
        );
        stored.put(
            "predicted_at",
            OffsetDateTime.now().toString()
        );

        try (
            BufferedWriter writer =
                new BufferedWriter(
                    new OutputStreamWriter(
                        new FileOutputStream(
                            file(context),
                            true
                        ),
                        StandardCharsets.UTF_8
                    )
                )
        ) {
            writer.write(stored.toString());
            writer.newLine();
        }
    }

    public static String summary(
        Context context
    ) throws IOException {
        File source = file(context);

        if (!source.exists()) {
            return "端末内予測履歴: 0件";
        }

        int count = 0;
        Deque<String> latest =
            new ArrayDeque<>();

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

                count += 1;

                try {
                    JSONObject row =
                        new JSONObject(line);
                    JSONObject target =
                        row.optJSONObject(
                            "target"
                        );
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
                } catch (
                    JSONException ignored
                ) {
                    latest.addLast(
                        "読取不能な履歴"
                    );
                }
            }
        }

        StringBuilder output =
            new StringBuilder(
                "端末内予測履歴: "
                    + count
                    + "件"
            );

        if (!latest.isEmpty()) {
            output.append("\n直近5件");

            for (String item : latest) {
                output.append("\n").append(item);
            }
        }

        return output.toString();
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
