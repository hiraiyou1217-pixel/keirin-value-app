from __future__ import annotations

import json
from datetime import date
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from android_prediction_import import (
    discover_google_drive_directories,
    import_android_predictions,
)
from current_race_snapshot import (
    load_current_race_snapshot,
    resolve_prediction_context,
)
from google_drive_prediction_import import (
    connect_google_drive,
    disconnect_google_drive,
    google_drive_connection_status,
    import_google_drive_predictions,
    save_google_drive_client_config,
)
from independent_learning_features import (
    get_independent_training_summary,
)
from independent_model_prediction import (
    predict_independent_race,
)
from learning_database import (
    get_independent_evaluation_segments,
    get_independent_evaluation_summary,
    get_independent_hole_hits,
    get_independent_prediction_detail,
    get_recent_independent_evaluations,
    save_independent_prediction,
    sync_independent_prediction_results,
)
from race_metadata import (
    get_venue_characteristics,
)
from train_independent_model import (
    INDEPENDENT_METADATA_PATH,
    INDEPENDENT_MODEL_PATH,
    train_independent_model,
)


st.set_page_config(
    page_title="オッズ非依存AI",
    page_icon="🧭",
    layout="wide",
)

st.title("🧭 オッズ非依存AI")


@st.dialog(
    "保存済みの着順確率",
    width="large",
)
def show_prediction_detail(
    run_id: str,
) -> None:
    detail = (
        get_independent_prediction_detail(
            run_id
        )
    )

    if detail is None:
        st.error(
            "選択した予測履歴を"
            "読み込めませんでした。"
        )
        return

    st.markdown(
        "### "
        f"{detail['race_date']} "
        f"{detail['venue']} "
        f"{detail['race_number']}R"
    )
    evaluation_label = (
        "正式評価"
        if detail["evaluation_eligible"]
        else "参考記録"
    )
    st.caption(
        f"{evaluation_label} / "
        f"状態: {detail['result_status']} / "
        f"予測日時: {detail['predicted_at']} / "
        f"モデル: {detail['model_version']}"
    )

    if (
        detail["result_status"] == "確定"
        and detail.get(
            "winning_combination"
        )
    ):
        st.success(
            "実際の的中組番: "
            f"{detail['winning_combination']} / "
            f"AI順位: {detail['winning_rank']}位 / "
            "AI確率: "
            f"{float(detail['winning_probability'] or 0) * 100:.4f}% / "
            "100円払戻: "
            f"{int(detail['payout_per_100'] or 0):,}円"
        )

    if (
        not detail["evaluation_eligible"]
        and detail.get(
            "eligibility_reason"
        )
    ):
        st.info(
            "参考記録の理由: "
            + str(
                detail[
                    "eligibility_reason"
                ]
            )
        )

    (
        rider_probability_tab,
        combination_probability_tab,
    ) = st.tabs(
        [
            "選手別の着順確率",
            "3連単の全組番",
        ]
    )

    with rider_probability_tab:
        rider_html_rows = []

        for rider in detail[
            "rider_probabilities"
        ]:
            rider_html_rows.append(
                "<tr>"
                f"<td>{int(rider['car_number'])}</td>"
                "<td>"
                f"{escape(str(rider['rider_name']))}"
                "</td>"
                "<td>"
                f"{float(rider['first_probability']) * 100:.4f}%"
                "</td>"
                "<td>"
                f"{float(rider['second_probability']) * 100:.4f}%"
                "</td>"
                "<td>"
                f"{float(rider['third_probability']) * 100:.4f}%"
                "</td>"
                "<td>"
                f"{float(rider['top3_probability']) * 100:.4f}%"
                "</td>"
                "</tr>"
            )

        st.html(
            """
            <style>
            .keirin-probability-table {
                width: 100%;
                border-collapse: collapse;
                font-size: 0.92rem;
            }
            .keirin-probability-table th,
            .keirin-probability-table td {
                border-bottom: 1px solid rgba(128, 128, 128, 0.28);
                padding: 0.48rem 0.55rem;
                text-align: right;
                white-space: nowrap;
            }
            .keirin-probability-table th:nth-child(2),
            .keirin-probability-table td:nth-child(2) {
                text-align: left;
            }
            .keirin-probability-table th {
                background: rgba(128, 128, 128, 0.16);
                font-weight: 700;
            }
            </style>
            <table class="keirin-probability-table">
                <thead>
                    <tr>
                        <th>車番</th>
                        <th>選手名</th>
                        <th>1着確率</th>
                        <th>2着確率</th>
                        <th>3着確率</th>
                        <th>3着内確率</th>
                    </tr>
                </thead>
                <tbody>
            """
            + "".join(rider_html_rows)
            + """
                </tbody>
            </table>
            """
        )

    with combination_probability_tab:
        combination_html_rows = []

        for row in detail[
            "prediction_rows"
        ]:
            row_class = (
                ' class="winner-row"'
                if row["is_winner"]
                else ""
            )
            combination_html_rows.append(
                f"<tr{row_class}>"
                "<td>"
                f"{int(row['predicted_rank'])}"
                "</td>"
                "<td>"
                f"{escape(str(row['combination']))}"
                "</td>"
                "<td>"
                f"{float(row['ai_probability']) * 100:.6f}%"
                "</td>"
                "<td>"
                + (
                    "的中"
                    if row["is_winner"]
                    else ""
                )
                + "</td>"
                "</tr>"
            )

        st.caption(
            f"保存組番数: "
            f"{len(combination_html_rows):,}組 / "
            "確率合計: "
            f"{float(detail['probability_sum']) * 100:.6f}%"
        )
        st.html(
            """
            <style>
            .keirin-combination-table-wrap {
                max-height: 500px;
                overflow: auto;
                border: 1px solid rgba(128, 128, 128, 0.28);
                border-radius: 0.45rem;
            }
            .keirin-combination-table {
                width: 100%;
                border-collapse: collapse;
                font-size: 0.92rem;
            }
            .keirin-combination-table th,
            .keirin-combination-table td {
                border-bottom: 1px solid rgba(128, 128, 128, 0.25);
                padding: 0.42rem 0.55rem;
                text-align: right;
                white-space: nowrap;
            }
            .keirin-combination-table th {
                position: sticky;
                top: 0;
                z-index: 1;
                background: rgb(128, 128, 128);
                color: white;
                font-weight: 700;
            }
            .keirin-combination-table .winner-row {
                background: rgba(0, 180, 90, 0.18);
                font-weight: 700;
            }
            </style>
            <div class="keirin-combination-table-wrap">
                <table class="keirin-combination-table">
                    <thead>
                        <tr>
                            <th>AI順位</th>
                            <th>組番</th>
                            <th>AI確率</th>
                            <th>結果</th>
                        </tr>
                    </thead>
                    <tbody>
            """
            + "".join(
                combination_html_rows
            )
            + """
                    </tbody>
                </table>
            </div>
            """
        )


