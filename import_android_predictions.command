#!/bin/bash

set -euo pipefail

SCRIPT_DIRECTORY="$(
    cd "$(dirname "$0")"
    pwd
)"
cd "$SCRIPT_DIRECTORY"

if [ ! -d ".venv" ]; then
    echo "仮想環境がありません。先にinstall.commandを実行してください。"
    read -r -p "Enterキーで閉じます。"
    exit 1
fi

source .venv/bin/activate

if ! python android_prediction_import.py; then
    echo
    echo "自動検出できない場合は、Streamlitのオッズ非依存AIページからDriveフォルダを指定してください。"
    read -r -p "Enterキーで閉じます。"
    exit 1
fi

echo
echo "スマホ予測の取込が完了しました。"
read -r -p "Enterキーで閉じます。"
