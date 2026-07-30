package jp.hirai.keirinai;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
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

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import org.json.JSONTokener;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class MainActivity extends Activity {
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
    private EditText urlInput;
    private Button fetchButton;
    private ProgressBar progressBar;
    private TextView statusView;
    private TextView targetView;
    private TextView lineupView;
    private TextView diagnosticsView;
    private LinearLayout riderContainer;
    private WebView webView;
    private String extractorScript = "";
    private String requestedUrl = "";
    private String latestDiagnostics = "";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        extractorScript = readAsset(
            "extract_racecard.js"
        );
        setContentView(buildScreen());
        configureWebView();

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
            "Galaxy Z Fold5 取得検証版 0.1",
            13,
            MUTED
        );
        LinearLayout.LayoutParams versionParams = matchWrap();
        versionParams.setMargins(0, dp(2), 0, dp(18));
        root.addView(version, versionParams);

        root.addView(
            infoCard(
                "この版では、WINTICKETの出走表URLから"
                    + "選手・コメント・並び候補をスマホ本体で"
                    + "読み取れるか確認します。"
                    + "仮のAI予測や推測値は表示しません。"
            ),
            matchWrap()
        );

        TextView inputLabel = label(
            "WINTICKET 出走表URL"
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

                    setStatus(
                        "ページを読み込みました。"
                            + "出走表の描画を待っています…",
                        MUTED
                    );
                    handler.postDelayed(
                        MainActivity.this
                            ::evaluateRaceCard,
                        4500
                    );
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
        getPreferences(MODE_PRIVATE)
            .edit()
            .putString("racecard_url", url)
            .apply();
        fetchButton.setEnabled(false);
        progressBar.setVisibility(View.VISIBLE);
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
            Object decoded = new JSONTokener(
                rawValue == null ? "null" : rawValue
            ).nextValue();
            String payload = decoded instanceof String
                ? (String) decoded
                : String.valueOf(decoded);
            JSONObject root = new JSONObject(payload);
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
            setStatus(
                riders.length()
                    + "人の選手データを取得しました。"
                    + "氏名・車番・コメントを確認してください。",
                PRIMARY
            );
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

    private void finishWithError(String message) {
        setStatus(message, ERROR);
        finishLoading();
    }

    private void finishLoading() {
        fetchButton.setEnabled(true);
        progressBar.setVisibility(View.GONE);
    }

    private void clearResult() {
        riderContainer.removeAllViews();
        targetView.setVisibility(View.GONE);
        lineupView.setVisibility(View.GONE);
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
        if (webView != null) {
            webView.stopLoading();
            webView.destroy();
        }
        super.onDestroy();
    }
}
