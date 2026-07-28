from datetime import date

import pandas as pd
import streamlit as st

from odds_http import fetch_trifecta_odds_http
from race_catalog import fetch_race_catalog


st.set_page_config(
    page_title="競輪 妙味期待値アプリ",
    layout="wide",
)

st.title("競輪3連単 妙味期待値アプリ")
st.caption(
    "Ver.0.3.2：Chromiumを使わないオッズ取得"
)

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
    with st.spinner(
        "WINTICKETから開催一覧を確認しています"
    ):
        catalog, logs = fetch_race_catalog(selected_date)

    st.session_state.catalog = catalog
    st.session_state.catalog_logs = logs
    st.session_state.odds = []
    st.session_state.odds_logs = []


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
        with st.spinner(
            "ブラウザを起動せず、"
            "オッズデータを取得しています"
        ):
            odds, logs = fetch_trifecta_odds_http(
                selected_race["url"]
            )

        st.session_state.odds = odds
        st.session_state.odds_logs = logs

    if st.session_state.odds:
        dataframe = pd.DataFrame(
            st.session_state.odds
        )

        st.success(
            f"3連単オッズを"
            f"{len(dataframe)}件取得しました。"
        )

        st.dataframe(
            dataframe,
            use_container_width=True,
            hide_index=True,
            column_config={
                "組番": st.column_config.TextColumn(
                    "組番"
                ),
                "オッズ": st.column_config.NumberColumn(
                    "オッズ",
                    format="%.1f",
                ),
                "人気": st.column_config.NumberColumn(
                    "人気",
                    format="%d",
                ),
            },
        )

        st.download_button(
            "CSVをダウンロード",
            dataframe.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name=(
                f"{selected_date:%Y%m%d}_"
                f"{venue}_{selected_label}_"
                "trifecta_odds.csv"
            ),
            mime="text/csv",
        )

    elif st.session_state.odds_logs:
        st.error(
            "オッズを検出できませんでした。"
            "Pythonは終了していません。"
            "下の取得ログを確認してください。"
        )

    else:
        st.info(
            "競輪場とレース番号を選び、"
            "「3連単オッズを取得」を"
            "押してください。"
        )

else:
    st.info(
        "開催日を選び、"
        "「この日の開催一覧を取得」を"
        "押してください。"
    )


with st.expander("取得ログ・自己診断"):
    logs = (
        st.session_state.catalog_logs
        + st.session_state.odds_logs
    )

    st.text(
        "\n".join(logs)
        if logs
        else "まだ取得を実行していません。"
    )
