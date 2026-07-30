package jp.hirai.keirinai;

import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.net.Uri;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

public final class AiBundleImporter {
    public static final String ACTIVE_DIRECTORY =
        "ai_bundle";
    public static final String MODEL_FILENAME =
        "portable_model.json";
    public static final String DATABASE_FILENAME =
        "keirin_learning.db";
    public static final String MANIFEST_FILENAME =
        "bundle_manifest.json";
    private static final String BUNDLE_FORMAT =
        "keirin_android_ai_bundle_v1";
    private static final Set<String> EXPECTED_FILES =
        Set.of(
            MODEL_FILENAME,
            DATABASE_FILENAME,
            MANIFEST_FILENAME
        );
    private static final long MODEL_LIMIT =
        100L * 1024L * 1024L;
    private static final long DATABASE_LIMIT =
        1024L * 1024L * 1024L;
    private static final long MANIFEST_LIMIT =
        2L * 1024L * 1024L;

    private AiBundleImporter() {
    }

    public static final class ImportResult {
        private final JSONObject manifest;

        ImportResult(JSONObject manifest) {
            this.manifest = manifest;
        }

        public JSONObject getManifest() {
            return manifest;
        }

        public String summary() {
            JSONObject model = manifest.optJSONObject(
                "model"
            );
            JSONObject database =
                manifest.optJSONObject("database");
            String trainedAt = model == null
                ? ""
                : model.optString(
                    "trained_at",
                    ""
                );
            int raceCount = database == null
                ? 0
                : database.optInt(
                    "race_count",
                    0
                );
            String lastDate = database == null
                ? ""
                : database.optString(
                    "last_race_date",
                    ""
                );

            return "AIデータ取込済み"
                + "\n学習日時: "
                + (
                    trainedAt.isBlank()
                        ? "不明"
                        : trainedAt
                )
                + "\nDBレース数: "
                + raceCount
                + "件"
                + "\n最終収集日: "
                + (
                    lastDate.isBlank()
                        ? "不明"
                        : lastDate
                );
        }
    }

    public static ImportResult importBundle(
        Context context,
        Uri sourceUri
    ) throws IOException, JSONException {
        File filesDirectory = context.getFilesDir();
        File stage = new File(
            filesDirectory,
            ".ai_import_" + UUID.randomUUID()
        );

        if (!stage.mkdir()) {
            throw new IOException(
                "取込用フォルダを作成できません。"
            );
        }

        try {
            extractExpectedFiles(
                context,
                sourceUri,
                stage
            );
            JSONObject manifest = verifyStage(stage);
            activateStage(filesDirectory, stage);
            return new ImportResult(manifest);
        } catch (
            IOException
            | JSONException
            | RuntimeException exception
        ) {
            deleteRecursively(stage);
            throw exception;
        }
    }

    private static void extractExpectedFiles(
        Context context,
        Uri sourceUri,
        File stage
    ) throws IOException {
        InputStream opened = context
            .getContentResolver()
            .openInputStream(sourceUri);

        if (opened == null) {
            throw new IOException(
                "選択したZIPを開けません。"
            );
        }

        Set<String> extracted = new HashSet<>();

        try (
            ZipInputStream archive =
                new ZipInputStream(
                    new BufferedInputStream(opened)
                )
        ) {
            ZipEntry entry;

            while (
                (entry = archive.getNextEntry())
                != null
            ) {
                String name = entry.getName();

                if (
                    entry.isDirectory()
                    || !EXPECTED_FILES.contains(name)
                    || !new File(name)
                        .getName()
                        .equals(name)
                ) {
                    throw new IOException(
                        "ZIP内に許可されていない"
                            + "項目があります: "
                            + name
                    );
                }

                if (!extracted.add(name)) {
                    throw new IOException(
                        "ZIP内ファイルが重複しています: "
                            + name
                    );
                }

                long limit = limitFor(name);
                File destination = new File(
                    stage,
                    name
                );
                long written = 0;
                byte[] buffer = new byte[64 * 1024];

                try (
                    BufferedOutputStream output =
                        new BufferedOutputStream(
                            new FileOutputStream(
                                destination
                            )
                        )
                ) {
                    int count;

                    while (
                        (count = archive.read(buffer))
                        != -1
                    ) {
                        written += count;

                        if (written > limit) {
                            throw new IOException(
                                "ZIP内ファイルが"
                                    + "上限を超えています: "
                                    + name
                            );
                        }

                        output.write(
                            buffer,
                            0,
                            count
                        );
                    }
                }

                archive.closeEntry();
            }
        }

        if (!extracted.equals(EXPECTED_FILES)) {
            Set<String> missing = new HashSet<>(
                EXPECTED_FILES
            );
            missing.removeAll(extracted);
            throw new IOException(
                "ZIPに必要なファイルがありません: "
                    + String.join("、", missing)
            );
        }
    }