st.success(
    "このAIは、3連単オッズ・人気順位・"
    "市場確率・払戻金・WINTICKET AI印を"
    "学習にも予測にも使用しません。"
)

st.caption(
    "競走得点、脚質、S/H/B、勝率、連対率、"
    "選手属性、競輪場特性、レース条件、直近成績、"
    "選手コメント、並びなど、発走前に分かる情報だけで"
    "全3連単組番を評価します。"
)

summary = get_independent_training_summary()

(
    summary_col1,
    summary_col2,
    summary_col3,
    summary_col4,
) = (
    st.columns(4)
)

with summary_col1:
    st.metric(
        "学習可能（前日以前）",
        f"{summary['completed_races']:,}",
    )

with summary_col2:
    st.metric(
        "当日以降を自動除外",
        (
            f"{summary['excluded_after_cutoff_races']:,}"
        ),
    )

with summary_col3:
    st.metric(
        "学習から除外する要確認",
        f"{summary['review_races']:,}",
    )

with summary_col4:
    st.metric(
        "推奨学習件数",
        "500件以上",
    )

st.caption(
    "今回の学習締切（日本時間）："
    f"{summary['training_cutoff_date']}。"
    "当日開催分は結果確定済みでも"
    "モデルへ入力しません。"
)

st.info(
    "30〜100レースでも動作確認はできますが、"
    "予測精度の判断には少なくとも300〜500レース、"
    "できれば1,000レース以上を推奨します。"
)

st.divider()
st.subheader("1. 独立モデルを学習")

with st.form(
    "train_odds_independent_model",
    clear_on_submit=False,
    enter_to_submit=False,
):
    training_col1, training_col2 = (
        st.columns(2)
    )

    with training_col1:
        minimum_completed_races = (
            st.number_input(
                "最低学習レース数",
                min_value=30,
                max_value=20_000,
                value=100,
                step=10,
            )
        )

    with training_col2:
        validation_splits = st.selectbox(
            "日付順検証の分割数",
            options=[2, 3, 4, 5],
            index=2,
        )

    train_button = st.form_submit_button(
        "オッズ非依存AIを学習",
        type="primary",
    )

if train_button:
    try:
        with st.spinner(
            "過去から未来の順で検証し、"
            "独立モデルを学習しています。"
        ):
            metadata = (
                train_independent_model(
                    minimum_completed_races=int(
                        minimum_completed_races
                    ),
                    cross_validation_splits=int(
                        validation_splits
                    ),
                )
            )

        st.session_state[
            "independent_training_metadata"
        ] = metadata
        if metadata.get("promoted", True):
            st.success(
                "新モデルは自動昇格判定を"
                "通過し、正式モデルとして"
                "保存されました。"
            )
        else:
            st.warning(
                "新モデルは自動昇格条件を"
                "満たさなかったため、現行モデルを"
                "維持し、候補モデルとして保存しました。"
            )

    except Exception as exc:
        st.error(
            f"{type(exc).__name__}: {exc}"
        )

metadata = st.session_state.get(
    "independent_training_metadata"
)

if (
    metadata is None
    and INDEPENDENT_METADATA_PATH.exists()
):
    try:
        metadata = json.loads(
            INDEPENDENT_METADATA_PATH.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ):
        metadata = None

