from __future__ import annotations

import pandas as pd
import streamlit as st

from learning_backtest import (
    run_walk_forward_backtest,
)
from learning_database import (
    get_database_summary,
)


st.set_page_config(
    page_title="モデルバックテスト",
    page_icon="🧪",
    layout="wide",
)

st.title("🧪 学習モデル・バックテスト")

st.caption(
    "テスト対象より前のレースだけで学習し、"
    "実際の確定払戻を使って収支を検証します。"
)

database_summary = get_database_summary()

info_col1, info_col2 = st.columns(2)

with info_col1:
    st.metric(
        "保存レース数",
        f"{database_summary['race_count']:,}",
    )

with info_col2:
    st.metric(
        "結果確定レース",
        f"{database_summary['completed_count']:,}",
    )

st.warning(
    "正確な回収率を計算するには、"
    "結果登録時に3連単の確定払戻を"
    "入力しておく必要があります。"
)

with st.form(
    "walk_forward_backtest_form",
    clear_on_submit=False,
    enter_to_submit=False,
):
    row1_col1, row1_col2, row1_col3 = (
        st.columns(3)
    )

    with row1_col1:
        minimum_training_races = (
            st.number_input(
                "初期学習レース数",
                min_value=10,
                max_value=5000,
                value=30,
                step=10,
            )
        )

    with row1_col2:
        maximum_test_races = (
            st.number_input(
                "最大テストレース数",
                min_value=10,
                max_value=1000,
                value=100,
                step=10,
            )
        )

    with row1_col3:
        market_blend = st.slider(
            "市場確率の混合率",
            min_value=0.0,
            max_value=0.90,
            value=0.25,
            step=0.05,
        )

    row2_col1, row2_col2, row2_col3 = (
        st.columns(3)
    )

    with row2_col1:
        minimum_expected_return = (
            st.number_input(
                "最低期待回収率",
                min_value=1.00,
                max_value=5.00,
                value=1.10,
                step=0.05,
            )
        )

    with row2_col2:
        maximum_odds = st.number_input(
            "最大対象オッズ",
            min_value=10.0,
            max_value=9999.9,
            value=300.0,
            step=10.0,
        )

    with row2_col3:
        maximum_bets_per_race = (
            st.number_input(
                "1レース最大買い目数",
                min_value=1,
                max_value=30,
                value=5,
                step=1,
            )
        )

    stake_per_bet = st.selectbox(
        "1点あたり購入額",
        options=[
            100,
            200,
            300,
            500,
            1000,
        ],
        index=0,
        format_func=(
            lambda value: f"{value:,}円"
        ),
    )

    execute_backtest = (
        st.form_submit_button(
            "時系列バックテストを実行",
            type="primary",
        )
    )

if execute_backtest:
    try:
        with st.spinner(
            "過去レースを順番に学習・予測しています。"
        ):
            result = run_walk_forward_backtest(
                minimum_training_races=int(
                    minimum_training_races
                ),
                maximum_test_races=int(
                    maximum_test_races
                ),
                market_blend=float(
                    market_blend
                ),
                minimum_expected_return=float(
                    minimum_expected_return
                ),
                maximum_odds=float(
                    maximum_odds
                ),
                maximum_bets_per_race=int(
                    maximum_bets_per_race
                ),
                stake_per_bet=int(
                    stake_per_bet
                ),
            )

        st.session_state[
            "backtest_result"
        ] = result

        st.success(
            "バックテストが完了しました。"
        )

    except Exception as exc:
        st.error(
            f"{type(exc).__name__}: {exc}"
        )

result = st.session_state.get(
    "backtest_result"
)

if result:
    summary = result["summary"]
    race_results: pd.DataFrame = (
        result["races"]
    )

    st.divider()
    st.subheader("収支結果")

    result_col1, result_col2, result_col3 = (
        st.columns(3)
    )

    with result_col1:
        st.metric(
            "回収率",
            f"{summary['return_rate'] * 100:.1f}%",
        )

        st.metric(
            "的中率",
            f"{summary['hit_rate'] * 100:.1f}%",
        )

    with result_col2:
        st.metric(
            "購入総額",
            f"{summary['total_purchase']:,}円",
        )

        st.metric(
            "払戻総額",
            f"{summary['total_payout']:,}円",
        )

    with result_col3:
        st.metric(
            "最終収支",
            f"{summary['total_profit']:+,}円",
        )

        st.metric(
            "的中数",
            (
                f"{summary['hit_count']} / "
                f"{summary['betting_races']}"
            ),
        )

    st.divider()
    st.subheader("予測順位評価")

    rank_col1, rank_col2, rank_col3 = (
        st.columns(3)
    )

    with rank_col1:
        st.metric(
            "確率1位的中率",
            f"{summary['top1_rate'] * 100:.2f}%",
        )

    with rank_col2:
        st.metric(
            "確率3位以内率",
            f"{summary['top3_rate'] * 100:.2f}%",
        )

    with rank_col3:
        mean_rank = summary[
            "mean_winner_rank"
        ]

        st.metric(
            "的中組番の平均予測順位",
            (
                f"{mean_rank:.2f}位"
                if pd.notna(mean_rank)
                else "算出不可"
            ),
        )

    st.caption(
        "確定払戻未登録のため除外："
        f"{summary['skipped_no_payout']}レース"
    )

    st.divider()
    st.subheader("レース別結果")

    display = race_results.copy()

    display["hit"] = display["hit"].map(
        {
            True: "的中",
            False: "不的中",
        }
    )

    display["winner_probability"] = (
        display["winner_probability"]
        * 100
    ).round(4)

    display[
        "winner_expected_return"
    ] = display[
        "winner_expected_return"
    ].round(3)

    display = display.rename(
        columns={
            "race_date": "開催日",
            "venue": "競輪場",
            "race_number": "R",
            "winning_combination": "確定組番",
            "selected_combinations": "購入組番",
            "selected_count": "点数",
            "purchase_amount": "購入額",
            "payout_amount": "払戻額",
            "profit": "収支",
            "hit": "結果",
            "winner_prediction_rank": (
                "的中組番予測順位"
            ),
            "winner_probability": (
                "的中組番確率%"
            ),
            "winner_expected_return": (
                "的中組番期待回収率"
            ),
        }
    )

    display_columns = [
        "開催日",
        "競輪場",
        "R",
        "確定組番",
        "購入組番",
        "点数",
        "購入額",
        "払戻額",
        "収支",
        "結果",
        "的中組番予測順位",
        "的中組番確率%",
        "的中組番期待回収率",
    ]

    st.dataframe(
        display[display_columns],
        use_container_width=True,
        hide_index=True,
    )

    csv_data = race_results.to_csv(
        index=False,
    ).encode("utf-8-sig")

    st.download_button(
        "バックテスト結果CSVをダウンロード",
        data=csv_data,
        file_name=(
            "keirin_walk_forward_backtest.csv"
        ),
        mime="text/csv",
    )
