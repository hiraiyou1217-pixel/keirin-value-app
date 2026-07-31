#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "=== 競輪アプリ セットアップ／更新 ==="

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python3が見つかりません。"
  echo "Python 3.12または3.13をインストールしてください。"
  read -p "Enterキーで終了します"
  exit 1
fi

PYTHON_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"

if [ "$PYTHON_VERSION" != "3.12" ] && [ "$PYTHON_VERSION" != "3.13" ]; then
  echo "現在のPythonは $PYTHON_VERSION です。"
  echo "Python 3.12または3.13を使用してください。"
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

if ./install_desktop_launcher.command; then
  echo "デスクトップ起動アイコンも更新しました。"
else
  echo "デスクトップ起動アイコンだけ作成できませんでした。"
  echo "後で install_desktop_launcher.command を実行してください。"
fi

echo ""
echo "更新が完了しました。"
echo "次回からデスクトップの「競輪AI.app」を開いてください。"
read -p "Enterキーで終了します"
