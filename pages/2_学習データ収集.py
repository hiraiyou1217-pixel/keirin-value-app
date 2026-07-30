from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import streamlit as st
from history_import_manager import (
    load_latest_job,
    start_history_import,
)
from race_url_utils import (
    infer_racecard_url,
    normalize_racecard_url,
)
from current_race_snapshot import (
    load_current_race_snapshot,
)

from result_auto_import import (
    import_unfinished_results,
)
from learning_database import (
    DATABASE_PATH,
    get_database_summary,
    get_races_without_url,
    get_recent_races,
    initialize_database,
    save_race_result,
    update_race_url,
    save_race_snapshot,
)


st.set_page_config(
    page_title="学習データ収集",
    page_icon="🧠",
    layout="wide",
)

initialize_database()

st.title("🧠 学習データ収集")

st.caption(
    "取得済みの出走表・オッズ・並びを、"
    "機械学習用SQLiteデータベースへ保存します。"
    "オッズ非表示時は独立AI用データとして"
    "安全に保存します。"
)

summary = get_database_summary()

(
    summary_col1,
    summary_col2,
    summary_col3,
    summary_col4,
    summary_col5,
    summary_col6,
) = (
    st.columns(6)
)

with summary_col1:
    st.metric(
        "保存レース数",
        f"{summary['race_count']:,}",
    )

with summary_col2:
    st.metric(
        "結果確定レース",
        f"{summary['completed_count']:,}",
    )

with summary_col3:
    st.metric(
        "要確認レース",
        f"{summary['review_count']:,}",
    )

with summary_col4:
    st.metric(
        "オッズなし",
        f"{summary['independent_only_count']:,}",
    )

with summary_col5:
    st.metric(
        "オッズ行数",
        f"{summary['odds_count']:,}",
    )

with summary_col6:
    st.metric(
        "選手行数",
        f"{summary['rider_count']:,}",
    )

st.info(
    f"保存先：{DATABASE_PATH}"
)


st.divider()
st.subheader("過去レース一括インポート")

st.caption(
    "WINTICKETの日付別結果一覧から"
    "全開催場・全レースを発見し、"
    "出走表・選手・並び・3連単全オッズ・"
    "結果を分離Workerで収集します。"
    "深夜などオッズ非表示時は不完全な"
    "オッズを破棄し、オッズ非依存AI用の"
    "出走表・並び・結果だけを保存します。"
)

yesterday = date.today() - timedelta(
    days=1
)
default_start_date = yesterday - timedelta(
    days=6
)

with st.form(
    "history_import_form",
    clear_on_submit=False,
    enter_to_submit=False,
):
    (
        history_col1,
        history_col2,
        history_col3,
    ) = st.columns(3)

    with history_col1:
        history_start_date = st.date_input(
            "開始日",
            value=default_start_date,
            max_value=yesterday,
            key="history_start_date",
        )

    with history_col2:
        history_end_date = st.date_input(
            "終了日",
            value=yesterday,
            max_value=yesterday,
            key="history_end_date",
        )

    with history_col3:
        history_maximum = st.number_input(
            "最大取得数",
            min_value=1,
            max_value=1000,
            value=30,
            step=10,
        )

    start_history = st.form_submit_button(
        "過去レース収集を開始",
        type="primary",
    )

if start_history:
    try:
        started_job = start_history_import(
            start_date=history_start_date,
            end_date=history_end_date,
            maximum_races=int(
                history_maximum
            ),
        )
        st.session_state[
            "history_import_job_id"
        ] = started_job["job_id"]
        st.success(
            "分離Workerを起動しました。"
            "このページを閉じても処理は継続します。"
        )
    except Exception as exc:
        st.error(
            f"{type(exc).__name__}: {exc}"
        )


def _history_rows(
    details: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "開催日": detail.get(
                "race_date",
                "",
            ),
            "競輪場": detail.get(
                "venue",
                "",
            ),
            "R": (
                detail.get(
                    "race_number",
                    "",
                )
                or ""
            ),
            "状態": detail.get(
                "status",
                "",
            ),
            "保存用途": (
                {
                    "independent": (
                        "オッズ非依存AI"
                    ),
                    "full": "全オッズ",
                }.get(
                    str(
                        detail.get(
                            "data_scope",
                            "",
                        )
                    ),
                    "",
                )
            ),
            "3連単": detail.get(
                "winning_combination",
                "",
            ),
            "払戻": (
                detail.get(
                    "payout_per_100",
                    "",
                )
                or ""
            ),
            "メッセージ": detail.get(
                "message",
                "",
            ),
        }
        for detail in details
    ]