    private static long limitFor(String name) {
        if (MODEL_FILENAME.equals(name)) {
            return MODEL_LIMIT;
        }

        if (DATABASE_FILENAME.equals(name)) {
            return DATABASE_LIMIT;
        }

        return MANIFEST_LIMIT;
    }

    private static JSONObject verifyStage(
        File stage
    ) throws IOException, JSONException {
        File manifestFile = new File(
            stage,
            MANIFEST_FILENAME
        );
        JSONObject manifest = new JSONObject(
            Files.readString(
                manifestFile.toPath(),
                StandardCharsets.UTF_8
            )
        );

        if (
            !BUNDLE_FORMAT.equals(
                manifest.optString("format")
            )
            || !manifest.optBoolean(
                "odds_independent",
                false
            )
        ) {
            throw new IOException(
                "オッズ非依存AI用ZIPではありません。"
            );
        }

        JSONObject validation =
            manifest.optJSONObject("validation");

        if (
            validation == null
            || !"ok".equals(
                validation.optString("status")
            )
        ) {
            throw new IOException(
                "Mac版との確率一致検証が"
                    + "完了していません。"
            );
        }

        JSONObject files = manifest.optJSONObject(
            "files"
        );

        if (files == null) {
            throw new IOException(
                "ZIPの検証情報がありません。"
            );
        }

        for (String name : Set.of(
            MODEL_FILENAME,
            DATABASE_FILENAME
        )) {
            File file = new File(stage, name);
            JSONObject expected =
                files.optJSONObject(name);

            if (expected == null) {
                throw new IOException(
                    "検証情報が不足しています: "
                        + name
                );
            }

            if (
                expected.optLong(
                    "size_bytes",
                    -1
                )
                != file.length()
                || !expected.optString(
                    "sha256",
                    ""
                ).equalsIgnoreCase(
                    sha256(file)
                )
            ) {
                throw new IOException(
                    "ZIPのチェックサムが"
                        + "一致しません: "
                        + name
                );
            }
        }

        JSONObject model = new JSONObject(
            Files.readString(
                new File(
                    stage,
                    MODEL_FILENAME
                ).toPath(),
                StandardCharsets.UTF_8
            )
        );

        if (
            !"keirin_hgb_binary_v1".equals(
                model.optString("format")
            )
            || !model.optBoolean(
                "odds_independent",
                false
            )
            || model.optInt(
                "feature_count",
                0
            ) <= 0
        ) {
            throw new IOException(
                "端末モデルの形式が不正です。"
            );
        }

        verifyDatabase(
            new File(
                stage,
                DATABASE_FILENAME
            )
        );
        return manifest;
    }

