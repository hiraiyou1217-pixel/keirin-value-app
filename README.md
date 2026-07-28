# keirin-value-app

## Ver.0.3.1

オッズ取得時にPlaywrightまたはChromiumがクラッシュすると、以前はStreamlit本体まで
終了する可能性がありました。

Ver.0.3.1では、オッズ取得を別Pythonプロセスで実行します。

- Chromiumが落ちてもアプリ画面は継続
- Workerの終了コードを表示
- 標準エラーを自己診断欄へ表示
- 120秒でタイムアウト
- ページ再描画のたびにselect要素を取得し直す

## 更新ファイル

- main.py
- odds_scraper.py
- odds_worker.py
- README.md
