#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "=== 競輪アプリ セットアップ／更新 ==="

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python3が見つかりません。"
  echo "Python 3.11以上をインストールしてください。"
  read -p "Enterキーで終了します"
  exit 1
fi

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium

echo ""
echo "更新が完了しました。次に run.command を開いてください。"
read -p "Enterキーで終了します"