if metadata:
    st.markdown("#### モデルの時系列評価")
    promotion = metadata.get(
        "promotion",
        {},
    )

    if promotion:
        if metadata.get("promoted", True):
            st.success(
                "自動昇格判定：採用"
                "（"
                + str(
                    promotion.get(
                        "reason",
                        "",
                    )
                )
                + "）"
            )
        else:
            st.warning(
                "自動昇格判定：現行モデルを維持"
                "（"
                + str(
                    promotion.get(
                        "reason",
                        "",
                    )
                )
                + "）"
            )

    evaluation_col1, evaluation_col2, (
        evaluation_col3
    ), evaluation_col4 = st.columns(4)

    with evaluation_col1:
        st.metric(
            "3連単 Top1",
            (
                f"{metadata.get('top1_hit_rate', 0) * 100:.2f}%"
            ),
        )

    with evaluation_col2:
        st.metric(
            "3連単 Top5",
            (
                f"{metadata.get('top5_hit_rate', 0) * 100:.2f}%"
            ),
        )

    with evaluation_col3:
        st.metric(
            "3連単 Top10",
            (
                f"{metadata.get('top10_hit_rate', 0) * 100:.2f}%"
            ),
        )

    with evaluation_col4:
        st.metric(
            "1着予測",
            (
                f"{metadata.get('first_place_hit_rate', 0) * 100:.2f}%"
            ),
        )

    detail_col1, detail_col2, detail_col3 = (
        st.columns(3)
    )

    with detail_col1:
        st.metric(
            "学習レース数",
            f"{metadata.get('race_count', 0):,}",
        )

    with detail_col2:
        st.metric(
            "平均的中順位",
            (
                f"{metadata.get('mean_winner_rank', 0):.2f}位"
            ),
        )

    with detail_col3:
        st.metric(
            "使用特徴量数",
            f"{metadata.get('feature_count', 0):,}",
        )

    st.caption(
        "モデル学習日時："
        f"{metadata.get('trained_at', '')}"
    )
    st.caption(
        "モデル学習期間："
        f"{metadata.get('training_start_date', '')}"
        "〜"
        f"{metadata.get('training_end_date', '')}"
    )
    st.caption(
        "学習設定締切："
        f"{metadata.get('training_cutoff_date', '')}"
        "／締切後の自動除外："
        f"{metadata.get('excluded_after_cutoff_race_count', 0):,}"
        "レース"
    )

    if (
        not metadata.get(
            "training_end_date"
        )
        or not metadata.get(
            "training_cutoff_date"
        )
    ):
        st.warning(
            "このモデルには学習期間または"
            "当日除外の締切記録がありません。"
            "客観評価を開始する前にモデルを"
            "再学習してください。"
        )

    with st.expander(
        "オッズ非依存監査を表示"
    ):
        st.write(
            "モデル属性：",
            (
                "オッズ非依存"
                if metadata.get(
                    "odds_independent"
                )
                else "要確認"
            ),
        )
        st.write(
            "除外入力："
            + "、".join(
                metadata.get(
                    "excluded_inputs",
                    [],
                )
            )
        )
        feature_groups = metadata.get(
            "feature_groups",
            [],
        )

        if feature_groups:
            st.write(
                "使用する拡張特徴："
                + "／".join(
                    str(value)
                    for value in feature_groups
                )
            )

        feature_coverage = metadata.get(
            "feature_coverage",
            {},
        )

        if feature_coverage:
            st.write(
                "学習データの拡張特徴カバレッジ：",
                feature_coverage,
            )

        calibration = metadata.get(
            "probability_calibration",
            {},
        )
        calibration_metrics = metadata.get(
            "calibration_metrics",
            {},
        )

        if calibration:
            st.write(
                "確率校正：",
                calibration,
            )

        if calibration_metrics:
            st.write(
                "校正前後の確率指標：",
                calibration_metrics,
            )

        promotion_checks = promotion.get(
            "checks",
            {},
        )

        if promotion_checks:
            st.write(
                "自動昇格の判定項目：",
                promotion_checks,
            )

        fold_results = metadata.get(
            "fold_results",
            [],
        )

        if fold_results:
            st.dataframe(
                pd.DataFrame(fold_results),
                use_container_width=True,
                hide_index=True,
            )

    segmented_evaluation = metadata.get(
        "segmented_evaluation",
        {},
    )

    if segmented_evaluation:
        with st.expander(
            "時系列検証の条件別評価を表示"
        ):
            selected_dimension = st.selectbox(
                "評価条件",
                options=list(
                    segmented_evaluation.keys()
                ),
                key=(
                    "training_segment_dimension"
                ),
            )
            segment_rows = (
                segmented_evaluation.get(
                    selected_dimension,
                    [],
                )
            )

            if segment_rows:
                segment_frame = pd.DataFrame(
                    segment_rows
                ).rename(
                    columns={
                        "condition": "条件",
                        "evaluated_race_count": (
                            "検証レース数"
                        ),
                        "top1_hit_rate": (
                            "Top1"
                        ),
                        "top5_hit_rate": (
                            "Top5"
                        ),
                        "top10_hit_rate": (
                            "Top10"
                        ),
                        "top30_hit_rate": (
                            "Top30"
                        ),
                        "mean_winner_rank": (
                            "平均的中順位"
                        ),
                        "race_log_loss": (
                            "LogLoss"
                        ),
                    }
                )
                st.dataframe(
                    segment_frame,
                    use_container_width=True,
                    hide_index=True,
                )

else:
    st.caption(
        "独立モデルはまだ作成されていません。"
    )

st.divider()
st.subheader("2. 現在レースを予測")

