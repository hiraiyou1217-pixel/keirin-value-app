package jp.hirai.keirinai;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.DatePickerDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import org.json.JSONTokener;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Calendar;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private static final int IMPORT_BUNDLE_REQUEST = 1201;
    private static final String DESKTOP_USER_AGENT =
        "Mozilla/5.0 (X11; Linux x86_64) "
            + "AppleWebKit/537.36 (KHTML, like Gecko) "
            + "Chrome/126.0 Safari/537.36";
    private static final int BACKGROUND = Color.rgb(
        247,
        248,
        250
    );
    private static final int CARD_BACKGROUND = Color.WHITE;
    private static final int PRIMARY = Color.rgb(0, 108, 76);
    private static final int ERROR = Color.rgb(177, 31, 40);
    private static final int MUTED = Color.rgb(88, 96, 105);

    private final Handler handler = new Handler(
        Looper.getMainLooper()
    );
    private final ExecutorService worker =
        Executors.newSingleThreadExecutor();
    private EditText urlInput;
    private Button fetchButton;
    private Button selectRaceButton;
    private Button importButton;
    private Button predictButton;
    private ProgressBar progressBar;
    private TextView statusView;
    private TextView bundleStatusView;
    private TextView targetView;
    private TextView lineupView;
    private TextView diagnosticsView;
    private TextView historyView;
    private LinearLayout riderContainer;
    private LinearLayout predictionContainer;
    private WebView webView;
    private String extractorScript = "";
    private String catalogScript = "";
    private String requestedUrl = "";
    private String latestDiagnostics = "";
    private JSONObject latestRacePayload;
    private LoadMode loadMode = LoadMode.NONE;

    private enum LoadMode {
        NONE,
        CATALOG,
        RACE
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        extractorScript = readAsset(
            "extract_racecard.js"
        );
        catalogScript = readAsset(
            "extract_catalog.js"
        );
        setContentView(buildScreen());
        configureWebView();
        updateBundleStatus();
        updateHistory();

        String savedUrl = getPreferences(MODE_PRIVATE)
            .getString("racecard_url", "");
        if (!savedUrl.isBlank()) {
            urlInput.setText(savedUrl);
        }
    }

    private View buildScreen() {
        ScrollView scrollView = new ScrollView(this);
        scrollView.setFillViewport(true);
        scrollView.setBackgroundColor(BACKGROUND);

        LinearLayout root = verticalLayout();
        root.setPadding(dp(16), dp(18), dp(16), dp(40));
        scrollView.addView(
            root,
            matchWrap()
        );

        TextView title = text(
            "オッズ非依存AI",
            26,
            Color.rgb(25, 32, 38)
        );
        title.setTypeface(
            title.getTypeface(),
            android.graphics.Typeface.BOLD
        );
        root.addView(title, matchWrap());

        TextView version = text(
            "Galaxy Z Fold5 端末内AI版 0.2",
            13,
            MUTED
        );
        LinearLayout.LayoutParams versionParams = matchWrap();
        versionParams.setMargins(0, dp(2), 0, dp(18));
        root.addView(version, versionParams);

        root.addView(
            infoCard(
                "Macで作成した検証済みAIデータZIPを"
                    + "一度取り込むと、WINTICKETの"
                    + "出走表からオッズを使わず"
                    + "スマホ本体だけで予測します。"
            ),
            matchWrap()
        );

        TextView bundleLabel = label(
            "AIデータ"
        );
        LinearLayout.LayoutParams bundleLabelParams =
            matchWrap();
        bundleLabelParams.setMargins(
            0,
            dp(18),
            0,
            dp(6)
        );
        root.addView(
            bundleLabel,
            bundleLabelParams
        );

        bundleStatusView = text(
            "AIデータは未取込です。",
            14,
            MUTED
        );
        bundleStatusView.setPadding(
            dp(12),
            dp(12),
            dp(12),
            dp(12)
        );
        bundleStatusView.setBackgroundColor(
            Color.WHITE
        );
        root.addView(
            bundleStatusView,
            matchWrap()
        );

        importButton = button(
            "AIデータZIPを取り込む"
        );
        importButton.setOnClickListener(
            ignored -> chooseBundle()
        );
        LinearLayout.LayoutParams importParams =
            matchWrap();
        importParams.setMargins(
            0,
            dp(8),
            0,
            0
        );
        root.addView(
            importButton,
            importParams
        );

        selectRaceButton = button(
            "日付からレースを選ぶ"
        );
        selectRaceButton.setTextColor(Color.WHITE);
        selectRaceButton.setBackgroundColor(PRIMARY);
        selectRaceButton.setOnClickListener(
            ignored -> chooseRaceDate()
        );
        LinearLayout.LayoutParams selectParams =
            matchWrap();
        selectParams.setMargins(
            0,
            dp(18),
            0,
            0
        );
        root.addView(
            selectRaceButton,
            selectParams
        );

        TextView inputLabel = label(
            "または WINTICKET 出走表URL"
        );
        LinearLayout.LayoutParams labelParams = matchWrap();
        labelParams.setMargins(0, dp(18), 0, dp(6));
        root.addView(inputLabel, labelParams);

        urlInput = new EditText(this);
        urlInput.setHint(
            "https://www.winticket.jp/keirin/..."
        );
        urlInput.setTextSize(15);
        urlInput.setTextColor(Color.rgb(20, 25, 30));
        urlInput.setHintTextColor(Color.rgb(130, 138, 145));
        urlInput.setSingleLine(false);
        urlInput.setMinLines(2);
        urlInput.setMaxLines(4);
        urlInput.setInputType(
            InputType.TYPE_CLASS_TEXT
                | InputType.TYPE_TEXT_VARIATION_URI
        );
        urlInput.setPadding(
            dp(12),
            dp(10),
            dp(12),
            dp(10)
        );
        urlInput.setBackgroundColor(CARD_BACKGROUND);
        root.addView(urlInput, matchWrap());

        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        actions.setGravity(Gravity.CENTER_VERTICAL);

        Button pasteButton = button("貼り付け");
        pasteButton.setOnClickListener(
            ignored -> pasteUrl()
        );
        LinearLayout.LayoutParams pasteParams = new LinearLayout.LayoutParams(
            0,
            dp(50),
            1f
        );
        pasteParams.setMargins(0, dp(10), dp(6), 0);
        actions.addView(pasteButton, pasteParams);

        fetchButton = button("出走表を取得");
        fetchButton.setTextColor(Color.WHITE);
        fetchButton.setBackgroundColor(PRIMARY);
        fetchButton.setOnClickListener(
            ignored -> startFetch()
        );
        LinearLayout.LayoutParams fetchParams = new LinearLayout.LayoutParams(
            0,
            dp(50),
            2f
        );
        fetchParams.setMargins(dp(6), dp(10), 0, 0);
        actions.addView(fetchButton, fetchParams);
        root.addView(actions, matchWrap());

        progressBar = new ProgressBar(
            this,
            null,
            android.R.attr.progressBarStyleHorizontal
        );
        progressBar.setIndeterminate(true);
        progressBar.setVisibility(View.GONE);
        LinearLayout.LayoutParams progressParams = matchWrap();
        progressParams.setMargins(0, dp(12), 0, 0);
        root.addView(progressBar, progressParams);

        statusView = text(
            "出走表URLを貼り付けてください。",
            15,
            MUTED
        );
        statusView.setPadding(
            dp(12),
            dp(12),
            dp(12),
            dp(12)
        );
        statusView.setBackgroundColor(Color.WHITE);
        LinearLayout.LayoutParams statusParams = matchWrap();
        statusParams.setMargins(0, dp(12), 0, 0);
        root.addView(statusView, statusParams);

        targetView = label("");
        targetView.setVisibility(View.GONE);
        LinearLayout.LayoutParams targetParams = matchWrap();
        targetParams.setMargins(0, dp(22), 0, dp(8));
        root.addView(targetView, targetParams);

        riderContainer = verticalLayout();
        root.addView(riderContainer, matchWrap());

        lineupView = text("", 14, Color.rgb(30, 36, 41));
        lineupView.setPadding(
            dp(12),
            dp(12),
            dp(12),
            dp(12)
        );
        lineupView.setBackgroundColor(Color.WHITE);
        lineupView.setVisibility(View.GONE);
        LinearLayout.LayoutParams lineupParams = matchWrap();
        lineupParams.setMargins(0, dp(14), 0, 0);
        root.addView(lineupView, lineupParams);

        predictButton = button(
            "オッズ非依存AIで予測"
        );
        predictButton.setTextColor(Color.WHITE);
        predictButton.setBackgroundColor(PRIMARY);
        predictButton.setEnabled(false);
        predictButton.setOnClickListener(
            ignored -> startPrediction()
        );
        LinearLayout.LayoutParams predictParams =
            matchWrap();
        predictParams.setMargins(
            0,
            dp(14),
            0,
            0
        );
        root.addView(
            predictButton,
            predictParams
        );

        predictionContainer = verticalLayout();
        LinearLayout.LayoutParams predictionParams =
            matchWrap();
        predictionParams.setMargins(
            0,
            dp(14),
            0,
            0
        );
        root.addView(
            predictionContainer,
            predictionParams
        );

        TextView historyLabel = label(
            "端末内予測履歴"
        );
        LinearLayout.LayoutParams historyLabelParams =
            matchWrap();
        historyLabelParams.setMargins(
            0,
            dp(22),
            0,
            dp(6)
        );
        root.addView(
            historyLabel,
            historyLabelParams
        );

        historyView = text(
            "端末内予測履歴: 0件",
            13,
            MUTED
        );
        historyView.setPadding(
            dp(12),
            dp(12),
            dp(12),
            dp(12)
        );
        historyView.setBackgroundColor(
            Color.WHITE
        );
        root.addView(
            historyView,
            matchWrap()
        );

        TextView diagnosticsLabel = label(
            "検証ログ"
        );
        LinearLayout.LayoutParams diagnosticsLabelParams =
            matchWrap();
        diagnosticsLabelParams.setMargins(
            0,
            dp(22),
            0,
            dp(6)
        );
        root.addView(
            diagnosticsLabel,
            diagnosticsLabelParams
        );

        diagnosticsView = text(
            "まだ取得していません。",
            12,
            MUTED
        );
        diagnosticsView.setTextIsSelectable(true);
        diagnosticsView.setPadding(
            dp(12),
            dp(12),
            dp(12),
            dp(12)
        );
        diagnosticsView.setBackgroundColor(
            Color.rgb(238, 241, 243)
        );
        root.addView(diagnosticsView, matchWrap());

        Button copyButton = button("検証ログをコピー");
        copyButton.setOnClickListener(
            ignored -> copyDiagnostics()
        );
        LinearLayout.LayoutParams copyParams = matchWrap();
        copyParams.setMargins(0, dp(8), 0, 0);
        root.addView(copyButton, copyParams);

        webView = new WebView(this);
        webView.setVisibility(View.INVISIBLE);
        root.addView(
            webView,
            new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                1
            )
        );

        return scrollView;
    }

    private void configureWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setLoadsImagesAutomatically(true);
        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUserAgentString(DESKTOP_USER_AGENT);
        settings.setMixedContentMode(
            WebSettings.MIXED_CONTENT_NEVER_ALLOW
        );
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance()
            .setAcceptThirdPartyCookies(webView, true);
        webView.setWebChromeClient(new WebChromeClient());
        webView.setWebViewClient(
            new WebViewClient() {
                @Override
                public boolean shouldOverrideUrlLoading(
                    WebView view,
                    WebResourceRequest request
                ) {
                    Uri uri = request.getUrl();
                    String host = uri.getHost();
                    return host == null
                        || !(
                            host.equals("www.winticket.jp")
                            || host.equals("winticket.jp")
                        );
                }

                @Override
                public void onPageFinished(
                    WebView view,
                    String url
                ) {
                    super.onPageFinished(view, url);

                    if (
                        requestedUrl.isBlank()
                        || !url.startsWith(
                            requestedUrl
                        )
                    ) {
                        return;
                    }

                    if (
                        loadMode
                        == LoadMode.CATALOG
                    ) {
                        setStatus(
                            "開催一覧を読み込みました。"
                                + "レースを探しています…",
                            MUTED
                        );
                        handler.postDelayed(
                            MainActivity.this
                                ::evaluateCatalog,
                            4500
                        );
                    } else if (
                        loadMode
                        == LoadMode.RACE
                    ) {
                        setStatus(
                            "ページを読み込みました。"
                                + "出走表の描画を"
                                + "待っています…",
                            MUTED
                        );
                        handler.postDelayed(
                            MainActivity.this
                                ::evaluateRaceCard,
                            4500
                        );
                    }
                }

                @Override
                public void onReceivedError(
                    WebView view,
                    WebResourceRequest request,
                    WebResourceError error
                ) {
                    super.onReceivedError(
                        view,
                        request,
                        error
                    );

                    if (request.isForMainFrame()) {
                        finishWithError(
                            "ページを開けませんでした: "
                                + error.getDescription()
                        );
                    }
                }
            }
        );
    }

    private void chooseBundle() {
        Intent intent = new Intent(
            Intent.ACTION_OPEN_DOCUMENT
        );
        intent.addCategory(
            Intent.CATEGORY_OPENABLE
        );
        intent.setType("*/*");
        intent.putExtra(
            Intent.EXTRA_MIME_TYPES,
            new String[] {
                "application/zip",
                "application/x-zip-compressed",
                "application/octet-stream",
            }
        );
        startActivityForResult(
            intent,
            IMPORT_BUNDLE_REQUEST
        );
    }

    @Override
    protected void onActivityResult(
        int requestCode,
        int resultCode,
        Intent data
    ) {
        super.onActivityResult(
            requestCode,
            resultCode,
            data
        );

        if (
            requestCode != IMPORT_BUNDLE_REQUEST
            || resultCode != RESULT_OK
            || data == null
            || data.getData() == null
        ) {
            return;
        }

        Uri uri = data.getData();
        setBusy(true);
        setStatus(
            "AIデータZIPを検証して"
                + "取り込んでいます…",
            MUTED
        );
        worker.execute(() -> {
            try {
                AiBundleImporter.ImportResult result =
                    AiBundleImporter.importBundle(
                        this,
                        uri
                    );
                handler.post(() -> {
                    bundleStatusView.setText(
                        result.summary()
                    );
                    bundleStatusView.setTextColor(
                        PRIMARY
                    );
                    setStatus(
                        "AIデータを安全に"
                            + "取り込みました。",
                        PRIMARY
                    );
                    finishLoading();
                    updatePredictButton();
                });
            } catch (Exception exception) {
                handler.post(() -> {
                    setStatus(
                        "AIデータ取込エラー: "
                            + exception.getMessage(),
                        ERROR
                    );
                    finishLoading();
                });
            }
        });
    }

    private void updateBundleStatus() {
        try {
            AiBundleImporter.ImportResult result =
                AiBundleImporter.current(this);

            if (result == null) {
                bundleStatusView.setText(
                    "AIデータは未取込です。"
                );
                bundleStatusView.setTextColor(MUTED);
            } else {
                bundleStatusView.setText(
                    result.summary()
                );
                bundleStatusView.setTextColor(
                    PRIMARY
                );
            }
        } catch (Exception exception) {
            bundleStatusView.setText(
                "AIデータ状態を確認できません: "
                    + exception.getMessage()
            );
            bundleStatusView.setTextColor(ERROR);
        }

        updatePredictButton();
    }

    private void chooseRaceDate() {
        Calendar now = Calendar.getInstance(
            Locale.JAPAN
        );
        DatePickerDialog dialog =
            new DatePickerDialog(
                this,
                (view, year, month, day) -> {
                    String dateText = String.format(
                        Locale.ROOT,
                        "%04d%02d%02d",
                        year,
                        month + 1,
                        day
                    );
                    loadCatalog(dateText);
                },
                now.get(Calendar.YEAR),
                now.get(Calendar.MONTH),
                now.get(Calendar.DAY_OF_MONTH)
            );
        dialog.show();
    }

    private void loadCatalog(String dateText) {
        if (catalogScript.isBlank()) {
            setStatus(
                "開催一覧の抽出プログラムを"
                    + "読み込めませんでした。",
                ERROR
            );
            return;
        }

        requestedUrl =
            "https://www.winticket.jp/"
                + "keirin/racecard/"
                + dateText;
        loadMode = LoadMode.CATALOG;
        setBusy(true);
        clearResult();
        setStatus(
            "指定日の開催一覧を"
                + "読み込んでいます…",
            MUTED
        );
        webView.stopLoading();
        webView.loadUrl(requestedUrl);
    }

    private void evaluateCatalog() {
        webView.evaluateJavascript(
            catalogScript,
            this::handleCatalogResult
        );
    }

    private void handleCatalogResult(
        String rawValue
    ) {
        try {
            JSONObject root = decodeJavascriptObject(
                rawValue
            );

            if (!root.optBoolean("ok", false)) {
                finishWithError(
                    root.optString(
                        "error",
                        "開催レースを"
                            + "取得できませんでした。"
                    )
                );
                return;
            }

            JSONArray races = root.optJSONArray(
                "races"
            );

            if (
                races == null
                || races.length() == 0
            ) {
                finishWithError(
                    "開催レースがありません。"
                );
                return;
            }

            String[] labels =
                new String[races.length()];

            for (
                int index = 0;
                index < races.length();
                index++
            ) {
                JSONObject race =
                    races.getJSONObject(index);
                labels[index] = race.optString(
                    "venue",
                    ""
                )
                    + "  "
                    + race.optInt(
                        "raceNumber",
                        0
                    )
                    + "R";
            }

            loadMode = LoadMode.NONE;
            finishLoading();
            new AlertDialog.Builder(this)
                .setTitle(
                    races.length()
                        + "レースから選択"
                )
                .setItems(
                    labels,
                    (dialog, index) -> {
                        JSONObject race =
                            races.optJSONObject(
                                index
                            );

                        if (race == null) {
                            return;
                        }

                        String url = race.optString(
                            "url",
                            ""
                        );
                        urlInput.setText(url);
                        startFetch();
                    }
                )
                .setNegativeButton(
                    "キャンセル",
                    null
                )
                .show();
            setStatus(
                "対象レースを選んでください。",
                PRIMARY
            );
        } catch (JSONException exception) {
            finishWithError(
                "開催一覧JSONが不正です: "
                    + exception.getMessage()
            );
        }
    }

    private void pasteUrl() {
        ClipboardManager clipboard =
            (ClipboardManager) getSystemService(
                Context.CLIPBOARD_SERVICE
            );

        if (
            clipboard == null
            || !clipboard.hasPrimaryClip()
        ) {
            toast("クリップボードが空です。");
            return;
        }

        ClipData clip = clipboard.getPrimaryClip();
        if (clip == null || clip.getItemCount() == 0) {
            toast("クリップボードが空です。");
            return;
        }

        CharSequence value = clip.getItemAt(0)
            .coerceToText(this);
        urlInput.setText(
            value == null ? "" : value.toString().trim()
        );
    }

    private void startFetch() {
        String url = urlInput.getText()
            .toString()
            .trim();

        if (!RaceCardRules.isSupportedRaceCardUrl(url)) {
            setStatus(
                "WINTICKETの個別出走表URLではありません。"
                    + "開催一覧ではなく、対象レースの"
                    + "出走表ページを開いてURLをコピーしてください。",
                ERROR
            );
            return;
        }

        if (extractorScript.isBlank()) {
            setStatus(
                "抽出プログラムを読み込めませんでした。",
                ERROR
            );
            return;
        }

        requestedUrl = url;
        loadMode = LoadMode.RACE;
        getPreferences(MODE_PRIVATE)
            .edit()
            .putString("racecard_url", url)
            .apply();
        setBusy(true);
        clearResult();
        setStatus(
            "WINTICKETを読み込んでいます…",
            MUTED
        );
        webView.stopLoading();
        webView.loadUrl(url);
    }

    private void evaluateRaceCard() {
        setStatus(
            "選手表と並び予想を解析しています…",
            MUTED
        );
        webView.evaluateJavascript(
            extractorScript,
            this::handleJavascriptResult
        );
    }

    private void handleJavascriptResult(String rawValue) {
        try {
            JSONObject root = decodeJavascriptObject(
                rawValue
            );
            latestDiagnostics = root.toString(2);
            diagnosticsView.setText(latestDiagnostics);

            if (!root.optBoolean("ok", false)) {
                finishWithError(
                    root.optString(
                        "error",
                        "選手データを取得できませんでした。"
                    )
                );
                return;
            }

            JSONArray riders = root.optJSONArray(
                "riders"
            );
            if (riders == null) {
                finishWithError(
                    "選手配列がありません。"
                );
                return;
            }

            List<Integer> carNumbers =
                new ArrayList<>();
            for (int index = 0; index < riders.length(); index++) {
                carNumbers.add(
                    riders.getJSONObject(index)
                        .optInt("carNumber", 0)
                );
            }
            String validationError =
                RaceCardRules.validateCarNumbers(
                    carNumbers
                );
            if (!validationError.isBlank()) {
                finishWithError(
                    validationError
                        + " 推測で補完せず、検証ログへ保存しました。"
                );
                return;
            }

            renderRiders(riders);
            String pageTitle = root.optString(
                "pageTitle",
                "対象レース"
            );
            targetView.setText(
                "取得対象\n" + pageTitle
            );
            targetView.setVisibility(View.VISIBLE);
            renderLineup(root);
            latestRacePayload = root;
            updatePredictButton();
            setStatus(
                riders.length()
                    + "人の選手データを取得しました。"
                    + "氏名・車番・コメントを"
                    + "確認してから予測してください。",
                PRIMARY
            );
            loadMode = LoadMode.NONE;
            finishLoading();
        } catch (JSONException exception) {
            latestDiagnostics = String.valueOf(rawValue);
            diagnosticsView.setText(
                latestDiagnostics
            );
            finishWithError(
                "解析結果のJSONが不正です: "
                    + exception.getMessage()
            );
        }
    }

    private JSONObject decodeJavascriptObject(
        String rawValue
    ) throws JSONException {
        Object decoded = new JSONTokener(
            rawValue == null ? "null" : rawValue
        ).nextValue();
        String payload = decoded instanceof String
            ? (String) decoded
            : String.valueOf(decoded);
        return new JSONObject(payload);
    }

    private void renderRiders(
        JSONArray riders
    ) throws JSONException {
        riderContainer.removeAllViews();

        for (int index = 0; index < riders.length(); index++) {
            JSONObject rider = riders.getJSONObject(index);
            LinearLayout card = verticalLayout();
            card.setPadding(
                dp(14),
                dp(12),
                dp(14),
                dp(12)
            );
            card.setBackgroundColor(CARD_BACKGROUND);

            int carNumber = rider.optInt(
                "carNumber",
                0
            );
            String name = rider.optString(
                "name",
                ""
            );
            TextView riderTitle = text(
                carNumber + "番  " + name,
                18,
                Color.rgb(22, 28, 33)
            );
            riderTitle.setTypeface(
                riderTitle.getTypeface(),
                android.graphics.Typeface.BOLD
            );
            card.addView(riderTitle, matchWrap());

            String profile = rider.optString(
                "profile",
                ""
            );
            String score = displayNumber(
                rider,
                "score"
            );
            String detail = (
                (
                    profile.isBlank()
                        ? ""
                        : profile + "\n"
                )
                    + "競走得点 " + score
                    + "  脚質 "
                    + rider.optString("style", "―")
                    + "  S/H/B "
                    + displayNumber(rider, "s")
                    + "/"
                    + displayNumber(rider, "h")
                    + "/"
                    + displayNumber(rider, "b")
            );
            TextView detailView = text(
                detail,
                14,
                MUTED
            );
            LinearLayout.LayoutParams detailParams =
                matchWrap();
            detailParams.setMargins(
                0,
                dp(5),
                0,
                0
            );
            card.addView(
                detailView,
                detailParams
            );

            String comment = rider.optString(
                "comment",
                ""
            );
            TextView commentView = text(
                "コメント："
                    + (
                        comment.isBlank()
                            ? "（空欄）"
                            : comment
                    ),
                15,
                Color.rgb(35, 41, 46)
            );
            commentView.setPadding(
                0,
                dp(8),
                0,
                0
            );
            card.addView(commentView, matchWrap());

            LinearLayout.LayoutParams cardParams =
                matchWrap();
            cardParams.setMargins(
                0,
                0,
                0,
                dp(9)
            );
            riderContainer.addView(
                card,
                cardParams
            );
        }
    }

    private void renderLineup(JSONObject root) {
        String lineupText = root.optString(
            "lineupText",
            ""
        );
        JSONArray items = root.optJSONArray(
            "lineupItems"
        );
        int itemCount = items == null
            ? 0
            : items.length();
        String compact = lineupText
            .replace("\r", "")
            .replaceAll("\\n{3,}", "\n\n")
            .trim();

        if (compact.length() > 500) {
            compact = compact.substring(0, 500)
                + "…";
        }

        lineupView.setText(
            "並び予想の取得確認\n"
                + (
                    compact.isBlank()
                        ? "並び予想テキストを検出できませんでした。"
                        : compact
                )
                + "\n\n座標付き車番要素: "
                + itemCount
                + "件"
        );
        lineupView.setVisibility(View.VISIBLE);
    }

    private void updatePredictButton() {
        if (predictButton == null) {
            return;
        }

        predictButton.setEnabled(
            latestRacePayload != null
                && AiBundleImporter.isReady(this)
                && progressBar.getVisibility()
                    != View.VISIBLE
        );
    }

    private void startPrediction() {
        if (latestRacePayload == null) {
            setStatus(
                "先に対象レースの出走表を"
                    + "取得してください。",
                ERROR
            );
            return;
        }

        if (!AiBundleImporter.isReady(this)) {
            setStatus(
                "先にMacで作成した"
                    + "AIデータZIPを"
                    + "取り込んでください。",
                ERROR
            );
            return;
        }

        final String payload =
            latestRacePayload.toString();
        setBusy(true);
        predictionContainer.removeAllViews();
        setStatus(
            "端末内で特徴量とAI確率を"
                + "計算しています…",
            MUTED
        );
        worker.execute(() -> {
            try {
                Python python =
                    Python.getInstance();
                PyObject module = python.getModule(
                    "mobile_ai_bridge"
                );
                PyObject response = module.callAttr(
                    "predict_race",
                    payload,
                    AiBundleImporter
                        .getModelFile(this)
                        .getAbsolutePath(),
                    AiBundleImporter
                        .getDatabaseFile(this)
                        .getAbsolutePath()
                );
                JSONObject prediction =
                    new JSONObject(
                        response.toString()
                    );
                PredictionHistory.append(
                    this,
                    prediction
                );
                handler.post(() -> {
                    try {
                        renderPrediction(
                            prediction
                        );
                        setStatus(
                            "オッズ非依存AIの"
                                + "端末内予測が"
                                + "完了しました。",
                            PRIMARY
                        );
                        updateHistory();
                    } catch (
                        JSONException exception
                    ) {
                        setStatus(
                            "予測表示エラー: "
                                + exception
                                    .getMessage(),
                            ERROR
                        );
                    }

                    finishLoading();
                });
            } catch (Exception exception) {
                handler.post(() -> {
                    setStatus(
                        "端末内予測エラー: "
                            + exception.getMessage(),
                        ERROR
                    );
                    finishLoading();
                });
            }
        });
    }

    private void renderPrediction(
        JSONObject prediction
    ) throws JSONException {
        predictionContainer.removeAllViews();
        JSONObject target = prediction.getJSONObject(
            "target"
        );
        JSONArray combinations =
            prediction.getJSONArray(
                "combinations"
            );
        JSONArray riders = prediction.getJSONArray(
            "riders"
        );
        JSONArray lineupGroups =
            prediction.getJSONArray(
                "lineup_groups"
            );
        StringBuilder lineup =
            new StringBuilder();

        for (
            int index = 0;
            index < lineupGroups.length();
            index++
        ) {
            if (index > 0) {
                lineup.append(" / ");
            }

            JSONArray group =
                lineupGroups.getJSONArray(index);

            for (
                int position = 0;
                position < group.length();
                position++
            ) {
                if (position > 0) {
                    lineup.append("-");
                }

                lineup.append(
                    group.getInt(position)
                );
            }
        }

        predictionContainer.addView(
            predictionCard(
                "予測対象",
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
                    + "\n採用並び: "
                    + lineup
                    + "\n並び方式: "
                    + prediction.optString(
                        "lineup_source",
                        ""
                    )
                    + "（信頼度 "
                    + String.format(
                        Locale.JAPAN,
                        "%.2f",
                        prediction.optDouble(
                            "lineup_confidence",
                            0.0
                        )
                    )
                    + "）"
            ),
            matchWrap()
        );

        StringBuilder combinationText =
            new StringBuilder();
        int displayCount = Math.min(
            30,
            combinations.length()
        );

        for (
            int index = 0;
            index < displayCount;
            index++
        ) {
            JSONObject row =
                combinations.getJSONObject(index);
            combinationText.append(
                String.format(
                    Locale.JAPAN,
                    "%2d位  %s  %.3f%%",
                    row.optInt("rank", index + 1),
                    row.optString(
                        "combination",
                        ""
                    ),
                    row.optDouble(
                        "probability",
                        0.0
                    )
                        * 100.0
                )
            );

            if (index + 1 < displayCount) {
                combinationText.append("\n");
            }
        }

        predictionContainer.addView(
            predictionCard(
                "3連単AI確率 上位30",
                combinationText.toString()
            ),
            cardParams()
        );

        StringBuilder riderText =
            new StringBuilder();

        for (
            int index = 0;
            index < riders.length();
            index++
        ) {
            JSONObject rider =
                riders.getJSONObject(index);
            riderText.append(
                String.format(
                    Locale.JAPAN,
                    "%d番 %s\n"
                        + "  1着 %.1f%% / "
                        + "2着 %.1f%% / "
                        + "3着 %.1f%% / "
                        + "3着内 %.1f%%",
                    rider.optInt(
                        "car_number",
                        0
                    ),
                    rider.optString(
                        "name",
                        ""
                    ),
                    rider.optDouble(
                        "first_probability",
                        0.0
                    )
                        * 100.0,
                    rider.optDouble(
                        "second_probability",
                        0.0
                    )
                        * 100.0,
                    rider.optDouble(
                        "third_probability",
                        0.0
                    )
                        * 100.0,
                    rider.optDouble(
                        "top3_probability",
                        0.0
                    )
                        * 100.0
                )
            );

            if (index + 1 < riders.length()) {
                riderText.append("\n\n");
            }
        }

        predictionContainer.addView(
            predictionCard(
                "選手別着順確率",
                riderText.toString()
            ),
            cardParams()
        );

        JSONObject coverage =
            prediction.optJSONObject(
                "feature_coverage"
            );
        JSONObject model = prediction.optJSONObject(
            "model"
        );
        String detail = "学習終了日: "
            + (
                model == null
                    ? "不明"
                    : model.optString(
                        "training_end_date",
                        "不明"
                    )
            )
            + "\n特徴量数: "
            + (
                coverage == null
                    ? 0
                    : coverage.optInt(
                        "feature_count",
                        0
                    )
            )
            + "\n直近履歴あり: "
            + (
                coverage == null
                    ? 0
                    : coverage.optInt(
                        "recent_history_rider_count",
                        0
                    )
            )
            + "人 / "
            + (
                coverage == null
                    ? 0
                    : coverage.optInt(
                        "rider_count",
                        0
                    )
            )
            + "人";
        predictionContainer.addView(
            predictionCard(
                "モデル・特徴量確認",
                detail
            ),
            cardParams()
        );
    }

    private View predictionCard(
        String title,
        String detail
    ) {
        LinearLayout card = verticalLayout();
        card.setPadding(
            dp(14),
            dp(12),
            dp(14),
            dp(12)
        );
        card.setBackgroundColor(Color.WHITE);
        TextView titleView = label(title);
        card.addView(titleView, matchWrap());
        TextView detailView = text(
            detail,
            14,
            Color.rgb(36, 43, 49)
        );
        detailView.setTextIsSelectable(true);
        LinearLayout.LayoutParams detailParams =
            matchWrap();
        detailParams.setMargins(
            0,
            dp(7),
            0,
            0
        );
        card.addView(
            detailView,
            detailParams
        );
        return card;
    }

    private LinearLayout.LayoutParams cardParams() {
        LinearLayout.LayoutParams params =
            matchWrap();
        params.setMargins(
            0,
            dp(10),
            0,
            0
        );
        return params;
    }

    private void updateHistory() {
        try {
            historyView.setText(
                PredictionHistory.summary(this)
            );
        } catch (IOException exception) {
            historyView.setText(
                "予測履歴を確認できません: "
                    + exception.getMessage()
            );
        }
    }

    private void finishWithError(String message) {
        loadMode = LoadMode.NONE;
        setStatus(message, ERROR);
        finishLoading();
    }

    private void finishLoading() {
        setBusy(false);
    }

    private void setBusy(boolean busy) {
        fetchButton.setEnabled(!busy);
        selectRaceButton.setEnabled(!busy);
        importButton.setEnabled(!busy);
        progressBar.setVisibility(
            busy ? View.VISIBLE : View.GONE
        );

        if (busy) {
            predictButton.setEnabled(false);
        } else {
            updatePredictButton();
        }
    }

    private void clearResult() {
        riderContainer.removeAllViews();
        predictionContainer.removeAllViews();
        targetView.setVisibility(View.GONE);
        lineupView.setVisibility(View.GONE);
        latestRacePayload = null;
        updatePredictButton();
        latestDiagnostics = "";
        diagnosticsView.setText(
            "取得中です。"
        );
    }

    private void setStatus(
        String message,
        int color
    ) {
        statusView.setText(message);
        statusView.setTextColor(color);
    }

    private void copyDiagnostics() {
        if (latestDiagnostics.isBlank()) {
            toast("コピーする検証ログがありません。");
            return;
        }

        ClipboardManager clipboard =
            (ClipboardManager) getSystemService(
                Context.CLIPBOARD_SERVICE
            );
        if (clipboard == null) {
            toast("クリップボードを利用できません。");
            return;
        }
        clipboard.setPrimaryClip(
            ClipData.newPlainText(
                "競輪AI Fold5検証ログ",
                latestDiagnostics
            )
        );
        toast("検証ログをコピーしました。");
    }

    private String displayNumber(
        JSONObject source,
        String key
    ) {
        if (
            !source.has(key)
            || source.isNull(key)
        ) {
            return "―";
        }

        double value = source.optDouble(
            key,
            Double.NaN
        );
        if (Double.isNaN(value)) {
            return "―";
        }

        if (value == Math.rint(value)) {
            return String.format(
                Locale.JAPAN,
                "%.0f",
                value
            );
        }

        return String.format(
            Locale.JAPAN,
            "%.2f",
            value
        );
    }

    private String readAsset(String name) {
        try (
            BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                    getAssets().open(name),
                    StandardCharsets.UTF_8
                )
            )
        ) {
            StringBuilder output =
                new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                output.append(line).append('\n');
            }
            return output.toString();
        } catch (IOException exception) {
            return "";
        }
    }

    private LinearLayout verticalLayout() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        return layout;
    }

    private TextView label(String value) {
        TextView output = text(
            value,
            16,
            Color.rgb(31, 38, 44)
        );
        output.setTypeface(
            output.getTypeface(),
            android.graphics.Typeface.BOLD
        );
        return output;
    }

    private TextView text(
        String value,
        int size,
        int color
    ) {
        TextView output = new TextView(this);
        output.setText(value);
        output.setTextSize(size);
        output.setTextColor(color);
        output.setLineSpacing(0, 1.12f);
        return output;
    }

    private Button button(String value) {
        Button output = new Button(this);
        output.setText(value);
        output.setTextSize(14);
        output.setAllCaps(false);
        return output;
    }

    private TextView infoCard(String message) {
        TextView output = text(
            message,
            14,
            Color.rgb(46, 55, 62)
        );
        output.setPadding(
            dp(13),
            dp(12),
            dp(13),
            dp(12)
        );
        output.setBackgroundColor(
            Color.rgb(232, 243, 238)
        );
        return output;
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        );
    }

    private int dp(int value) {
        return Math.round(
            value
                * getResources()
                    .getDisplayMetrics()
                    .density
        );
    }

    private void toast(String message) {
        Toast.makeText(
            this,
            message,
            Toast.LENGTH_SHORT
        ).show();
    }

    @Override
    protected void onDestroy() {
        handler.removeCallbacksAndMessages(null);
        worker.shutdownNow();
        if (webView != null) {
            webView.stopLoading();
            webView.destroy();
        }
        super.onDestroy();
    }
}
