#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo ".venvがありません。先に install.command を実行してください。"
  read -p "Enterキーで終了します"
  exit 1
fi

source .venv/bin/activate
python -m streamlit run main.py