snapshot = load_current_race_snapshot()
prediction_context = resolve_prediction_context(
    snapshot,
    st.session_state,
    default_date=date.today().isoformat(),
)
riders = prediction_context["riders"]
lineup_groups = prediction_context[
    "lineup_groups"
]
race_date_value = prediction_context[
    "race_date"
]

if hasattr(
    race_date_value,
    "isoformat",
):
    race_date_text = (
        race_date_value.isoformat()
    )
else:
    race_date_text = str(
        race_date_value
    )

venue = str(
    prediction_context["venue"]
)
race_number = int(
    prediction_context["race_number"]
    or 0
)
race_id = (
    f"{race_date_text}_"
    f"{venue}_"
    f"{race_number}"
)

st.write(
    "予測対象："
    f"{race_date_text} "
    f"{venue} "
    f"{race_number}R"
)
race_conditions = dict(
    prediction_context.get(
        "race_conditions",
        {},
    )
    or {}
)
profile_rider_count = sum(
    bool(
        rider.get("選手ID")
        or rider.get("府県")
        or rider.get("級班")
    )
    for rider in riders
)
venue_characteristics = (
    get_venue_characteristics(
        venue
    )
)

with st.expander(
    "今回の拡張特徴を確認",
):
    st.write(
        "選手属性："
        f"{profile_rider_count}/{len(riders)}人"
    )
    st.write(
        "競輪場特性："
        f"周長 {venue_characteristics['bank_length_m']}m／"
        f"みなし直線 {venue_characteristics['home_straight_m']}m／"
        f"最大カント {venue_characteristics['max_cant_degrees']}°"
    )
    st.write(
        "レース条件：",
        (
            race_conditions
            if race_conditions
            else "未取得"
        ),
    )
    st.write(
        "並び："
        + " / ".join(
            "-".join(
                str(number)
                for number in group
            )
            for group in lineup_groups
        )
    )
    st.caption(
        "直近成績は対象日より前の確定済みSQLite履歴だけを"
        "選手ID（未取得時は選手名）で照合し、予測時に自動反映します。"
    )

if (
    prediction_context["source"]
    == "snapshot"
):
    st.caption(
        "使用データ：メイン画面で最後に保存した"
        "現在レース"
        + (
            "（保存時刻 "
            f"{prediction_context['saved_at']}）"
            if prediction_context[
                "saved_at"
            ]
            else ""
        )
    )

if (
    riders
    and not prediction_context[
        "odds_complete"
    ]
):
    st.info(
        "オッズなしで保存された現在レースです。"
        "このページの予測はオッズを使用しないため、"
        "そのまま実行できます。"
    )

rider_numbers: set[int] = set()

for rider in riders:
    try:
        car_number = int(
            float(
                rider.get("車番", 0)
            )
        )
    except (TypeError, ValueError):
        continue

    if car_number > 0:
        rider_numbers.add(car_number)
lineup_numbers: list[int] = []

for group in lineup_groups:
    for number in group:
        try:
            lineup_numbers.append(
                int(number)
            )
        except (TypeError, ValueError):
            continue
lineup_complete = (
    bool(rider_numbers)
    and len(lineup_numbers)
    == len(set(lineup_numbers))
    and set(lineup_numbers)
    == rider_numbers
)
prediction_ready = True

if not INDEPENDENT_MODEL_PATH.exists():
    st.warning(
        "先にこのページ上部で"
        "独立モデルを学習してください。"
    )
    prediction_ready = False

if not riders:
    st.warning(
        "現在レースの選手データがありません。"
        "メイン画面で出走表を取得してください。"
    )
    prediction_ready = False

if riders and not lineup_complete:
    st.warning(
        "現在レースの並びが未取得または"
        "不完全です。メイン画面で並びまで"
        "取得してください。"
    )
    prediction_ready = False

st.caption(
    "現在レースのスナップショットにオッズが"
    "含まれていても、このページは一切参照しません。"
)

predict_button = st.button(
    "オッズを使わず予測",
    type="primary",
    disabled=not prediction_ready,
)

if predict_button:
    try:
        with st.spinner(
            "全3連単組番を評価しています。"
        ):
            (
                combination_prediction,
                rider_prediction,
                prediction_metadata,
            ) = predict_independent_race(
                riders=riders,
                lineup_groups=lineup_groups,
                race_id=race_id,
                race_date=race_date_text,
                venue=venue,
                race_number=race_number,
                race_conditions=(
                    prediction_context.get(
                        "race_conditions",
                        {},
                    )
                ),
            )

        prediction_record = (
            save_independent_prediction(
                race_date=race_date_text,
                venue=venue,
                race_number=race_number,
                prediction_rows=(
                    combination_prediction
                    .to_dict("records")
                ),
                model_metadata=(
                    prediction_metadata
                ),
                input_snapshot={
                    "saved_at": (
                        prediction_context[
                            "saved_at"
                        ]
                    ),
                    "race_date": (
                        race_date_text
                    ),
                    "venue": venue,
                    "race_number": (
                        race_number
                    ),
                    "race_url": (
                        prediction_context[
                            "race_url"
                        ]
                    ),
                    "riders": riders,
                    "lineup_groups": (
                        lineup_groups
                    ),
                    "race_conditions": (
                        prediction_context.get(
                            "race_conditions",
                            {},
                        )
                    ),
                },
            )
        )
        prediction_metadata[
            "prediction_run_id"
        ] = prediction_record["run_id"]
        prediction_metadata[
            "evaluation_eligible"
        ] = bool(
            prediction_record[
                "evaluation_eligible"
            ]
        )
        prediction_metadata[
            "eligibility_reason"
        ] = str(
            prediction_record[
                "eligibility_reason"
            ]
            or ""
        )
        st.session_state[
            "independent_combination_prediction"
        ] = combination_prediction
        st.session_state[
            "independent_rider_prediction"
        ] = rider_prediction
        st.session_state[
            "independent_prediction_metadata"
        ] = prediction_metadata
        st.success(
            f"{len(combination_prediction)}組の"
            "独立予測が完了しました。"
        )

        if prediction_record["created"]:
            if prediction_record[
                "evaluation_eligible"
            ]:
                st.success(
                    "正式評価予測として"
                    "順位を固定保存しました。"
                )
            else:
                st.info(
                    "予測履歴へ参考記録として"
                    "保存しました："
                    + str(
                        prediction_record[
                            "eligibility_reason"
                        ]
                        or ""
                    )
                )
        else:
            st.info(
                "同一レース・同一モデルの"
                "初回予測を保持しています。"
                "順位は上書きしていません。"
            )

    except Exception as exc:
        st.error(
            f"{type(exc).__name__}: {exc}"
        )

