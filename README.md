# keirin-value-app

## Ver.0.3.2

オッズ取得時のPython強制終了を回避するため、
オッズ取得処理からChromiumを完全に外しました。

### 変更点

- オッズ取得はHTTP通信のみ
- HTML内の埋め込みJSONを解析
- JSONで取れない場合はHTMLテキストを解析
- エラー時もStreamlitは終了しない
- 人気順位がない場合はオッズ順で補完

開催一覧取得には、既存のrace_catalog.pyを使用します。
