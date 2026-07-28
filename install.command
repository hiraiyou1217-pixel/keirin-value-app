#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "=== 競輪アプリ 初回セットアップ ==="

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python3が見つかりません。"
  echo "https://www.python.org/downloads/macos/ からPython 3.11以上をインストールしてください。"
  read -p "Enterキーで終了します"
  exit 1
fi

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium

echo ""
echo "セットアップが完了しました。"
echo "次に run.command を開いてください。"
read -p "Enterキーで終了します"
