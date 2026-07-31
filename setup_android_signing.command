#!/bin/bash

set -euo pipefail

SCRIPT_DIRECTORY="$(
    cd "$(dirname "$0")"
    pwd
)"
cd "$SCRIPT_DIRECTORY"

python3 setup_android_signing.py
open .android-signing

echo
echo "固定署名ファイルを作成しました。"
echo "github-actions-secrets.txtの4項目をGitHub Actions Secretsへ登録してください。"
read -r -p "Enterキーで閉じます。"