@st.fragment(run_every="3s")
def render_history_import_progress() -> None:
    job = load_latest_job()

    if not job:
        st.info(
            "過去レースWorkerは"
            "まだ実行されていません。"
        )
        return

    status_labels = {
        "running": "実行中",
        "completed": "完了",
        "failed": "失敗終了",
        "stopped": "異常終了",
    }
    status = str(
        job.get("status", "")
    )
    processed = int(
        job.get("processed", 0)
    )
    total = int(
        job.get("total", 0)
    )
    progress_value = (
        min(processed / total, 1.0)
        if total > 0
        else 0.0
    )

    st.write(
        f"Worker状態："
        f"{status_labels.get(status, status)}"
    )
    st.progress(
        progress_value,
        text=str(
            job.get("message", "")
        ),
    )

    (
        job_col1,
        job_col2,
        job_col3,
        job_col4,
        job_col5,
    ) = st.columns(5)

    with job_col1:
        st.metric(
            "処理",
            f"{processed}/{total}",
        )

    with job_col2:
        st.metric(
            "成功",
            int(
                job.get(
                    "success_count",
                    0,
                )
            ),
        )

    with job_col3:
        st.metric(
            "失敗",
            int(
                job.get(
                    "failure_count",
                    0,
                )
            ),
        )

    with job_col4:
        st.metric(
            "要確認",
            int(
                job.get(
                    "review_count",
                    0,
                )
            ),
        )

    with job_col5:
        st.metric(
            "オッズなし保存",
            int(
                job.get(
                    "independent_count",
                    0,
                )
            ),
        )

    successes = _history_rows(
        list(job.get("successes", []))
    )
    failures = _history_rows(
        list(job.get("failures", []))
    )
    reviews = _history_rows(
        list(job.get("reviews", []))
    )

    success_tab, failure_tab, review_tab = (
        st.tabs(
            [
                "成功一覧",
                "失敗一覧",
                "要確認一覧",
            ]
        )
    )

    with success_tab:
        if successes:
            st.dataframe(
                successes,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption(
                "成功レースはまだありません。"
            )

    with failure_tab:
        if failures:
            st.dataframe(
                failures,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption(
                "失敗レースはありません。"
            )

    with review_tab:
        if reviews:
            st.dataframe(
                reviews,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption(
                "要確認レースはありません。"
            )


render_history_import_progress()


st.divider()
st.subheader("現在取得中のレースを保存")

snapshot = load_current_race_snapshot()

odds_rows: list[dict[str, Any]] = (
    st.session_state.get("odds", [])
    or st.session_state.get(
        "odds_rows",
        [],
    )
    or snapshot.get(
        "odds_rows",
        [],
    )
)

riders: list[dict[str, Any]] = (
    st.session_state.get(
        "rider_data",
        [],
    )
    or snapshot.get(
        "riders",
        [],
    )
)

lineup_groups: list[list[int]] = (
    st.session_state.get(
        "lineup_groups",
        [],
    )
    or snapshot.get(
        "lineup_groups",
        [],
    )
)

odds_logs: list[str] = (
    st.session_state.get(
        "odds_logs",
        [],
    )
    or snapshot.get(
        "odds_logs",
        [],
    )
)

odds_complete = any(
    str(log).strip()
    == "オッズデータ完全性: OK"
    for log in odds_logs
)

default_date = st.session_state.get(
    "selected_date",
    date.today(),
)

if hasattr(default_date, "isoformat"):
    default_date_text = (
        default_date.isoformat()
    )
else:
    default_date_text = str(default_date)

default_venue = str(
    st.session_state.get(
        "venue",
        st.session_state.get(
            "selected_venue",
            "",
        ),
    )
)

default_race_number = int(
    st.session_state.get(
        "race_number",
        st.session_state.get(
            "selected_race_number",
            1,
        ),
    )
)

session_race_url = st.session_state.get(
    "racecard_url",
    st.session_state.get(
        "selected_race_url",
        "",
    ),
)

default_race_url = infer_racecard_url(
    explicit_url=(
        session_race_url
        or snapshot.get(
            "race_url",
            "",
        )
    ),
    logs=(
        odds_logs
        or snapshot.get(
            "odds_logs",
            [],
        )
    ),
)

default_race_title = str(
    st.session_state.get(
        "race_title",
        "",
    )
)

with st.form(
    "save_learning_snapshot_form",
    clear_on_submit=False,
    enter_to_submit=False,
):
    input_col1, input_col2, input_col3 = (
        st.columns(3)
    )

    with input_col1:
        race_date = st.text_input(
            "開催日",
            value=default_date_text,
            placeholder="2026-07-29",
        )

    with input_col2:
        venue = st.text_input(
            "競輪場",
            value=default_venue,
            placeholder="和歌山",
        )

    with input_col3:
        race_number = st.number_input(
            "レース番号",
            min_value=1,
            max_value=12,
            value=default_race_number,
            step=1,
        )

    race_title = st.text_input(
        "レース名",
        value=default_race_title,
    )

    race_url = st.text_input(
        "出走表URL",
        value=default_race_url,
    )

    save_snapshot = st.form_submit_button(
        "現在の取得データを保存",
        type="primary",
    )

if save_snapshot:
    if not odds_rows:
        st.error(
            "オッズデータがありません。"
            "先にメイン画面でオッズを取得してください。"
        )

    elif not riders:
        st.error(
            "出走表データがありません。"
            "先に選手データを取得してください。"
        )

    elif not odds_complete:
        st.error(
            "オッズデータ完全性がOKではありません。"
            "不完全なオッズは学習用に保存しません。"
        )

    elif len(odds_rows) not in (
        210,
        336,
        504,
    ):
        st.error(
            "オッズ件数が理論組番数と一致しません。"
            f"現在は{len(odds_rows)}件です。"
        )

    elif not race_date.strip():
        st.error(
            "開催日を入力してください。"
        )

    elif not venue.strip():
        st.error(
            "競輪場を入力してください。"
        )

    else:
        race_id = save_race_snapshot(
            race_date=race_date.strip(),
            venue=venue.strip(),
            race_number=int(race_number),
            race_url=infer_racecard_url(
                explicit_url=race_url,
                logs=odds_logs,
            ),
            race_title=race_title.strip(),
            riders=riders,
            odds_rows=odds_rows,
            lineup_groups=lineup_groups,
            odds_complete=True,
        )

        st.success(
            "学習データを保存しました。"
        )

        st.code(race_id)



st.divider()
st.subheader("出走表URLが未登録のレース")

races_without_url = get_races_without_url(
    limit=200
)

if not races_without_url:
    st.success(
        "URL未登録のレースはありません。"
    )
else:
    st.warning(
        f"{len(races_without_url)}レースで"
        "出走表URLが未登録です。"
    )

    missing_url_options = {
        (
            f"{race['race_date']} "
            f"{race['venue']} "
            f"{race['race_number']}R "
            f"{race['race_title'] or ''}"
        ): race["race_id"]
        for race in races_without_url
    }

    with st.form(
        "repair_missing_race_url_form",
        clear_on_submit=False,
        enter_to_submit=False,
    ):
        selected_missing_label = (
            st.selectbox(
                "URLを登録するレース",
                options=list(
                    missing_url_options.keys()
                ),
            )
        )

        replacement_race_url = (
            st.text_input(
                "WINTICKET出走表URL",
                placeholder=(
                    "https://www.winticket.jp/"
                    "keirin/.../racecard/.../.../..."
                ),
            )
        )

        save_replacement_url = (
            st.form_submit_button(
                "出走表URLを登録",
                type="primary",
            )
        )

    if save_replacement_url:
        normalized_replacement_url = (
            normalize_racecard_url(
                replacement_race_url
            )
        )

        if (
            not normalized_replacement_url
            or "/racecard/"
            not in normalized_replacement_url
        ):
            st.error(
                "有効なWINTICKETの"
                "出走表URLを入力してください。"
            )
        else:
            updated = update_race_url(
                race_id=missing_url_options[
                    selected_missing_label
                ],
                race_url=(
                    normalized_replacement_url
                ),
            )

            if updated:
                st.success(
                    "出走表URLを登録しました。"
                    "ページを再読み込みすると"
                    "一覧から消えます。"
                )
            else:
                st.error(
                    "URLを登録できませんでした。"
                )


st.divider()
st.subheader("未確定レースの結果を自動取得")

st.caption(
    "結果未登録のレースを順番に確認し、"
    "確定済みの着順と3連単払戻を"
    "SQLiteへ登録します。"
)

with st.form(
    "automatic_result_import_form",
    clear_on_submit=False,
    enter_to_submit=False,
):
    maximum_result_checks = st.number_input(
        "1回に確認する最大レース数",
        min_value=1,
        max_value=200,
        value=30,
        step=10,
    )

    automatic_result_import = (
        st.form_submit_button(
            "未確定レースの結果を一括取得",
            type="primary",
        )
    )

if automatic_result_import:
    try:
        with st.spinner(
            "未確定レースの結果を"
            "確認しています。"
        ):
            import_result = (
                import_unfinished_results(
                    maximum_races=int(
                        maximum_result_checks
                    )
                )
            )

        st.session_state[
            "automatic_result_import"
        ] = import_result

        st.success(
            "結果確認が完了しました。"
        )

    except Exception as exc:
        st.error(
            f"{type(exc).__name__}: {exc}"
        )

import_result = st.session_state.get(
    "automatic_result_import"
)

if import_result:
    (
        result_col1,
        result_col2,
        result_col3,
        result_col4,
        result_col5,
    ) = (
        st.columns(5)
    )

    with result_col1:
        st.metric(
            "確認",
            import_result["checked"],
        )

    with result_col2:
        st.metric(
            "登録",
            import_result["registered"],
        )

    with result_col3:
        st.metric(
            "未確定",
            import_result["unsettled"],
        )

    with result_col4:
        st.metric(
            "要確認",
            import_result.get(
                "review",
                0,
            ),
        )

    with result_col5:
        st.metric(
            "取得失敗",
            import_result["failed"],
        )

    detail_rows = []

    for detail in import_result[
        "details"
    ]:
        detail_rows.append(
            {
                "開催日": detail[
                    "race_date"
                ],
                "競輪場": detail[
                    "venue"
                ],
                "R": detail[
                    "race_number"
                ],
                "状態": detail[
                    "status"
                ],
                "確定組番": detail[
                    "winning_combination"
                ],
                "払戻": detail[
                    "payout_per_100"
                ]
                or "",
                "メッセージ": detail[
                    "message"
                ],
            }
        )

    st.dataframe(
        detail_rows,
        use_container_width=True,
        hide_index=True,
    )


st.divider()
st.subheader("レース結果を登録")

recent_races = get_recent_races(
    limit=100
)

unfinished_races = [
    race
    for race in recent_races
    if race["result_status"] != "確定"
]

if not unfinished_races:
    st.info(
        "結果未登録のレースはありません。"
    )

else:
    race_options = {
        (
            f"{race['race_date']} "
            f"{race['venue']} "
            f"{race['race_number']}R "
            f"{race['race_title'] or ''}"
        ): race["race_id"]
        for race in unfinished_races
    }

    with st.form(
        "register_race_result_form",
        clear_on_submit=False,
        enter_to_submit=False,
    ):
        selected_label = st.selectbox(
            "結果を登録するレース",
            options=list(
                race_options.keys()
            ),
        )

        result_col1, result_col2, result_col3 = (
            st.columns(3)
        )

        with result_col1:
            first_place = st.number_input(
                "1着車番",
                min_value=1,
                max_value=9,
                value=1,
                step=1,
            )

        with result_col2:
            second_place = st.number_input(
                "2着車番",
                min_value=1,
                max_value=9,
                value=2,
                step=1,
            )

        with result_col3:
            third_place = st.number_input(
                "3着車番",
                min_value=1,
                max_value=9,
                value=3,
                step=1,
            )

        payout_per_100 = st.number_input(
            "3連単確定払戻（100円あたり）",
            min_value=0,
            value=0,
            step=10,
            help=(
                "未確認の場合は0のままでも保存できます。"
            ),
        )

        register_result = (
            st.form_submit_button(
                "結果を登録",
                type="primary",
            )
        )

    if register_result:
        places = {
            int(first_place),
            int(second_place),
            int(third_place),
        }

        if len(places) != 3:
            st.error(
                "1着・2着・3着には"
                "異なる車番を指定してください。"
            )

        else:
            save_race_result(
                race_id=race_options[
                    selected_label
                ],
                first_place=int(
                    first_place
                ),
                second_place=int(
                    second_place
                ),
                third_place=int(
                    third_place
                ),
                payout_per_100=(
                    int(payout_per_100)
                    if payout_per_100 > 0
                    else None
                ),
            )

            st.success(
                "レース結果を登録しました。"
            )

st.divider()
st.subheader("最近保存したレース")

recent_races = get_recent_races(
    limit=50
)

if recent_races:
    display_rows = []

    for race in recent_races:
        display_rows.append(
            {
                "開催日": race["race_date"],
                "競輪場": race["venue"],
                "R": race["race_number"],
                "レース名": race["race_title"],
                "車数": race["rider_count"],
                "オッズ完全": (
                    "OK"
                    if race["odds_complete"]
                    else "非依存AI用"
                ),
                "結果": race["result_status"],
                "要確認理由": (
                    race.get(
                        "review_reason",
                        "",
                    )
                    or ""
                ),
                "確定組番": (
                    race["winning_combination"]
                    or ""
                ),
                "払戻": (
                    race["payout_per_100"]
                    or ""
                ),
            }
        )

    st.dataframe(
        display_rows,
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info(
        "まだ学習データはありません。"
    )
