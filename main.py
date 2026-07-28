from datetime import date
import streamlit as st

from race_catalog import fetch_race_catalog

st.set_page_config(page_title="競輪 妙味期待値アプリ", layout="wide")
st.title("競輪3連単 妙味期待値アプリ")
st.caption("Ver.0.2：開催日・競輪場・レース番号の選択")

selected_date = st.date_input("開催日", value=date.today())

if "catalog" not in st.session_state:
    st.session_state.catalog = {}
if "catalog_logs" not in st.session_state:
    st.session_state.catalog_logs = []

if st.button("この日の開催一覧を取得", type="primary"):
    with st.spinner("WINTICKETから開催一覧を確認しています"):
        catalog, logs = fetch_race_catalog(selected_date)
    st.session_state.catalog = catalog
    st.session_state.catalog_logs = logs

catalog = st.session_state.catalog

if catalog:
    venues = list(catalog.keys())
    venue = st.selectbox("競輪場", venues)
    races = catalog[venue]

    race_labels = [f"{r['race_number']}R" for r in races]
    selected_label = st.selectbox("レース番号", race_labels)
    selected_race = races[race_labels.index(selected_label)]

    st.success(f"選択中：{selected_date:%Y年%m月%d日}・{venue}・{selected_label}")
    st.code(selected_race["url"], language=None)

    st.info(
        "この段階では対象レースURLの自動確定まで実装済みです。"
        "次の更新で、このURLから3連単オッズを取得します。"
    )
else:
    st.info("開催日を選び、「この日の開催一覧を取得」を押してください。")

with st.expander("取得ログ・自己診断"):
    if st.session_state.catalog_logs:
        st.text("\n".join(st.session_state.catalog_logs))
    else:
        st.write("まだ取得を実行していません。")
