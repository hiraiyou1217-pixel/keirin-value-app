# keirin-value-app

## Ver.0.3

選択したレースの出走表URLから、対応するWINTICKETオッズURLを自動生成し、
3連単の人気順オッズを取得します。

### 新機能

- 出走表URLからオッズURLを自動生成
- 3連単・人気順を自動選択
- 50件単位の表示範囲を順番に取得
- 取得結果を表で表示
- CSVダウンロード
- 取得ログと自己診断

### 更新方法

1. ZIP内のファイルをリポジトリ直下へ上書き
2. 起動中なら `Control + C` で停止
3. `run.command`を再実行
4. GitHub DesktopでCommit
5. Push origin

追加ライブラリはないため、通常はinstall.commandの再実行は不要です。