    private static void verifyDatabase(
        File databaseFile
    ) throws IOException {
        SQLiteDatabase database = null;

        try {
            database = SQLiteDatabase.openDatabase(
                databaseFile.getAbsolutePath(),
                null,
                SQLiteDatabase.OPEN_READONLY
            );

            try (
                Cursor cursor = database.rawQuery(
                    "PRAGMA integrity_check",
                    null
                )
            ) {
                if (
                    !cursor.moveToFirst()
                    || !"ok".equalsIgnoreCase(
                        cursor.getString(0)
                    )
                ) {
                    throw new IOException(
                        "SQLite整合性NGです。"
                    );
                }
            }

            for (String table : Set.of(
                "races",
                "riders"
            )) {
                try (
                    Cursor cursor = database.rawQuery(
                        "SELECT COUNT(*) FROM "
                            + table,
                        null
                    )
                ) {
                    if (!cursor.moveToFirst()) {
                        throw new IOException(
                            "SQLiteテーブルを"
                                + "確認できません: "
                                + table
                        );
                    }
                }
            }
        } catch (RuntimeException exception) {
            throw new IOException(
                "SQLiteを開けません: "
                    + exception.getMessage(),
                exception
            );
        } finally {
            if (database != null) {
                database.close();
            }
        }
    }

    private static void activateStage(
        File filesDirectory,
        File stage
    ) throws IOException {
        File active = new File(
            filesDirectory,
            ACTIVE_DIRECTORY
        );
        File previous = new File(
            filesDirectory,
            ACTIVE_DIRECTORY + "_previous"
        );
        deleteRecursively(previous);
        boolean movedOld = false;

        if (active.exists()) {
            if (!active.renameTo(previous)) {
                throw new IOException(
                    "現在のAIデータを"
                        + "退避できません。"
                );
            }

            movedOld = true;
        }

        if (!stage.renameTo(active)) {
            if (movedOld) {
                previous.renameTo(active);
            }

            throw new IOException(
                "検証済みAIデータを"
                    + "有効化できません。"
            );
        }
    }

    public static ImportResult current(
        Context context
    ) throws IOException, JSONException {
        File manifestFile = getManifestFile(
            context
        );

        if (!manifestFile.exists()) {
            return null;
        }

        JSONObject manifest = new JSONObject(
            Files.readString(
                manifestFile.toPath(),
                StandardCharsets.UTF_8
            )
        );
        return new ImportResult(manifest);
    }

    public static boolean isReady(
        Context context
    ) {
        return getModelFile(context).isFile()
            && getDatabaseFile(context).isFile()
            && getManifestFile(context).isFile();
    }

    public static File getModelFile(
        Context context
    ) {
        return new File(
            new File(
                context.getFilesDir(),
                ACTIVE_DIRECTORY
            ),
            MODEL_FILENAME
        );
    }

    public static File getDatabaseFile(
        Context context
    ) {
        return new File(
            new File(
                context.getFilesDir(),
                ACTIVE_DIRECTORY
            ),
            DATABASE_FILENAME
        );
    }

    private static File getManifestFile(
        Context context
    ) {
        return new File(
            new File(
                context.getFilesDir(),
                ACTIVE_DIRECTORY
            ),
            MANIFEST_FILENAME
        );
    }

    private static String sha256(
        File file
    ) throws IOException {
        try {
            MessageDigest digest = MessageDigest
                .getInstance("SHA-256");
            byte[] buffer = new byte[64 * 1024];

            try (
                BufferedInputStream input =
                    new BufferedInputStream(
                        new FileInputStream(file)
                    )
            ) {
                int count;

                while (
                    (count = input.read(buffer))
                    != -1
                ) {
                    digest.update(
                        buffer,
                        0,
                        count
                    );
                }
            }

            StringBuilder output =
                new StringBuilder();

            for (byte value : digest.digest()) {
                output.append(
                    String.format(
                        Locale.ROOT,
                        "%02x",
                        value & 0xff
                    )
                );
            }

            return output.toString();
        } catch (
            NoSuchAlgorithmException exception
        ) {
            throw new IOException(
                "SHA-256を利用できません。",
                exception
            );
        }
    }

    private static void deleteRecursively(
        File target
    ) {
        if (
            target == null
            || !target.exists()
        ) {
            return;
        }

        File[] children = target.listFiles();

        if (children != null) {
            for (File child : children) {
                deleteRecursively(child);
            }
        }

        target.delete();
    }
}
