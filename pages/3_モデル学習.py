from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from learning_features import (
    build_training_dataframe,
)
from train_learning_model import (
    METADATA_PATH,
    MODEL_PATH,
    train_baseline_model,
)


st.set_page_config(
    page_title="モデル学習",
    page_icon="📈",
    layout="wide",
)

st.title("📈 過去レースモデル学習")

st.warning(
    "モデル学習には結果確定済みのレースだけを使います。"
    "少数レースでの成績は参考値です。"
)

dataframe = build_training_dataframe()

if dataframe.empty:
    st.error(
        "学習可能なデータがありません。"
        "先に学習データ収集ページでレース結果を"
        "登録してください。"
    )
    st.stop()

race_count = int(
    dataframe["race_id"].nunique()
)

row_count = len(dataframe)
winning_rows = int(
    dataframe["target"].sum()
)

metric_col1, metric_col2, metric_col3 = (
    st.columns(3)
)

with metric_col1:
    st.metric(
        "結果確定レース",
        f"{race_count:,}",
    )

with metric_col2:
    st.metric(
        "学習候補組番",
        f"{row_count:,}",
    )

with metric_col3:
    st.metric(
        "的中組番",
        f"{winning_rows:,}",
    )

st.caption(
    "1レースにつき正解は1組だけなので、"
    "通常は的中組番数とレース数が一致します。"
)

with st.form(
    "train_baseline_model_form",
    clear_on_submit=False,
    enter_to_submit=False,
):
    settings_col1, settings_col2 = (
        st.columns(2)
    )

    with settings_col1:
        minimum_completed_races = (
            st.number_input(
                "最低学習レース数",
                min_value=10,
                max_value=10_000,
                value=30,
                step=10,
            )
        )

    with settings_col2:
        cross_validation_splits = (
            st.selectbox(
                "交差検証の分割数",
                options=[2, 3, 4, 5],
                index=3,
            )
        )

    train_button = st.form_submit_button(
        "基準モデルを学習",
        type="primary",
    )

if train_button:
    try:
        with st.spinner(
            "レース単位で交差検証し、"
            "モデルを学習しています。"
        ):
            metadata = train_baseline_model(
                minimum_completed_races=int(
                    minimum_completed_races
                ),
                cross_validation_splits=int(
                    cross_validation_splits
                ),
            )

        st.success(
            "モデル学習と保存が完了しました。"
        )

        st.session_state[
            "latest_training_metadata"
        ] = metadata

    except Exception as exc:
        st.error(
            f"{type(exc).__name__}: {exc}"
        )

metadata = st.session_state.get(
    "latest_training_metadata"
)

if (
    metadata is None
    and METADATA_PATH.exists()
):
    metadata = json.loads(
        METADATA_PATH.read_text(
            encoding="utf-8"
        )
    )

if metadata:
    st.divider()
    st.subheader("最新モデルの評価")

    evaluation_col1, evaluation_col2 = (
        st.columns(2)
    )

    with evaluation_col1:
        st.metric(
            "Top1的中率",
            f"{metadata['top1_hit_rate'] * 100:.2f}%",
        )

        st.metric(
            "Top3的中率",
            f"{metadata['top3_hit_rate'] * 100:.2f}%",
        )

        st.metric(
            "平均的中順位",
            f"{metadata['mean_winner_rank']:.2f}位",
        )

    with evaluation_col2:
        st.metric(
            "ROC AUC",
            f"{metadata['roc_auc']:.4f}",
        )

        st.metric(
            "レース対数損失",
            f"{metadata['race_log_loss']:.4f}",
        )

        st.metric(
            "学習レース数",
            f"{metadata['race_count']:,}",
        )

    st.caption(
        "Top1的中率はモデル確率1位の組番が"
        "実際に的中した割合です。"
    )

    fold_rows = metadata.get(
        "fold_results",
        [],
    )

    if fold_rows:
        st.markdown("#### 交差検証")

        st.dataframe(
            pd.DataFrame(fold_rows),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("#### 保存先")

    st.code(str(MODEL_PATH))

st.divider()
st.subheader("学習データCSV")

csv_data = dataframe.to_csv(
    index=False,
).encode("utf-8-sig")

st.download_button(
    "学習データCSVをダウンロード",
    data=csv_data,
    file_name="keirin_training_data.csv",
    mime="text/csv",
)