combination_prediction = (
    st.session_state.get(
        "independent_combination_prediction"
    )
)
rider_prediction = st.session_state.get(
    "independent_rider_prediction"
)
prediction_metadata = (
    st.session_state.get(
        "independent_prediction_metadata",
        {},
    )
)

if (
    isinstance(
        combination_prediction,
        pd.DataFrame,
    )
    and not combination_prediction.empty
    and prediction_metadata.get(
        "race_id"
    )
    == race_id
):
    st.markdown("#### 3連単確率上位")
    display_combinations = (
        combination_prediction.head(30).copy()
    )
    display_combinations[
        "AI確率"
    ] = (
        display_combinations[
            "AI確率"
        ] * 100
    ).round(4)
    display_combinations = (
        display_combinations.rename(
            columns={
                "combination": "組番",
                "AI確率": "AI確率%",
            }
        )
    )
    st.dataframe(
        display_combinations,
        use_container_width=True,
        hide_index=True,
    )

    if isinstance(
        rider_prediction,
        pd.DataFrame,
    ):
        st.markdown("#### 選手別の着順確率")
        display_riders = (
            rider_prediction.copy()
        )

        for column in (
            "1着確率",
            "2着確率",
            "3着確率",
            "3着内確率",
        ):
            display_riders[
                f"{column}%"
            ] = (
                display_riders[
                    column
                ] * 100
            ).round(2)
            display_riders = (
                display_riders.drop(
                    columns=[column]
                )
            )

        st.dataframe(
            display_riders,
            use_container_width=True,
            hide_index=True,
        )

    csv_data = (
        combination_prediction.to_csv(
            index=False
        ).encode("utf-8-sig")
    )
    st.download_button(
        "独立予測CSVをダウンロード",
        data=csv_data,
        file_name=(
            f"{race_date_text}_"
            f"{venue}_"
            f"{race_number}R_"
            "odds_independent_prediction.csv"
        ),
        mime="text/csv",
    )

    coverage = prediction_metadata.get(
        "feature_coverage",
        {},
    )

    if coverage:
        st.caption(
            "今回の特徴量カバレッジ："
            f"選手属性 {coverage.get('profile_rider_count', 0)}/"
            f"{coverage.get('rider_count', 0)}人、"
            f"過去成績あり {coverage.get('recent_history_rider_count', 0)}/"
            f"{coverage.get('rider_count', 0)}人、"
            "競輪場特性 "
            + (
                "取得済み"
                if coverage.get(
                    "venue_characteristics_known"
                )
                else "未取得"
            )
            + "、並び信頼度 "
            f"{coverage.get('lineup_confidence', 0):.2f}"
        )


st.divider()
st.subheader("3. AI予測の客観評価")

