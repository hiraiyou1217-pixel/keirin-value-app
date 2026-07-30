# Galaxy Z Fold5 端末内オッズ非依存AI

Android 14のGalaxy Z Fold5本体でWINTICKETの出走表を取得し、
Macで学習したオッズ非依存AIを端末内で実行するアプリです。
期待値計算、3連単オッズ取得、Streamlitは含みません。

## できること

- アプリ内の日付選択から当日の全開催・全レースを表示
- 個別出走表から選手、プロフィール、競走得点、脚質、S/H/B、
  勝率、2連対率、3連対率、コメント、並びを取得
- Mac版と同じ特徴量生成コードと学習SQLiteを利用
- オッズを使わず3連単全組番と選手別1〜3着確率を端末内計算
- 3連単AI確率の上位30、選手別着順確率、特徴量充足を表示
- 全組番の予測確率を端末内履歴へ自動保存
- 不足車番や未対応競輪場を推測補完せずエラーにする

## AIデータZIPをMacで作る

学習済みモデルとSQLiteは公開GitHubやAPKへ入れません。Macで次を実行します。

```bash
cd ~/Documents/GitHub/keirin-value-app
source .venv/bin/activate
python export_android_ai_bundle.py
```

またはFinderから `export_android_ai.command` をダブルクリックします。

出力ファイル:

```text
exports/keirin_android_ai_bundle.zip
```

作成時に次を自動確認します。

- scikit-learnモデルがオッズ非依存の二値モデルである
- 端末用決定木JSONとMac版 `predict_proba` の確率が一致する
- SQLiteの `PRAGMA integrity_check` が `ok`
- `races` と `riders` テーブルが存在する
- ZIP内のモデル・SQLiteのサイズとSHA-256をmanifestへ保存する

ZIPは学習データを含むため公開リポジトリへPushしないでください。
Google Driveへ置く場合も本人だけが見られる設定にします。

## GitHub ActionsでAPKを作る

1. 変更をGitHubへPushします。
2. GitHubのリポジトリで `Actions` を開きます。
3. `Android Fold5 APK` を開きます。
4. 緑のチェックになった実行を開きます。
5. `Artifacts` の `keirin-ai-fold5-debug` をダウンロードします。
6. ZIPを展開し、`app-debug.apk` をGalaxyへ送ります。

APKはarm64-v8a専用で、Galaxy Z Fold5 / Android 14を対象にしています。
Python 3.12、NumPy、PandasをAPK内に持つため、旧取得検証版より
ファイルサイズと初回起動時間が増えます。

## GalaxyへAPKを更新インストール

1. Galaxyで `app-debug.apk` をタップします。
2. 「更新」または「インストール」を押します。
3. Androidから確認された場合だけ、ファイルを開いたアプリに
   「不明なアプリをインストール」を一時的に許可します。
4. インストール後はその許可を元に戻します。

同じアプリID・デバッグ署名のまま更新するため、通常は取得検証版を
アンインストールする必要はありません。

## GalaxyへAIデータを取り込む

1. `keirin_android_ai_bundle.zip` をGoogle Driveの非公開領域へ置くか、
   USBなどでGalaxyへコピーします。
2. アプリを開き、「AIデータZIPを取り込む」を押します。
3. Androidのファイル選択画面でZIPを選びます。
4. 「AIデータ取込済み」、学習日時、DBレース数、最終収集日を確認します。

取込中はZIPを一時領域で展開し、許可ファイル名、サイズ、SHA-256、
モデル形式、SQLite整合性をすべて確認します。検証が終わるまで
現在のAIデータは置き換えません。

## 予測操作

1. 「日付からレースを選ぶ」を押します。
2. 日付を選び、表示された競輪場・R番号を押します。
3. 選手数、氏名、車番、競走得点、コメントを確認します。
4. 「オッズ非依存AIで予測」を押します。
5. 3連単上位30と選手別の1着・2着・3着・3着内確率を確認します。

開催一覧を取得できない場合は、個別出走表URLを貼り付けて
「出走表を取得」する方法も残しています。

## AIデータ更新

Macで過去データを追加してモデルを再学習したら、もう一度
`export_android_ai_bundle.py` を実行します。同名ZIPをGalaxyへ送り、
アプリの「AIデータZIPを取り込む」で再取込します。検証済みZIPだけが
安全に置き換えられ、端末内の予測履歴は残ります。

## ローカルビルド

Android SDK、Java 17、Gradle 8.11.1、Python 3.12がある環境では、
共有Pythonソースを準備してからビルドします。

```bash
python android-fold5/tools/prepare_python_sources.py
gradle -p android-fold5 :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```
