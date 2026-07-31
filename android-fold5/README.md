# Galaxy Z Fold5 端末内オッズ非依存AI

Android 14のGalaxy Z Fold5本体でWINTICKETの出走表を取得し、
Macで学習したオッズ非依存AIを端末内で実行するアプリです。
期待値計算、3連単オッズ取得、Streamlitは含みません。

## できること

- 日付→開催場→レースNo.の順に絞り込んで対象レースを選択
- 個別出走表から選手、プロフィール、競走得点、脚質、S/H/B、
  勝率、2連対率、3連対率、コメント、並びを取得
- Mac版と同じ特徴量生成コードと学習SQLiteを利用
- オッズを使わず3連単全組番と選手別1〜3着確率を端末内計算
- 3連単AI確率の上位30、選手別着順確率、特徴量充足を表示
- 全組番の予測確率を端末内履歴へ自動保存
- 予測JSONを本人のGoogle Driveフォルダへ自動同期
- Drive送信済み履歴は端末に3日間だけ保持
- 未送信履歴は3日を過ぎても削除せず次回再送
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

## 初回だけ固定署名を設定する

GitHub Actionsの実行環境が変わってもAPKを上書き更新できるよう、
本人専用の固定署名鍵を使用します。これは初回だけ行います。

```bash
cd ~/Documents/GitHub/keirin-value-app
python3 setup_android_signing.py
open .android-signing
```

`.android-signing/github-actions-secrets.txt` に表示された次の4項目を、
GitHubのリポジトリで `Settings` → `Secrets and variables` →
`Actions` → `New repository secret` から登録します。

- `ANDROID_SIGNING_KEYSTORE_BASE64`
- `ANDROID_SIGNING_STORE_PASSWORD`
- `ANDROID_SIGNING_KEY_ALIAS`
- `ANDROID_SIGNING_KEY_PASSWORD`

`.android-signing/keirin-ai-release.p12` と
`github-actions-secrets.txt` はGitHubへPushせず、外付け媒体などにも
安全なバックアップを作ってください。同じ鍵を失うと、既存アプリを
アンインストールせずに更新できなくなります。

## GitHub ActionsでAPKを作る

1. 変更をGitHubへPushします。
2. GitHubのリポジトリで `Actions` を開きます。
3. `Android Fold5 APK` を開きます。
4. 緑のチェックになった実行を開きます。
5. `Artifacts` の `keirin-ai-fold5-release` をダウンロードします。
6. ZIPを展開し、`app-release.apk` をGalaxyへ送ります。

APKはarm64-v8a専用で、Galaxy Z Fold5 / Android 14を対象にしています。
Python 3.12、NumPy、PandasをAPK内に持つため、旧取得検証版より
ファイルサイズと初回起動時間が増えます。

## GalaxyへAPKを更新インストール

1. Galaxyで `app-release.apk` をタップします。
2. 「更新」または「インストール」を押します。
3. Androidから確認された場合だけ、ファイルを開いたアプリに
   「不明なアプリをインストール」を一時的に許可します。
4. インストール後はその許可を元に戻します。

初めて固定署名版へ移行するときだけ、現在のデバッグ版と署名が異なるため
旧アプリのアンインストールが必要です。AIデータZIPをアプリ外へ保管して
から実行してください。固定署名版の導入後は、同じ署名鍵を使う限り
アンインストールせず上書き更新できます。

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

1. 「日付 → 開催場 → レースNo.を選ぶ」を押します。
2. 日付を選びます。
3. その日に開催される競輪場から1場を選びます。
4. 選択した開催場のレースNo.を選びます。
5. 選手数、氏名、車番、競走得点、コメントを確認します。
6. 「オッズ非依存AIで予測」を押します。
7. 3連単上位30と選手別の1着・2着・3着・3着内確率を確認します。

選択中の「日付 → 開催場 → R」は画面に表示されます。レースNo.の
選択画面から開催場へ、開催場の選択画面から日付へ戻って選び直せます。
従来の個別出走表URL貼り付けも引き続き使用できます。

開催一覧を取得できない場合は、個別出走表URLを貼り付けて
「出走表を取得」する方法も残しています。

## Google Driveへ予測を同期

Google CloudのAPIキーや開発者用OAuth設定は不要です。Galaxyに
Google Driveアプリをインストールし、予測を保存する本人のGoogle
アカウントへログインしてください。

1. Google Driveに本人だけがアクセスできる `KeirinAI` フォルダを作ります。
2. Androidアプリの「Google Drive保存先を選ぶ・変更」を押します。
3. システムのフォルダ選択画面で、Google Driveの `KeirinAI` を選びます。
4. 「このフォルダを使用」→「許可」を押します。
5. 以後は予測完了時にJSONを自動送信します。

必要な許可は選択した `KeirinAI` フォルダの読み書きだけです。他のDrive
フォルダ、メール、連絡先への許可は要求しません。通信に失敗した場合は
アプリ起動時または「未送信の予測を今すぐ同期」で再送します。

送信済み予測は端末に72時間保持した後、自動削除します。未送信の予測は
72時間を過ぎても削除しません。Drive上のJSONはMacで取り込むまで
削除しないでください。

## Macへスマホ予測を取り込む

Google Drive for desktopは不要です。Streamlitの「オッズ非依存AI」→
「AI予測の客観評価」→「Galaxyの予測をGoogle Driveから取り込む」→
「Driveへ直接接続（推奨）」を開きます。

初回だけ次のGoogle側設定が必要です。

1. Google Cloudで新しいプロジェクトを作ります。
2. Google Drive APIを有効にします。
3. Google Auth Platformでアプリ名と連絡先メールを設定します。
4. 個人のGoogleアカウントでは対象を「外部」にし、テストユーザーへ
   Galaxyで使用中のGoogleアカウントを追加します。
5. OAuthクライアントを「デスクトップアプリ」として作成し、
   JSONをダウンロードします。
6. 画面でJSONを選び「OAuth設定をMacへ保存」を押します。
7. 「Googleアカウントへ接続」を押し、Driveの閲覧を許可します。

接続後は「Driveから予測を取り込む」を押します。`KeirinAI`フォルダが
1個なら空欄で自動検出します。複数ある場合だけ、ブラウザ版Driveで対象
フォルダを開いたURLを貼り付けます。Drive APIの権限は読み取り専用で、
アプリは `KeirinAI` 内の `keirin_prediction_*.json` だけを取得します。

OAuthクライアントJSONと認証トークンはMacの
`data/google_drive/` にだけ保存され、GitHubには追加されません。
接続を解除すると認証トークンをMacから削除します。

従来どおり手動ダウンロードしたフォルダも「Mac内フォルダ」タブから
取り込めます。

開催日・競輪場・R番号・出走車番・3連単全組番・全順位・確率合計を
検証し、完全な予測だけをSQLiteへ保存します。再実行時は同じレース・
同じモデルの予測を重複登録しません。結果が既に登録済みなら直ちに照合し、
未登録なら結果収集後に既存の自己評価へ反映します。

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