with st.expander(
    "Galaxyの予測をGoogle Driveから取り込む",
    expanded=False,
):
    (
        drive_api_tab,
        local_folder_tab,
    ) = st.tabs(
        [
            "Driveへ直接接続（推奨）",
            "Mac内フォルダ",
        ]
    )

    with drive_api_tab:
        st.caption(
            "Google Driveデスクトップ版は"
            "不要です。初回だけGoogle Cloudの"
            "OAuthクライアントJSONと、Driveの"
            "閲覧許可が必要です。認証情報は"
            "このMac内だけに保存されます。"
        )
        status = (
            google_drive_connection_status()
        )
        oauth_client_file = st.file_uploader(
            "OAuthクライアントJSON",
            type=["json"],
            key=(
                "google_drive_oauth_client"
            ),
            help=(
                "Google Cloudでアプリの種類を"
                "「デスクトップアプリ」にして"
                "ダウンロードしたJSONです。"
            ),
        )

        if st.button(
            "OAuth設定をMacへ保存",
            key=(
                "save_google_drive_oauth"
            ),
            disabled=(
                oauth_client_file is None
            ),
        ):
            try:
                save_google_drive_client_config(
                    oauth_client_file.getvalue()
                )
                status = (
                    google_drive_connection_status()
                )
                st.success(
                    "OAuth設定を保存しました。"
                    "次にGoogleアカウントへ"
                    "接続してください。"
                )
            except Exception as exception:
                st.error(
                    "OAuth設定エラー: "
                    f"{type(exception).__name__}: "
                    f"{exception}"
                )

        if status["client_configured"]:
            st.success(
                "OAuth設定：登録済み"
            )
        else:
            st.info(
                "OAuth設定：未登録"
            )

        (
            connect_column,
            disconnect_column,
        ) = st.columns(2)

        with connect_column:
            if st.button(
                "Googleアカウントへ接続",
                key=(
                    "connect_google_drive"
                ),
                disabled=not status[
                    "client_configured"
                ],
                use_container_width=True,
            ):
                try:
                    connect_google_drive()
                    status = (
                        google_drive_connection_status()
                    )
                    st.success(
                        "Google Driveへ"
                        "接続しました。"
                    )
                except Exception as exception:
                    st.error(
                        "Google Drive接続エラー: "
                        f"{type(exception).__name__}: "
                        f"{exception}"
                    )

        with disconnect_column:
            if st.button(
                "Google接続を解除",
                key=(
                    "disconnect_google_drive"
                ),
                disabled=not status[
                    "authorized"
                ],
                use_container_width=True,
            ):
                disconnect_google_drive()
                status = (
                    google_drive_connection_status()
                )
                st.info(
                    "このMacに保存した"
                    "Google認証を削除しました。"
                )

        if status["authorized"]:
            st.success(
                "Google Drive：接続済み"
            )
        else:
            st.info(
                "Google Drive：未接続"
            )

        drive_folder_value = st.text_input(
            "KeirinAIフォルダのURL"
            "（通常は空欄でOK）",
            placeholder=(
                "https://drive.google.com/"
                "drive/folders/..."
            ),
            key=(
                "google_drive_folder_value"
            ),
            help=(
                "KeirinAIフォルダが複数ある"
                "場合だけURLを貼り付けます。"
                "1個なら自動検出します。"
            ),
        )

        if st.button(
            "Driveから予測を取り込む",
            key=(
                "import_google_drive_predictions"
            ),
            disabled=not status["authorized"],
            type="primary",
            use_container_width=True,
        ):
            try:
                mobile_import_result = (
                    import_google_drive_predictions(
                        drive_folder_value
                    )
                )
                st.session_state[
                    "android_prediction_import_result"
                ] = mobile_import_result
                st.success(
                    "Driveのスマホ予測を"
                    "取り込みました。"
                    f" 対象 "
                    f"{mobile_import_result['remote_file_count']}件、"
                    f"新規 "
                    f"{mobile_import_result['imported_count']}件、"
                    f"重複 "
                    f"{mobile_import_result['duplicate_count']}件、"
                    f"失敗 "
                    f"{mobile_import_result['failed_count']}件。"
                )
            except Exception as exception:
                st.error(
                    "Drive予測取込エラー: "
                    f"{type(exception).__name__}: "
                    f"{exception}"
                )

        st.markdown(
            "[Google公式：Drive APIの"
            "初期設定手順]"
            "(https://developers.google.com/"
            "workspace/drive/api/quickstart/"
            "python?hl=ja)"
        )

    with local_folder_tab:
        drive_directories = (
            discover_google_drive_directories()
        )
        default_drive_directory = (
            str(drive_directories[0])
            if len(drive_directories) == 1
            else ""
        )
        mobile_prediction_directory = (
            st.text_input(
                "Mac内のKeirinAIフォルダ",
                value=default_drive_directory,
                placeholder=(
                    "/Users/.../Downloads/"
                    "KeirinAI"
                ),
                key=(
                    "android_prediction_directory"
                ),
            )
        )

        if len(drive_directories) > 1:
            st.info(
                "候補が複数あります。取り込む"
                "KeirinAIフォルダを指定してください。\n\n"
                + "\n".join(
                    f"- `{path}`"
                    for path in drive_directories
                )
            )
        elif not drive_directories:
            st.caption(
                "Driveから手動ダウンロード"
                "した場合は、解凍後の"
                "KeirinAIフォルダのパスを"
                "貼り付けてください。"
            )

        if st.button(
            "Mac内フォルダから取り込む",
            key="import_android_predictions",
        ):
            if not mobile_prediction_directory:
                st.error(
                    "KeirinAIフォルダを"
                    "指定してください。"
                )
            else:
                try:
                    mobile_import_result = (
                        import_android_predictions(
                            Path(
                                mobile_prediction_directory
                            )
                        )
                    )
                    st.session_state[
                        "android_prediction_import_result"
                    ] = mobile_import_result
                    st.success(
                        "スマホ予測を"
                        "取り込みました。"
                        f" 新規 "
                        f"{mobile_import_result['imported_count']}件、"
                        f"重複 "
                        f"{mobile_import_result['duplicate_count']}件、"
                        f"失敗 "
                        f"{mobile_import_result['failed_count']}件。"
                    )
                except Exception as exception:
                    st.error(
                        "スマホ予測取込エラー: "
                        f"{type(exception).__name__}: "
                        f"{exception}"
                    )

    mobile_import_result = (
        st.session_state.get(
            "android_prediction_import_result"
        )
    )

    if mobile_import_result:
        if mobile_import_result["records"]:
            st.dataframe(
                pd.DataFrame(
                    mobile_import_result[
                        "records"
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )

        if mobile_import_result["failures"]:
            st.warning(
                "形式不正などで取り込めない"
                "ファイルがあります。"
            )
            st.dataframe(
                pd.DataFrame(
                    mobile_import_result[
                        "failures"
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )

st.caption(
    "予測時点の全組番順位をSQLiteへ固定保存し、"
    "学習データ収集で結果が登録された時点で"
    "的中組番の順位を自動照合します。"
)

st.info(
    "正式評価は、対象日がモデル学習終了日より後、"
    "発走前（発走時刻が未取得なら開催日以前）に予測、"
    "結果未登録、かつ同一レースの"
    "初回正式予測である場合だけです。条件外は"
    "参考記録として残し、的中率へ含めません。"
)

st.caption(
    "発走時刻を取得できたレースは時刻まで比較します。"
    "発走時刻がない旧データだけ開催日単位へフォールバックし、"
    "予測日時そのものは常に記録します。"
)

if st.button(
    "結果との照合を更新",
    key="sync_independent_evaluation",
):
    synchronized_count = (
        sync_independent_prediction_results()
    )
    st.success(
        f"{synchronized_count}レースの"
        "照合状態を更新しました。"
    )

evaluation_summary = (
    get_independent_evaluation_summary()
)

(
    evaluation_count_col,
    pending_count_col,
    reference_count_col,
    review_count_col,
) = st.columns(4)

with evaluation_count_col:
    st.metric(
        "正式評価済み",
        evaluation_summary[
            "official_count"
        ],
    )

with pending_count_col:
    st.metric(
        "正式結果待ち",
        evaluation_summary[
            "pending_count"
        ],
    )

with reference_count_col:
    st.metric(
        "参考記録",
        evaluation_summary[
            "reference_count"
        ],
    )

with review_count_col:
    st.metric(
        "正式要確認",
        evaluation_summary[
            "review_count"
        ],
    )

(
    top1_col,
    top5_col,
    top10_col,
    top20_col,
    top30_col,
) = st.columns(5)

for column, label, key in (
    (
        top1_col,
        "Top1的中率",
        "top1_hit_rate",
    ),
    (
        top5_col,
        "Top5的中率",
        "top5_hit_rate",
    ),
    (
        top10_col,
        "Top10的中率",
        "top10_hit_rate",
    ),
    (
        top20_col,
        "Top20的中率",
        "top20_hit_rate",
    ),
    (
        top30_col,
        "Top30的中率",
        "top30_hit_rate",
    ),
):
    with column:
        st.metric(
            label,
            (
                f"{evaluation_summary[key] * 100:.2f}%"
            ),
        )

average_rank_col, maximum_payout_col = (
    st.columns(2)
)

with average_rank_col:
    st.metric(
        "的中組番の平均AI順位",
        (
            f"{evaluation_summary['mean_winner_rank']:.2f}位"
            if evaluation_summary[
                "official_count"
            ]
            else "-"
        ),
    )

with maximum_payout_col:
    st.metric(
        "正式評価の最高払戻",
        (
            f"{evaluation_summary['maximum_payout']:,}円"
            if evaluation_summary[
                "maximum_payout"
            ]
            else "-"
        ),
    )

evaluation_segments = (
    get_independent_evaluation_segments()
)

if evaluation_segments:
    with st.expander(
        "正式評価の条件別成績を表示"
    ):
        segment_dimensions = list(
            dict.fromkeys(
                str(row["dimension"])
                for row
                in evaluation_segments
            )
        )
        selected_official_dimension = (
            st.selectbox(
                "集計条件",
                options=segment_dimensions,
                key=(
                    "official_segment_dimension"
                ),
            )
        )
        official_rows = [
            row
            for row in evaluation_segments
            if row["dimension"]
            == selected_official_dimension
        ]
        official_frame = pd.DataFrame(
            official_rows
        ).rename(
            columns={
                "condition": "条件",
                "race_count": "レース数",
                "top1_hit_rate": "Top1",
                "top5_hit_rate": "Top5",
                "top10_hit_rate": "Top10",
                "top30_hit_rate": "Top30",
                "mean_winner_rank": (
                    "平均的中順位"
                ),
                "race_log_loss": "LogLoss",
            }
        ).drop(
            columns=["dimension"],
            errors="ignore",
        )
        st.dataframe(
            official_frame,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Top1": st.column_config.NumberColumn(
                    format="%.2f"
                ),
                "Top5": st.column_config.NumberColumn(
                    format="%.2f"
                ),
                "Top10": st.column_config.NumberColumn(
                    format="%.2f"
                ),
                "Top30": st.column_config.NumberColumn(
                    format="%.2f"
                ),
                "平均的中順位": (
                    st.column_config.NumberColumn(
                        format="%.2f"
                    )
                ),
                "LogLoss": (
                    st.column_config.NumberColumn(
                        format="%.4f"
                    )
                ),
            },
        )
        st.caption(
            "Top各列は0〜1で表示します。"
            "レース数が少ない条件は参考値です。"
        )

recent_evaluations = (
    get_recent_independent_evaluations(
        limit=100
    )
)

if recent_evaluations:
    evaluation_rows = []

    for evaluation in recent_evaluations:
        probability = evaluation.get(
            "winning_probability"
        )
        evaluation_rows.append(
            {
                "_run_id": evaluation[
                    "run_id"
                ],
                "開催日": evaluation[
                    "race_date"
                ],
                "競輪場": evaluation[
                    "venue"
                ],
                "R": evaluation[
                    "race_number"
                ],
                "区分": (
                    "正式"
                    if evaluation[
                        "evaluation_eligible"
                    ]
                    else "参考"
                ),
                "状態": evaluation[
                    "result_status"
                ],
                "的中組番": (
                    evaluation.get(
                        "winning_combination"
                    )
                    or ""
                ),
                "AI順位": (
                    evaluation.get(
                        "winning_rank"
                    )
                    or ""
                ),
                "AI確率%": (
                    round(
                        float(probability)
                        * 100,
                        4,
                    )
                    if probability
                    is not None
                    else ""
                ),
                "払戻": (
                    evaluation.get(
                        "payout_per_100"
                    )
                    or ""
                ),
                "予測日時": evaluation[
                    "predicted_at"
                ],
                "学習終了日": (
                    evaluation.get(
                        "training_end_date"
                    )
                    or ""
                ),
                "学習締切": (
                    evaluation.get(
                        "training_cutoff_date"
                    )
                    or ""
                ),
                "参考理由": (
                    evaluation.get(
                        "eligibility_reason"
                    )
                    or ""
                ),
            }
        )

    st.markdown("#### 予測・自己評価履歴")
    st.caption(
        "見たいレースのR欄をクリックすると、"
        "予測時に保存した着順確率を表示します。"
    )
    (
        date_header,
        venue_header,
        race_header,
        category_header,
        status_header,
        winner_header,
        rank_header,
        probability_header,
        payout_header,
    ) = st.columns(
        [
            1.05,
            1.15,
            0.6,
            0.6,
            0.75,
            0.85,
            0.65,
            0.8,
            0.85,
        ]
    )

    for column, label in (
        (date_header, "開催日"),
        (venue_header, "競輪場"),
        (race_header, "R"),
        (category_header, "区分"),
        (status_header, "状態"),
        (winner_header, "的中組番"),
        (rank_header, "AI順位"),
        (probability_header, "AI確率%"),
        (payout_header, "払戻"),
    ):
        column.markdown(f"**{label}**")

    selected_run_id = ""

    for row_index, row in enumerate(
        evaluation_rows
    ):
        with st.container(border=True):
            (
                date_column,
                venue_column,
                race_column,
                category_column,
                status_column,
                winner_column,
                rank_column,
                probability_column,
                payout_column,
            ) = st.columns(
                [
                    1.05,
                    1.15,
                    0.6,
                    0.6,
                    0.75,
                    0.85,
                    0.65,
                    0.8,
                    0.85,
                ]
            )
            date_column.write(
                row["開催日"]
            )
            venue_column.write(
                row["競輪場"]
            )

            with race_column:
                if st.button(
                    f"🔗 {row['R']}R",
                    key=(
                        "open_prediction_detail_"
                        f"{row_index}_"
                        f"{row['_run_id']}"
                    ),
                    type="tertiary",
                    help=(
                        "保存済み着順確率を"
                        "ポップアップ表示"
                    ),
                ):
                    selected_run_id = str(
                        row["_run_id"]
                    )

            category_column.write(
                row["区分"]
            )
            status_column.write(
                row["状態"]
            )
            winner_column.write(
                row["的中組番"] or "-"
            )
            rank_column.write(
                (
                    f"{row['AI順位']}位"
                    if row["AI順位"] != ""
                    else "-"
                )
            )
            probability_column.write(
                (
                    row["AI確率%"]
                    if row["AI確率%"] != ""
                    else "-"
                )
            )
            payout_column.write(
                (
                    f"{int(row['払戻']):,}円"
                    if row["払戻"] != ""
                    else "-"
                )
            )
            detail_caption = (
                f"予測日時: {row['予測日時']} / "
                f"学習終了日: "
                f"{row['学習終了日'] or '-'} / "
                f"学習締切: "
                f"{row['学習締切'] or '-'}"
            )

            if row["参考理由"]:
                detail_caption += (
                    " / 参考理由: "
                    + str(
                        row["参考理由"]
                    )
                )

            st.caption(detail_caption)

    if selected_run_id:
        show_prediction_detail(
            selected_run_id
        )
else:
    st.caption(
        "予測履歴はまだありません。"
    )

hole_hits = get_independent_hole_hits(
    limit=50
)

if hole_hits:
    hole_rows = []

    for hit in hole_hits:
        probability = float(
            hit[
                "winning_probability"
            ]
            or 0.0
        )
        hole_rows.append(
            {
                "開催日": hit["race_date"],
                "競輪場": hit["venue"],
                "R": hit["race_number"],
                "的中組番": hit[
                    "winning_combination"
                ],
                "AI順位": hit[
                    "winning_rank"
                ],
                "AI確率%": round(
                    probability * 100,
                    4,
                ),
                "払戻": (
                    hit["payout_per_100"]
                    or ""
                ),
            }
        )

    st.markdown(
        "#### 穴目的中一覧（正式評価・11位以下）"
    )
    st.dataframe(
        hole_rows,
        use_container_width=True,
        hide_index=True,
    )
