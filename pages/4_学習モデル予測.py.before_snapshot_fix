from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from learned_model_prediction import (
    predict_current_race,
)
from train_learning_model import MODEL_PATH


st.set_page_config(
    page_title="学習モデル予測",
    page_icon="🤖",
    layout="wide",
)

st.title("🤖 学習モデル予測")

st.caption(
    "過去レースで学習したモデルを使い、"
    "現在取得中のレース全組番を予測します。"
)

if not MODEL_PATH.exists():
    st.error(
        "学習済みモデルがありません。"
        "先に「モデル学習」ページで"
        "基準モデルを作成してください。"
    )
    st.stop()

odds_rows: list[dict[str, Any]] = (
    st.session_state.get("odds", [])
    or st.session_state.get(
        "odds_rows",
        [],
    )
)

riders: list[dict[str, Any]] = (
    st.session_state.get(
        "rider_data",
        [],
    )
)

lineup_groups: list[list[int]] = (
    st.session_state.get(
        "lineup_groups",
        [],
    )
)

odds_logs: list[str] = (
    st.session_state.get(
        "odds_logs",
        [],
    )
)

odds_complete = any(
    str(log).strip()
    == "オッズデータ完全性: OK"
    for log in odds_logs
)

if not odds_rows:
    st.warning(
        "オッズデータがありません。"
        "メイン画面で対象レースを取得してください。"
    )
    st.stop()

if not riders:
    st.warning(
        "選手データがありません。"
        "メイン画面で出走表を取得してください。"
    )
    st.stop()

if not odds_complete:
    st.error(
        "オッズデータ完全性がOKではありません。"
        "不完全なオッズでは予測しません。"
    )
    st.stop()

default_date = st.session_state.get(
    "selected_date",
    date.today(),
)

if hasattr(default_date, "isoformat"):
    race_date = default_date.isoformat()
else:
    race_date = str(default_date)

venue = str(
    st.session_state.get(
        "venue",
        st.session_state.get(
            "selected_venue",
            "",
        ),
    )
)

race_number = int(
    st.session_state.get(
        "race_number",
        st.session_state.get(
            "selected_race_number",
            0,
        ),
    )
)

st.info(
    "このページは検証用です。"
    "現行の買い目プランへはまだ反映しません。"
)

with st.form(
    "learned_model_prediction_form",
    clear_on_submit=False,
    enter_to_submit=False,
):
    setting_col1, setting_col2 = (
        st.columns(2)
    )

    with setting_col1:
        market_blend = st.slider(
            "市場確率の混合率",
            min_value=0.0,
            max_value=0.90,
            value=0.25,
            step=0.05,
            help=(
                "0なら学習モデルのみ、"
                "高いほど市場オッズへ近づきます。"
            ),
        )

    with setting_col2:
        minimum_expected_return = (
            st.number_input(
                "候補表示の最低期待回収率",
                min_value=0.50,
                max_value=5.00,
                value=1.05,
                step=0.05,
            )
        )

    predict_button = st.form_submit_button(
        "現在レースを予測",
        type="primary",
    )

if predict_button:
    try:
        prediction, metadata = (
            predict_current_race(
                odds_rows=odds_rows,
                riders=riders,
                lineup_groups=lineup_groups,
                race_id=(
                    f"{race_date}_"
                    f"{venue}_"
                    f"{race_number}"
                ),
                race_date=race_date,
                venue=venue,
                race_number=race_number,
                market_blend=float(
                    market_blend
                ),
            )
        )

        st.session_state[
            "learned_prediction"
        ] = prediction

        st.session_state[
            "learned_prediction_metadata"
        ] = metadata

        st.success(
            f"{len(prediction)}組の予測が完了しました。"
        )

    except Exception as exc:
        st.error(
            f"{type(exc).__name__}: {exc}"
        )

prediction = st.session_state.get(
    "learned_prediction"
)

metadata = st.session_state.get(
    "learned_prediction_metadata",
    {},
)

if isinstance(prediction, pd.DataFrame):
    if prediction.empty:
        st.warning(
            "予測結果は0件です。"
        )
        st.stop()

    st.divider()
    st.subheader("モデル情報")

    model_col1, model_col2, model_col3 = (
        st.columns(3)
    )

    with model_col1:
        st.metric(
            "学習レース数",
            f"{metadata.get('training_race_count', 0):,}",
        )

    with model_col2:
        st.metric(
            "学習組番数",
            f"{metadata.get('training_row_count', 0):,}",
        )

    with model_col3:
        st.metric(
            "使用特徴量数",
            f"{metadata.get('feature_count', 0):,}",
        )

    st.caption(
        "モデル学習日時："
        f"{metadata.get('trained_at', '')}"
    )

    st.divider()
    st.subheader("確率上位")

    probability_top = prediction.head(20).copy()

    probability_top["学習モデル確率"] = (
        probability_top[
            "学習モデル確率"
        ] * 100
    ).round(4)

    probability_top["市場確率"] = (
        probability_top[
            "市場確率"
        ] * 100
    ).round(4)

    probability_top["最終確率"] = (
        probability_top[
            "最終確率"
        ] * 100
    ).round(4)

    probability_top["期待回収率"] = (
        probability_top[
            "期待回収率"
        ]
    ).round(3)

    probability_top["フェアオッズ"] = (
        probability_top[
            "フェアオッズ"
        ]
    ).round(1)

    probability_top = probability_top.rename(
        columns={
            "combination": "組番",
            "popularity": "人気",
            "odds": "オッズ",
            "学習モデル確率": "学習確率%",
            "市場確率": "市場確率%",
            "最終確率": "最終確率%",
        }
    )

    st.dataframe(
        probability_top,
        use_container_width=True,
        hide_index=True,
    )

    st.divider()
    st.subheader("期待値候補")

    value_candidates = prediction[
        prediction["期待回収率"]
        >= float(minimum_expected_return)
    ].copy()

    value_candidates = value_candidates.sort_values(
        "期待回収率",
        ascending=False,
    )

    if value_candidates.empty:
        st.warning(
            "現在の条件では期待値候補は0件です。"
        )

    else:
        display_candidates = (
            value_candidates.head(50).copy()
        )

        display_candidates[
            "最終確率"
        ] = (
            display_candidates[
                "最終確率"
            ] * 100
        ).round(4)

        display_candidates[
            "期待回収率"
        ] = display_candidates[
            "期待回収率"
        ].round(3)

        display_candidates[
            "期待利益率"
        ] = (
            display_candidates[
                "期待利益率"
            ] * 100
        ).round(1)

        display_candidates[
            "市場比"
        ] = display_candidates[
            "市場比"
        ].round(3)

        display_candidates = (
            display_candidates.rename(
                columns={
                    "combination": "組番",
                    "popularity": "人気",
                    "odds": "オッズ",
                    "最終確率": "最終確率%",
                    "期待利益率": "期待利益率%",
                }
            )
        )

        st.dataframe(
            display_candidates,
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    csv_data = prediction.to_csv(
        index=False,
    ).encode("utf-8-sig")

    st.download_button(
        "学習モデル予測CSVをダウンロード",
        data=csv_data,
        file_name=(
            f"{race_date}_"
            f"{venue}_"
            f"{race_number}R_"
            "learned_prediction.csv"
        ),
        mime="text/csv",
    )
