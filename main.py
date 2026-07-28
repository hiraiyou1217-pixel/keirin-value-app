from __future__ import annotations

import csv
from datetime import date
from html import escape
from io import StringIO

import streamlit as st

from odds_http import fetch_trifecta_odds_http
from race_catalog import fetch_race_catalog


st.set_page_config(
    page_title="競輪 妙味期待値アプリ",
    layout="wide",
)

st.title("競輪3連単 妙味期待値アプリ")
st.caption("Ver.0.3.3：pandasを使わない安定版")


def make_csv(rows: list[dict]) -> bytes:
    buffer = StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=["組番", "オッズ", "人気"],
    )
    writer.writeheader()

    for row in rows:
        writer.writerow(
            {
                "組番": row.get("組番", ""),
                "オッズ": row.get("オッズ", ""),
                "人気": row.get("人気", ""),
            }
        )

    return buffer.getvalue().encode("utf-8-sig")


def render_odds_table(rows: list[dict]) -> None:
    table_rows = []

    for row in rows:
        combo = escape(str(row.get("組番", "")))
        odds = escape(str(row.get("オッズ", "")))
        rank = escape(str(row.get("人気", "")))

        table_rows.append(
            f"""
            <tr>
                <td>{rank}</td>
                <td>{combo}</td>
                <td>{odds}</td>
            </tr>
            """
        )

    html = f"""
    <div style="max-height:600px;overflow:auto;border:1px solid #ddd;">
        <table style="width:100%;border-collapse:collapse;">
            <thead>
                <tr style="position:sticky;top:0;background:#f5f5f5;">
                    <th style="padding:8px;border-bottom:1px solid #ddd;">人気</th>
                    <th style="padding:8px;border-bottom:1px solid #ddd;">組番</th>
                    <th style="padding:8px;border-bottom:1px solid #ddd;">オッズ</th>
                </tr>
            </thead>
            <tbody>
                {''.join(table_rows)}
            </tbody>
        </table>
    </div>
    """

    st.markdown(html, unsafe_allow_html=True)


selected_date = st.date_input(
    "開催日",
    value=date.today(),
)

defaults = {
    "catalog": {},
    "catalog_logs": [],
    "odds": [],
    "odds_logs": [],
}

for key, default in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = default


if st.button(
    "この日の開催一覧を取得",
    type="primary",
):
    try:
        with st.spinner(
            "WINTICKETから開催一覧を確認しています"
        ):
            catalog, logs = fetch_race_catalog(selected_date)

        st.session_state.catalog = catalog
        st.session_state.catalog_logs = logs
        st.session_state.odds = []
        st.session_state.odds_logs = []

    except Exception as exc:
        st.session_state.catalog = {}
        st.session_state.catalog_logs = [
            f"開催一覧取得エラー: {type(exc).__name__}: {exc}"
        ]


catalog = st.session_state.catalog

if catalog:
    venue = st.selectbox(
        "競輪場",
        list(catalog.keys()),
    )

    races = catalog[venue]

    race_labels = [
        f"{race['race_number']}R"
        for race in races
    ]

    selected_label = st.selectbox(
        "レース番号",
        race_labels,
    )

    selected_race = races[
        race_labels.index(selected_label)
    ]

    st.success(
        f"選択中：{selected_date:%Y年%m月%d日}"
        f"・{venue}・{selected_label}"
    )

    st.code(
        selected_race["url"],
        language=None,
    )

    if st.button(
        "3連単オッズを取得",
        type="primary",
    ):
        try:
            with st.spinner(
                "ブラウザを起動せず、オッズを取得しています"
            ):
                odds, logs = fetch_trifecta_odds_http(
                    selected_race["url"]
                )

            # Streamlitへ渡す前に標準型へ統一
            safe_rows = []

            for row in odds:
                safe_rows.append(
                    {
                        "組番": str(row.get("組番", "")),
                        "オッズ": float(row.get("オッズ", 0)),
                        "人気": int(row.get("人気", 9999)),
                    }
                )

            st.session_state.odds = safe_rows
            st.session_state.odds_logs = logs

        except Exception as exc:
            st.session_state.odds = []
            st.session_state.odds_logs = [
                f"オッズ取得エラー: {type(exc).__name__}: {exc}"
            ]

    odds = st.session_state.odds

    if odds:
        st.success(
            f"3連単オッズを{len(odds)}件取得しました。"
        )

        render_odds_table(odds)

        st.download_button(
            "CSVをダウンロード",
            data=make_csv(odds),
            file_name=(
                f"{selected_date:%Y%m%d}_"
                f"{venue}_{selected_label}_"
                "trifecta_odds.csv"
            ),
            mime="text/csv",
        )

    elif st.session_state.odds_logs:
        st.warning(
            "取得処理は終了しましたが、"
            "有効なオッズを検出できませんでした。"
        )

    else:
        st.info(
            "競輪場とレース番号を選び、"
            "「3連単オッズを取得」を押してください。"
        )

else:
    st.info(
        "開催日を選び、"
        "「この日の開催一覧を取得」を押してください。"
    )


with st.expander("取得ログ・自己診断"):
    logs = (
        st.session_state.catalog_logs
        + st.session_state.odds_logs
    )

    st.code(
        "\n".join(logs)
        if logs
        else "まだ取得を実行していません。",
        language=None,
    )
