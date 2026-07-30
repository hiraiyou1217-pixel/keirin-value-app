# Galaxy Z Fold5 出走表取得検証版

既存のmacOS版を変更せず、Android 14のGalaxy Z Fold5本体で
WINTICKETの個別出走表ページを読み込めるか確認するための検証アプリです。

## この版で確認すること

- WINTICKETの個別出走表URLをAndroid WebViewで開ける
- 出走表のtableから5〜9人の選手を重複なく取得できる
- 車番、選手名、プロフィール、競走得点、脚質、S/H/B、各率、
  コメントを表示できる
- 「並び予想」付近のテキストと座標付き車番要素を取得できる
- 不足・重複時に車番を推測補完せず、エラーと検証ログを残す

この版にはAI予測をまだ入れていません。Android WebViewからの取得が
実機で安定することを確認した後、既存の学習済みモデルとSQLiteを
端末用へ移植します。

## GitHub ActionsでAPKを作る

`.github/workflows/android-fold5.yml` が、Android SDKを用意して
単体テスト、Lint、APK作成を行います。

1. 変更をGitHubへPushします。
2. GitHubのリポジトリで `Actions` を開きます。
3. `Android Fold5 APK` を開きます。
4. 成功した実行の `Artifacts` から
   `keirin-ai-fold5-debug` をダウンロードします。
5. ZIPを展開して `app-debug.apk` をGalaxy Z Fold5へ送ります。

## Galaxy Z Fold5へのインストール

1. `app-debug.apk` をタップします。
2. Androidから確認された場合だけ、そのファイルを開いたアプリに
   「不明なアプリをインストール」を一時的に許可します。
3. インストール完了後、許可を元に戻します。

このAPKはGoogle Play公開版ではないデバッグ署名版です。

## 実機確認

1. ChromeでWINTICKETの対象レースの個別出走表を開きます。
2. Chromeの共有メニューから「リンクをコピー」します。
3. `競輪AI Fold5検証` を開きます。
4. 「貼り付け」→「出走表を取得」を押します。
5. 選手数、氏名、車番、競走得点、コメントをWINTICKETと照合します。
6. 正しくない場合は「検証ログをコピー」して報告します。

開催日別の一覧URLではなく、次の形の個別レースURLが必要です。

```text
https://www.winticket.jp/keirin/競輪場slug/racecard/開催ID/日目/R番号
```

## ローカルビルド

Android SDK、Java 17、Gradle 8.11.1がある環境では次のコマンドでも
ビルドできます。

```bash
gradle -p android-fold5 :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```
