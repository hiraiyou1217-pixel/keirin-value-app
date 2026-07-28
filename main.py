from datetime import date
import pandas as pd
import streamlit as st

from race_catalog import fetch_race_catalog
from odds_scraper import fetch_trifecta_odds

st.set_page_config(page_title="競輪 妙味期待値アプリ", layout="wide")
st.title("競輪3連単 妙味期待値アプリ")
st.caption("Ver.0.3：レース選択・3連単オッズ自動取得")

selected_date = st.date_input("開催日", value=date.today())

for key, default in {
    "catalog": {},
    "catalog_logs": [],
    "odds": [],
    "odds_logs": [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

if st.button("この日の開催一覧を取得", type="primary"):
    with st.spinner("WINTICKETから開催一覧を確認しています"):
        catalog, logs = fetch_race_catalog(selected_date)
    st.session_state.catalog = catalog
    st.session_state.catalog_logs = logs
    st.session_state.odds = []
    st.session_state.odds_logs = []

catalog = st.session_state.catalog

if catalog:
    venues = list(catalog.keys())
    venue = st.selectbox("競輪場", venues)
    races = catalog[venue]

    race_labels = [f"{race['race_number']}R" for race in races]
    selected_label = st.selectbox("レース番号", race_labels)
    selected_race = races[race_labels.index(selected_label)]

    st.success(
        f"選択中：{selected_date:%Y年%m月%d日}・{venue}・{selected_label}"
    )

    col1, col2 = st.columns([1, 2])
    with col1:
        show_browser = st.checkbox("取得ブラウザを表示する", value=False)
    with col2:
        st.code(selected_race["url"], language=None)

    if st.button("3連単オッズを取得", type="primary"):
        with st.spinner("WINTICKETから3連単オッズを取得しています"):
            odds, logs = fetch_trifecta_odds(
                selected_race["url"],
                headless=not show_browser,
            )
        st.session_state.odds = odds
        st.session_state.odds_logs = logs

    if st.session_state.odds:
        df = pd.DataFrame(st.session_state.odds)
        st.success(f"3連単オッズを{len(df)}件取得しました。")
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "組番": st.column_config.TextColumn("組番"),
                "オッズ": st.column_config.NumberColumn("オッズ", format="%.1f"),
                "人気": st.column_config.NumberColumn("人気", format="%d"),
            },
        )
        csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "CSVをダウンロード",
            csv_bytes,
            file_name=f"{selected_date:%Y%m%d}_{venue}_{selected_label}_trifecta_odds.csv",
            mime="text/csv",
        )
    else:
        st.info("競輪場とレース番号を選び、「3連単オッズを取得」を押してください。")
else:
    st.info("開催日を選び、「この日の開催一覧を取得」を押してください。")

with st.expander("取得ログ・自己診断"):
    logs = st.session_state.catalog_logs + st.session_state.odds_logs
    if logs:
        st.text("\n".join(logs))
    else:
        st.write("まだ取得を実行していません。")
