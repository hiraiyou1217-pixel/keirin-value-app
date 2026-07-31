package jp.hirai.keirinai;

import android.content.ContentResolver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;

import androidx.documentfile.provider.DocumentFile;

import org.json.JSONObject;

import java.io.BufferedWriter;
import java.io.IOException;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class DrivePredictionSync {
    private static final String PREFERENCES =
        "prediction_drive_sync";
    private static final String FOLDER_URI =
        "folder_uri";
    private static final String FILE_PREFIX =
        "keirin_prediction_";

    private DrivePredictionSync() {
    }

    public static void saveFolder(
        Context context,
        Uri uri,
        int resultFlags
    ) {
        int flags = resultFlags
            & (
                Intent.FLAG_GRANT_READ_URI_PERMISSION
                | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
            );
        context.getContentResolver()
            .takePersistableUriPermission(
                uri,
                flags
            );
        preferences(context)
            .edit()
            .putString(
                FOLDER_URI,
                uri.toString()
            )
            .apply();
    }

    public static boolean isConfigured(
        Context context
    ) {
        return !folderUri(context).isBlank();
    }

    public static String status(
        Context context
    ) {
        if (!isConfigured(context)) {
            return "Google Drive保存先は未設定です。"
                + "\n初回だけ専用フォルダを"
                + "選択してください。";
        }

        return "Google Drive保存先: 設定済み"
            + "\n予測完了時とアプリ起動時に"
            + "未送信データを同期します。";
    }

    public static SyncResult syncPending(
        Context context
    ) throws IOException {
        String uriText = folderUri(context);

        if (uriText.isBlank()) {
            return SyncResult.notConfigured();
        }

        Uri treeUri = Uri.parse(uriText);
        DocumentFile directory =
            DocumentFile.fromTreeUri(
                context,
                treeUri
            );

        if (
            directory == null
            || !directory.exists()
            || !directory.isDirectory()
            || !directory.canWrite()
        ) {
            throw new IOException(
                "Google Drive保存先へ"
                    + "書き込めません。"
                    + "保存先を選び直してください。"
            );
        }

        Map<String, DocumentFile> existing =
            new HashMap<>();

        for (
            DocumentFile file
            : directory.listFiles()
        ) {
            String name = file.getName();

            if (name != null) {
                existing.put(name, file);
            }
        }

        List<JSONObject> pending =
            PredictionHistory.pending(context);
        Set<String> uploadedIds =
            new HashSet<>();
        int uploaded = 0;
        int replaced = 0;
        int failed = 0;
        String lastError = "";
        ContentResolver resolver =
            context.getContentResolver();

        for (JSONObject record : pending) {
            String predictionId =
                record.optString(
                    "prediction_id",
                    ""
                );

            if (predictionId.isBlank()) {
                failed += 1;
                lastError =
                    "予測IDがありません。";
                continue;
            }

            String fileName = fileName(
                predictionId
            );
            DocumentFile destination =
                existing.get(fileName);
            boolean created = false;

            try {
                if (destination == null) {
                    destination =
                        directory.createFile(
                            "application/json",
                            fileName
                        );
                    created = true;
                } else {
                    created = false;
                }

                if (destination == null) {
                    throw new IOException(
                        "Drive上にファイルを"
                            + "作成できません。"
                    );
                }

                writeJson(
                    resolver,
                    destination.getUri(),
                    record
                );

                if (created) {
                    uploaded += 1;
                } else {
                    replaced += 1;
                }

                uploadedIds.add(predictionId);
                existing.put(
                    destination.getName() == null
                        ? fileName
                        : destination.getName(),
                    destination
                );
            } catch (Exception exception) {
                failed += 1;
                lastError = String.valueOf(
                    exception.getMessage()
                );
            }
        }

        PredictionHistory.markUploaded(
            context,
            uploadedIds
        );
        int removed =
            PredictionHistory.cleanup(context);
        int remaining =
            PredictionHistory.pending(
                context
            ).size();

        return new SyncResult(
            true,
            uploaded,
            replaced,
            failed,
            remaining,
            removed,
            lastError
        );
    }

    static String fileName(
        String predictionId
    ) {
        String safe = predictionId.replaceAll(
            "[^A-Za-z0-9_-]",
            "_"
        );
        return FILE_PREFIX + safe + ".json";
    }

    private static void writeJson(
        ContentResolver resolver,
        Uri uri,
        JSONObject record
    ) throws IOException {
        OutputStream stream =
            resolver.openOutputStream(
                uri,
                "wt"
            );

        if (stream == null) {
            throw new IOException(
                "Driveファイルを開けません。"
            );
        }

        try (
            BufferedWriter writer =
                new BufferedWriter(
                    new OutputStreamWriter(
                        stream,
                        StandardCharsets.UTF_8
                    )
                )
        ) {
            writer.write(record.toString());
            writer.newLine();
        }
    }

    private static String folderUri(
        Context context
    ) {
        return preferences(context).getString(
            FOLDER_URI,
            ""
        );
    }

    private static SharedPreferences preferences(
        Context context
    ) {
        return context.getSharedPreferences(
            PREFERENCES,
            Context.MODE_PRIVATE
        );
    }

    public static final class SyncResult {
        public final boolean configured;
        public final int uploaded;
        public final int replaced;
        public final int failed;
        public final int remaining;
        public final int removed;
        public final String lastError;

        private SyncResult(
            boolean configured,
            int uploaded,
            int replaced,
            int failed,
            int remaining,
            int removed,
            String lastError
        ) {
            this.configured = configured;
            this.uploaded = uploaded;
            this.replaced = replaced;
            this.failed = failed;
            this.remaining = remaining;
            this.removed = removed;
            this.lastError = lastError;
        }

        private static SyncResult notConfigured() {
            return new SyncResult(
                false,
                0,
                0,
                0,
                0,
                0,
                ""
            );
        }

        public String summary() {
            if (!configured) {
                return "Drive保存先は未設定です。"
                    + "予測は端末内に保持しました。";
            }

            String summary =
                "Drive新規送信 "
                    + uploaded
                    + "件 / 再送 "
                    + replaced
                    + "件 / 未送信 "
                    + remaining
                    + "件";

            if (removed > 0) {
                summary += " / 3日経過削除 "
                    + removed
                    + "件";
            }

            if (failed > 0) {
                summary += " / 失敗 "
                    + failed
                    + "件";

                if (
                    lastError != null
                    && !lastError.isBlank()
                ) {
                    summary += "（"
                        + lastError
                        + "）";
                }
            }

            return summary;
        }
    }
}
