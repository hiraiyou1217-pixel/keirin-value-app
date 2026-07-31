#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$HOME/Desktop"
APP_PATH="$DESKTOP_DIR/競輪AI.app"
SOURCE_PATH="$(mktemp "${TMPDIR:-/tmp}/keirin-ai-launcher.XXXXXX.applescript")"
ICON_WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/keirin-ai-icon.XXXXXX")"
TEMP_APP_PATH="$ICON_WORK_DIR/競輪AI.app"

cleanup() {
  rm -f "$SOURCE_PATH"
  rm -rf "$ICON_WORK_DIR"
}
trap cleanup EXIT

PROJECT_DIR_ESCAPED="${PROJECT_DIR//\\/\\\\}"
PROJECT_DIR_ESCAPED="${PROJECT_DIR_ESCAPED//\"/\\\"}"

cat > "$SOURCE_PATH" <<APPLESCRIPT
property projectDirectory : "$PROJECT_DIR_ESCAPED"

on run
    set pythonPath to projectDirectory & "/.venv/bin/python"
    set mainPath to projectDirectory & "/main.py"
    set logDirectory to projectDirectory & "/logs"
    set logPath to logDirectory & "/streamlit-desktop.log"

    try
        do shell script "test -x " & quoted form of pythonPath
    on error
        display dialog "先にリポジトリ内の install.command を実行してください。" buttons {"OK"} default button "OK" with icon stop
        return
    end try

    set launchCommand to "mkdir -p " & quoted form of logDirectory & "; " & ¬
        "if ! /usr/sbin/lsof -nP -iTCP:8501 -sTCP:LISTEN >/dev/null 2>&1; then " & ¬
        "cd " & quoted form of projectDirectory & " && " & ¬
        "nohup " & quoted form of pythonPath & " -m streamlit run " & quoted form of mainPath & ¬
        " --server.headless true --server.address 127.0.0.1 --server.port 8501" & ¬
        " > " & quoted form of logPath & " 2>&1 </dev/null & fi; " & ¬
        "for attempt in \$(seq 1 30); do " & ¬
        "if /usr/bin/curl -fsS http://127.0.0.1:8501/_stcore/health >/dev/null 2>&1; then exit 0; fi; " & ¬
        "/bin/sleep 1; done; exit 0"

    do shell script launchCommand
    open location "http://127.0.0.1:8501"
end run
APPLESCRIPT

mkdir -p "$DESKTOP_DIR"
/usr/bin/osacompile -o "$TEMP_APP_PATH" "$SOURCE_PATH"

ICON_SOURCE="$PROJECT_DIR/android-fold5/app/src/main/res/drawable-nodpi/ic_launcher_foreground.png"

if [ -f "$ICON_SOURCE" ]; then
  ICONSET="$ICON_WORK_DIR/KeirinAI.iconset"
  mkdir -p "$ICONSET"
  /usr/bin/sips -z 16 16 "$ICON_SOURCE" --out "$ICONSET/icon_16x16.png" >/dev/null
  /usr/bin/sips -z 32 32 "$ICON_SOURCE" --out "$ICONSET/icon_16x16@2x.png" >/dev/null
  /usr/bin/sips -z 32 32 "$ICON_SOURCE" --out "$ICONSET/icon_32x32.png" >/dev/null
  /usr/bin/sips -z 64 64 "$ICON_SOURCE" --out "$ICONSET/icon_32x32@2x.png" >/dev/null
  /usr/bin/sips -z 128 128 "$ICON_SOURCE" --out "$ICONSET/icon_128x128.png" >/dev/null
  /usr/bin/sips -z 256 256 "$ICON_SOURCE" --out "$ICONSET/icon_128x128@2x.png" >/dev/null
  /usr/bin/sips -z 256 256 "$ICON_SOURCE" --out "$ICONSET/icon_256x256.png" >/dev/null
  /usr/bin/sips -z 512 512 "$ICON_SOURCE" --out "$ICONSET/icon_256x256@2x.png" >/dev/null
  /usr/bin/sips -z 512 512 "$ICON_SOURCE" --out "$ICONSET/icon_512x512.png" >/dev/null
  /usr/bin/sips -z 1024 1024 "$ICON_SOURCE" --out "$ICONSET/icon_512x512@2x.png" >/dev/null
  /usr/bin/iconutil -c icns "$ICONSET" -o "$ICON_WORK_DIR/applet.icns"
  cp "$ICON_WORK_DIR/applet.icns" "$TEMP_APP_PATH/Contents/Resources/applet.icns"
  /usr/bin/touch "$TEMP_APP_PATH"
fi

rm -rf "$APP_PATH"
mv "$TEMP_APP_PATH" "$APP_PATH"

echo ""
echo "デスクトップへ「競輪AI.app」を作成しました。"
echo "今後はこのアイコンをダブルクリックするだけで起動できます。"
