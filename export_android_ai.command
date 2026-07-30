#!/bin/bash

set -euo pipefail

SCRIPT_DIRECTORY="$(
    cd "$(dirname "$0")"
    pwd
)"
cd "$SCRIPT_DIRECTORY"

if [ -x ".venv/bin/python" ]; then
    PYTHON_COMMAND=".venv/bin/python"
else
    PYTHON_COMMAND="python3"
fi

"$PYTHON_COMMAND" export_android_ai_bundle.py

echo
echo "Galaxy用AIデータZIPを作成しました。"
echo "$SCRIPT_DIRECTORY/exports/keirin_android_ai_bundle.zip"

if command -v open >/dev/null 2>&1; then
    open "$SCRIPT_DIRECTORY/exports"
fi
