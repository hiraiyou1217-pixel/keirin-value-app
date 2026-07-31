from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

from race_metadata import (
    extract_race_conditions_from_riders,
)

DATABASE_PATH = Path(
    os.environ.get(
        "KEIRIN_LEARNING_DATABASE",
        str(
            Path(__file__).resolve().parent
            / "data"
            / "keirin_learning.db"
        ),
    )
)

VENUE_NAME_ALIASES = {
    "iwakidaira": "いわき平",
    "iwakitaira": "いわき平",
}


def get_connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=30,
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA journal_mode=WAL"
    )
    connection.execute(
        "PRAGMA foreign_keys=ON"
    )

    return connection


def normalize_venue_name(value: Any) -> str:
    venue = re.sub(
        r"\s+",
        "",
        str(value or "").strip(),
    )

    for suffix in ("競輪場", "競輪"):
        if venue.endswith(suffix):
            venue = venue[: -len(suffix)]
            break

    return VENUE_NAME_ALIASES.get(
        venue.lower(),
        venue,
    )


def canonical_venue_display(
    value: Any,
) -> str:
    original = str(value or "").strip()
    compact = re.sub(
        r"\s+",
        "",
        original,
    )

    for suffix in ("競輪場", "競輪"):
        if compact.endswith(suffix):
            compact = compact[: -len(suffix)]
            break

    alias = VENUE_NAME_ALIASES.get(
        compact.lower()
    )

    if alias:
        return f"{alias}競輪"

    return original


def canonical_race_title(
    value: Any,
) -> str:
    title = str(value or "").strip()

    for slug, venue in (
        VENUE_NAME_ALIASES.items()
    ):
        title = re.sub(
            (
                rf"^{re.escape(slug)}"
                r"(?=競輪場?|[\s\d]|$)"
            ),
            venue,
            title,
            count=1,
            flags=re.IGNORECASE,
        )

    return title


def build_race_key(
    race_date: str,
    venue: str,
    race_number: int,
) -> str:
    normalized_date = str(race_date).strip()
    normalized_venue = normalize_venue_name(
        venue
    )

    if not normalized_date:
        raise ValueError(
            "開催日が空です。"
        )

    if not normalized_venue:
        raise ValueError(
            "競輪場が空です。"
        )

    number = int(race_number)

    if not 1 <= number <= 12:
        raise ValueError(
            "レース番号は1〜12で指定してください。"
        )

    return (
        f"{normalized_date}|"
        f"{normalized_venue}|"
        f"{number:02d}"
    )


def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    columns = {
        str(row["name"])
        for row in connection.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()
    }

    if column_name not in columns:
        connection.execute(
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN {column_name} "
            f"{definition}"
        )


def _backfill_race_keys(
    connection: sqlite3.Connection,
    *,
    force: bool = False,
) -> None:
    if force:
        rows = connection.execute(
            """
            SELECT
                race_id,
                race_date,
                venue,
                race_number
            FROM races
            """
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT
                race_id,
                race_date,
                venue,
                race_number
            FROM races
            WHERE
                race_key IS NULL
                OR TRIM(race_key) = ''
            """
        ).fetchall()

    for row in rows:
        connection.execute(
            """
            UPDATE races
            SET
                race_key = ?,
                venue = ?
            WHERE race_id = ?
            """,
            (
                build_race_key(
                    str(row["race_date"]),
                    str(row["venue"]),
                    int(row["race_number"]),
                ),
                canonical_venue_display(
                    row["venue"]
                ),
                str(row["race_id"]),
            ),
        )


def _backfill_race_titles(
    connection: sqlite3.Connection,
) -> None:
    rows = connection.execute(
        """
        SELECT
            race_id,
            race_title
        FROM races
        WHERE
            race_title IS NOT NULL
            AND TRIM(race_title) != ''
        """
    ).fetchall()

    for row in rows:
        current_title = str(
            row["race_title"]
        )
        canonical_title = (
            canonical_race_title(
                current_title
            )
        )

        if canonical_title == current_title:
            continue

        connection.execute(
            """
            UPDATE races
            SET race_title = ?
            WHERE race_id = ?
            """,
            (
                canonical_title,
                str(row["race_id"]),
            ),
        )


def _deduplicate_races(
    connection: sqlite3.Connection,
) -> None:
    duplicate_keys = connection.execute(
        """
        SELECT race_key
        FROM races
        WHERE race_key IS NOT NULL
        GROUP BY race_key
        HAVING COUNT(*) > 1
        """
    ).fetchall()

    status_priority = {
        "確定": 3,
        "要確認": 2,
        "未確定": 1,
    }

    for key_row in duplicate_keys:
        race_key = str(key_row["race_key"])
        rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT *
                FROM races
                WHERE race_key = ?
                """,
                (race_key,),
            ).fetchall()
        ]

        canonical = max(
            rows,
            key=lambda row: (
                status_priority.get(
                    str(row.get("result_status")),
                    0,
                ),
                int(row.get("odds_complete") or 0),
                int(row.get("rider_count") or 0),
                str(row.get("updated_at") or ""),
            ),
        )

        data_source = max(
            rows,
            key=lambda row: (
                int(row.get("odds_complete") or 0),
                int(row.get("rider_count") or 0),
                str(row.get("updated_at") or ""),
            ),
        )

        result_source = max(
            rows,
            key=lambda row: (
                status_priority.get(
                    str(row.get("result_status")),
                    0,
                ),
                str(row.get("updated_at") or ""),
            ),
        )

        canonical_id = str(
            canonical["race_id"]
        )
        data_source_id = str(
            data_source["race_id"]
        )

        if data_source_id != canonical_id:
            connection.execute(
                "DELETE FROM riders WHERE race_id = ?",
                (canonical_id,),
            )
            connection.execute(
                "DELETE FROM odds WHERE race_id = ?",
                (canonical_id,),
            )

            connection.execute(
                """
                INSERT INTO riders (
                    race_id,
                    car_number,
                    rider_name,
                    cyclist_id,
                    home_prefecture,
                    class_name,
                    age,
                    generation,
                    ai_mark,
                    competition_score,
                    style,
                    s_count,
                    h_count,
                    b_count,
                    win_rate,
                    quinella_rate,
                    trio_rate,
                    comment,
                    lineup_number,
                    lineup_position,
                    lineup_length,
                    raw_json
                )
                SELECT
                    ?,
                    car_number,
                    rider_name,
                    cyclist_id,
                    home_prefecture,
                    class_name,
                    age,
                    generation,
                    ai_mark,
                    competition_score,
                    style,
                    s_count,
                    h_count,
                    b_count,
                    win_rate,
                    quinella_rate,
                    trio_rate,
                    comment,
                    lineup_number,
                    lineup_position,
                    lineup_length,
                    raw_json
                FROM riders
                WHERE race_id = ?
                """,
                (
                    canonical_id,
                    data_source_id,
                ),
            )

            connection.execute(
                """
                INSERT INTO odds (
                    race_id,
                    combination,
                    popularity,
                    odds,
                    collected_at,
                    is_winner
                )
                SELECT
                    ?,
                    combination,
                    popularity,
                    odds,
                    collected_at,
                    is_winner
                FROM odds
                WHERE race_id = ?
                """,
                (
                    canonical_id,
                    data_source_id,
                ),
            )

        race_url = next(
            (
                str(row.get("race_url") or "").strip()
                for row in rows
                if str(
                    row.get("race_url") or ""
                ).strip()
            ),
            "",
        )
        result_url = next(
            (
                str(row.get("result_url") or "").strip()
                for row in rows
                if str(
                    row.get("result_url") or ""
                ).strip()
            ),
            "",
        )

        connection.execute(
            """
            UPDATE races
            SET
                race_url = ?,
                result_url = ?,
                race_title = ?,
                race_grade = ?,
                race_stage = ?,
                race_class = ?,
                day_number = ?,
                scheduled_start_time = ?,
                race_distance_m = ?,
                lap_count = ?,
                weather = ?,
                temperature_c = ?,
                wind_direction = ?,
                wind_speed_mps = ?,
                lineup_source = ?,
                lineup_confidence = ?,
                feature_version = ?,
                rider_count = ?,
                lineup_json = ?,
                odds_complete = ?,
                result_status = ?,
                first_place = ?,
                second_place = ?,
                third_place = ?,
                winning_combination = ?,
                payout_per_100 = ?,
                review_reason = ?,
                result_raw_json = ?,
                updated_at = ?
            WHERE race_id = ?
            """,
            (
                race_url or None,
                result_url or None,
                data_source.get("race_title")
                or canonical.get("race_title"),
                data_source.get("race_grade")
                or canonical.get("race_grade"),
                data_source.get("race_stage")
                or canonical.get("race_stage"),
                data_source.get("race_class")
                or canonical.get("race_class"),
                data_source.get("day_number")
                or canonical.get("day_number"),
                data_source.get(
                    "scheduled_start_time"
                )
                or canonical.get(
                    "scheduled_start_time"
                ),
                data_source.get(
                    "race_distance_m"
                )
                or canonical.get(
                    "race_distance_m"
                ),
                data_source.get("lap_count")
                or canonical.get("lap_count"),
                data_source.get("weather")
                or canonical.get("weather"),
                data_source.get(
                    "temperature_c"
                )
                or canonical.get(
                    "temperature_c"
                ),
                data_source.get(
                    "wind_direction"
                )
                or canonical.get(
                    "wind_direction"
                ),
                data_source.get(
                    "wind_speed_mps"
                )
                or canonical.get(
                    "wind_speed_mps"
                ),
                data_source.get(
                    "lineup_source"
                )
                or canonical.get(
                    "lineup_source"
                ),
                data_source.get(
                    "lineup_confidence"
                )
                or canonical.get(
                    "lineup_confidence"
                ),
                max(
                    int(
                        row.get(
                            "feature_version"
                        )
                        or 0
                    )
                    for row in rows
                ),
                int(
                    data_source.get("rider_count")
                    or 0
                ),
                data_source.get("lineup_json")
                or "[]",
                int(
                    data_source.get("odds_complete")
                    or 0
                ),
                result_source.get("result_status")
                or "未確定",
                result_source.get("first_place"),
                result_source.get("second_place"),
                result_source.get("third_place"),
                result_source.get(
                    "winning_combination"
                ),
                result_source.get(
                    "payout_per_100"
                ),
                result_source.get("review_reason"),
                result_source.get(
                    "result_raw_json"
                ),
                max(
                    str(
                        row.get("updated_at")
                        or ""
                    )
                    for row in rows
                ),
                canonical_id,
            ),
        )

        for row in rows:
            duplicate_id = str(row["race_id"])

            if duplicate_id != canonical_id:
                connection.execute(
                    "DELETE FROM races "
                    "WHERE race_id = ?",
                    (duplicate_id,),
                )


def _backup_before_schema_migration(
    connection: sqlite3.Connection,
) -> Path | None:
    user_version = int(
        connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]
    )

    if user_version >= 7:
        return None

    has_races_table = (
        connection.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE
                type = 'table'
                AND name = 'races'
            """
        ).fetchone()[0]
        > 0
    )

    if not has_races_table:
        return None

    backup_directory = (
        DATABASE_PATH.parent
        / "backups"
    )
    backup_directory.mkdir(
        parents=True,
        exist_ok=True,
    )
    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S_%f"
    )
    backup_path = (
        backup_directory
        / (
            "keirin_learning_"
            "before_history_import_"
            f"{timestamp}.db"
        )
    )

    with sqlite3.connect(
        backup_path
    ) as destination:
        connection.backup(destination)

    return backup_path


def initialize_database() -> None:
    with get_connection() as connection:
        schema_version = int(
            connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]
        )

        _backup_before_schema_migration(
            connection
        )

        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS races (
                race_id TEXT PRIMARY KEY,
                race_key TEXT,
                race_date TEXT NOT NULL,
                venue TEXT NOT NULL,
                race_number INTEGER NOT NULL,
                race_url TEXT,
                result_url TEXT,
                race_title TEXT,
                race_grade TEXT,
                race_stage TEXT,
                race_class TEXT,
                day_number INTEGER,
                scheduled_start_time TEXT,
                race_distance_m INTEGER,
                lap_count INTEGER,
                weather TEXT,
                temperature_c REAL,
                wind_direction TEXT,
                wind_speed_mps REAL,
                lineup_source TEXT,
                lineup_confidence REAL,
                feature_version
                    INTEGER NOT NULL DEFAULT 0,
                rider_count INTEGER NOT NULL,
                lineup_json TEXT NOT NULL,
                odds_complete INTEGER NOT NULL DEFAULT 0,
                collected_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                result_status TEXT NOT NULL DEFAULT '未確定',
                first_place INTEGER,
                second_place INTEGER,
                third_place INTEGER,
                winning_combination TEXT,
                payout_per_100 INTEGER,
                review_reason TEXT,
                result_raw_json TEXT
            );

            CREATE TABLE IF NOT EXISTS riders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id TEXT NOT NULL,
                car_number INTEGER NOT NULL,
                rider_name TEXT,
                cyclist_id TEXT,
                home_prefecture TEXT,
                class_name TEXT,
                age INTEGER,
                generation INTEGER,
                ai_mark TEXT,
                competition_score REAL,
                style TEXT,
                s_count INTEGER,
                h_count INTEGER,
                b_count INTEGER,
                win_rate REAL,
                quinella_rate REAL,
                trio_rate REAL,
                comment TEXT,
                lineup_number INTEGER,
                lineup_position INTEGER,
                lineup_length INTEGER,
                raw_json TEXT NOT NULL,
                UNIQUE(race_id, car_number),
                FOREIGN KEY(race_id)
                    REFERENCES races(race_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS odds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id TEXT NOT NULL,
                combination TEXT NOT NULL,
                popularity INTEGER,
                odds REAL NOT NULL,
                collected_at TEXT NOT NULL,
                is_winner INTEGER NOT NULL DEFAULT 0,
                UNIQUE(race_id, combination),
                FOREIGN KEY(race_id)
                    REFERENCES races(race_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS
                independent_prediction_runs (
                    run_id TEXT PRIMARY KEY,
                    race_key TEXT NOT NULL,
                    race_date TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    race_number INTEGER NOT NULL,
                    model_version TEXT NOT NULL,
                    model_trained_at TEXT NOT NULL,
                    training_start_date TEXT,
                    training_end_date TEXT,
                    training_cutoff_date TEXT,
                    excluded_after_cutoff_race_count
                        INTEGER NOT NULL DEFAULT 0,
                    predicted_at TEXT NOT NULL,
                    input_snapshot_json
                        TEXT NOT NULL DEFAULT '{}',
                    input_snapshot_hash
                        TEXT NOT NULL DEFAULT '',
                    prediction_before_or_on_race
                        INTEGER NOT NULL DEFAULT 0,
                    result_known_at_prediction
                        INTEGER NOT NULL DEFAULT 0,
                    evaluation_eligible
                        INTEGER NOT NULL DEFAULT 0,
                    eligibility_reason TEXT,
                    result_status
                        TEXT NOT NULL DEFAULT '未確定',
                    winning_combination TEXT,
                    winning_rank INTEGER,
                    winning_probability REAL,
                    payout_per_100 INTEGER,
                    evaluated_at TEXT,
                    UNIQUE(
                        race_key,
                        model_version,
                        model_trained_at
                    )
                );

            CREATE TABLE IF NOT EXISTS
                independent_prediction_rows (
                    run_id TEXT NOT NULL,
                    combination TEXT NOT NULL,
                    predicted_rank INTEGER NOT NULL,
                    ai_probability REAL NOT NULL,
                    PRIMARY KEY(
                        run_id,
                        combination
                    ),
                    UNIQUE(
                        run_id,
                        predicted_rank
                    ),
                    FOREIGN KEY(run_id)
                        REFERENCES
                            independent_prediction_runs(
                                run_id
                            )
                        ON DELETE CASCADE
                );

            CREATE INDEX IF NOT EXISTS
                idx_races_date
                ON races(race_date);

            CREATE INDEX IF NOT EXISTS
                idx_riders_race
                ON riders(race_id);

            CREATE INDEX IF NOT EXISTS
                idx_odds_race
                ON odds(race_id);

            CREATE INDEX IF NOT EXISTS
                idx_odds_winner
                ON odds(is_winner);

            CREATE INDEX IF NOT EXISTS
                idx_independent_runs_race
                ON independent_prediction_runs(
                    race_key
                );

            CREATE INDEX IF NOT EXISTS
                idx_independent_runs_evaluation
                ON independent_prediction_runs(
                    evaluation_eligible,
                    result_status
                );
            """
        )

        _ensure_column(
            connection,
            "races",
            "race_key",
            "TEXT",
        )
        _ensure_column(
            connection,
            "races",
            "result_url",
            "TEXT",
        )
        _ensure_column(
            connection,
            "races",
            "review_reason",
            "TEXT",
        )
        _ensure_column(
            connection,
            "races",
            "result_raw_json",
            "TEXT",
        )

        for (
            column_name,
            column_type,
        ) in (
            ("race_grade", "TEXT"),
            ("race_stage", "TEXT"),
            ("race_class", "TEXT"),
            ("day_number", "INTEGER"),
            (
                "scheduled_start_time",
                "TEXT",
            ),
            ("race_distance_m", "INTEGER"),
            ("lap_count", "INTEGER"),
            ("weather", "TEXT"),
            ("temperature_c", "REAL"),
            ("wind_direction", "TEXT"),
            ("wind_speed_mps", "REAL"),
            ("lineup_source", "TEXT"),
            ("lineup_confidence", "REAL"),
            (
                "feature_version",
                "INTEGER NOT NULL DEFAULT 0",
            ),
        ):
            _ensure_column(
                connection,
                "races",
                column_name,
                column_type,
            )

        for (
            column_name,
            column_type,
        ) in (
            ("cyclist_id", "TEXT"),
            ("home_prefecture", "TEXT"),
            ("class_name", "TEXT"),
            ("age", "INTEGER"),
            ("generation", "INTEGER"),
        ):
            _ensure_column(
                connection,
                "riders",
                column_name,
                column_type,
            )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
                idx_riders_cyclist
                ON riders(cyclist_id)
            """
        )

        _ensure_column(
            connection,
            "independent_prediction_runs",
            "training_cutoff_date",
            "TEXT",
        )
        _ensure_column(
            connection,
            "independent_prediction_runs",
            "excluded_after_cutoff_race_count",
            "INTEGER NOT NULL DEFAULT 0",
        )

        if schema_version < 3:
            connection.execute(
                """
                DROP INDEX IF EXISTS
                    idx_races_race_key
                """
            )
            _backfill_race_keys(
                connection,
                force=True,
            )
        else:
            _backfill_race_keys(
                connection
            )

        if schema_version < 4:
            _backfill_race_titles(
                connection
            )

        _deduplicate_races(connection)

        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                idx_races_race_key
                ON races(race_key)
            """
        )
        connection.execute(
            "PRAGMA user_version=7"
        )


def safe_int(
    value: Any,
    default: int | None = None,
) -> int | None:
    if value in (None, ""):
        return default

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def safe_float(
    value: Any,
    default: float | None = None,
) -> float | None:
    if value in (None, ""):
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_race_id(
    race_date: str,
    venue: str,
    race_number: int,
    race_url: str = "",
) -> str:
    del race_url

    race_key = build_race_key(
        race_date,
        venue,
        race_number,
    )

    digest = hashlib.sha256(
        race_key.encode("utf-8")
    ).hexdigest()[:16]

    return (
        f"{race_date}_"
        f"{venue}_"
        f"{race_number:02d}_"
        f"{digest}"
    )


def build_lineup_metadata(
    lineup_groups: list[list[int]],
) -> dict[int, dict[str, int]]:
    metadata: dict[int, dict[str, int]] = {}

    for group_number, group in enumerate(
        lineup_groups,
        start=1,
    ):
        for position, car_number in enumerate(group):
            metadata[int(car_number)] = {
                "lineup_number": group_number,
                "lineup_position": position,
                "lineup_length": len(group),
            }

    return metadata


def validate_complete_odds(
    riders: list[dict[str, Any]],
    odds_rows: list[dict[str, Any]],
) -> tuple[bool, str]:
    rider_numbers = sorted(
        {
            int(number)
            for rider in riders
            if (
                number := safe_int(
                    rider.get("車番")
                )
            )
            is not None
        }
    )

    if len(rider_numbers) < 3:
        return (
            False,
            "出走車番を3車以上確認できません。",
        )

    expected = {
        f"{first}-{second}-{third}"
        for first in rider_numbers
        for second in rider_numbers
        for third in rider_numbers
        if len({first, second, third}) == 3
    }

    acquired: set[str] = set()

    for row in odds_rows:
        combination = str(
            row.get("組番", "")
        ).strip()
        odds_value = safe_float(
            row.get("オッズ")
        )

        if combination not in expected:
            return (
                False,
                "出走車番と一致しない組番があります: "
                f"{combination or '(空欄)'}",
            )

        if odds_value is None or odds_value <= 1:
            return (
                False,
                "無効な3連単オッズがあります: "
                f"{combination}",
            )

        if combination in acquired:
            return (
                False,
                "重複した3連単組番があります: "
                f"{combination}",
            )

        acquired.add(combination)

    missing = sorted(expected - acquired)

    if missing:
        preview = "、".join(missing[:10])

        if len(missing) > 10:
            preview += "…"

        return (
            False,
            f"3連単オッズが{len(missing)}組不足しています: "
            f"{preview}",
        )

    if len(odds_rows) != len(expected):
        return (
            False,
            "3連単オッズ件数が理論組番数と"
            "一致しません。",
        )

    return (
        True,
        f"全{len(expected)}組番を確認しました。",
    )


def _save_race_snapshot(
    *,
    race_date: str,
    venue: str,
    race_number: int,
    race_url: str,
    race_title: str,
    riders: list[dict[str, Any]],
    odds_rows: list[dict[str, Any]],
    lineup_groups: list[list[int]],
    odds_complete: bool,
    race_conditions: (
        dict[str, Any] | None
    ) = None,
) -> str:
    initialize_database()

    if odds_complete:
        complete, validation_message = (
            validate_complete_odds(
                riders,
                odds_rows,
            )
        )

        if not complete:
            raise ValueError(
                "オッズ完全性検証に失敗しました: "
                f"{validation_message}"
            )

    elif odds_rows:
        raise ValueError(
            "オッズ非依存AI用データには"
            "不完全なオッズを保存できません。"
        )

    rider_numbers = [
        safe_int(rider.get("車番"))
        for rider in riders
    ]
    valid_rider_numbers = [
        int(number)
        for number in rider_numbers
        if number is not None
    ]

    if (
        len(valid_rider_numbers) < 3
        or len(valid_rider_numbers)
        != len(riders)
        or len(valid_rider_numbers)
        != len(set(valid_rider_numbers))
        or any(
            number <= 0
            for number in valid_rider_numbers
        )
    ):
        raise ValueError(
            "出走車番は重複なしで"
            "3車以上必要です。"
        )

    race_key = build_race_key(
        race_date,
        venue,
        race_number,
    )
    candidate_race_id = build_race_id(
        race_date,
        venue,
        race_number,
    )

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    lineup_metadata = build_lineup_metadata(
        lineup_groups
    )
    stored_race_conditions = {
        **extract_race_conditions_from_riders(
            riders
        ),
        **(race_conditions or {}),
    }

    with get_connection() as connection:
        existing = connection.execute(
            """
            SELECT race_id, odds_complete
            FROM races
            WHERE race_key = ?
            LIMIT 1
            """,
            (race_key,),
        ).fetchone()

        race_id = (
            str(existing["race_id"])
            if existing is not None
            else candidate_race_id
        )

        effective_odds_complete = bool(
            odds_complete
            or (
                existing is not None
                and bool(
                    existing["odds_complete"]
                )
            )
        )

        connection.execute(
            """
            INSERT INTO races (
                race_id,
                race_key,
                race_date,
                venue,
                race_number,
                race_url,
                race_title,
                race_grade,
                race_stage,
                race_class,
                day_number,
                scheduled_start_time,
                race_distance_m,
                lap_count,
                weather,
                temperature_c,
                wind_direction,
                wind_speed_mps,
                lineup_source,
                lineup_confidence,
                feature_version,
                rider_count,
                lineup_json,
                odds_complete,
                collected_at,
                updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?
            )
            ON CONFLICT(race_id) DO UPDATE SET
                race_key = excluded.race_key,
                race_date = excluded.race_date,
                venue = excluded.venue,
                race_number = excluded.race_number,
                race_url = CASE
                    WHEN TRIM(excluded.race_url) != ''
                    THEN excluded.race_url
                    ELSE races.race_url
                END,
                race_title = CASE
                    WHEN TRIM(excluded.race_title) != ''
                    THEN excluded.race_title
                    ELSE races.race_title
                END,
                race_grade = CASE
                    WHEN TRIM(excluded.race_grade) != ''
                    THEN excluded.race_grade
                    ELSE races.race_grade
                END,
                race_stage = CASE
                    WHEN TRIM(excluded.race_stage) != ''
                    THEN excluded.race_stage
                    ELSE races.race_stage
                END,
                race_class = CASE
                    WHEN TRIM(excluded.race_class) != ''
                    THEN excluded.race_class
                    ELSE races.race_class
                END,
                day_number = COALESCE(
                    excluded.day_number,
                    races.day_number
                ),
                scheduled_start_time = CASE
                    WHEN TRIM(
                        excluded.scheduled_start_time
                    ) != ''
                    THEN excluded.scheduled_start_time
                    ELSE races.scheduled_start_time
                END,
                race_distance_m = COALESCE(
                    excluded.race_distance_m,
                    races.race_distance_m
                ),
                lap_count = COALESCE(
                    excluded.lap_count,
                    races.lap_count
                ),
                weather = CASE
                    WHEN TRIM(excluded.weather) != ''
                    THEN excluded.weather
                    ELSE races.weather
                END,
                temperature_c = COALESCE(
                    excluded.temperature_c,
                    races.temperature_c
                ),
                wind_direction = CASE
                    WHEN TRIM(
                        excluded.wind_direction
                    ) != ''
                    THEN excluded.wind_direction
                    ELSE races.wind_direction
                END,
                wind_speed_mps = COALESCE(
                    excluded.wind_speed_mps,
                    races.wind_speed_mps
                ),
                lineup_source = CASE
                    WHEN TRIM(
                        excluded.lineup_source
                    ) != ''
                    THEN excluded.lineup_source
                    ELSE races.lineup_source
                END,
                lineup_confidence = COALESCE(
                    excluded.lineup_confidence,
                    races.lineup_confidence
                ),
                feature_version = MAX(
                    races.feature_version,
                    excluded.feature_version
                ),
                rider_count = excluded.rider_count,
                lineup_json = excluded.lineup_json,
                odds_complete = excluded.odds_complete,
                updated_at = excluded.updated_at
            """,
            (
                race_id,
                race_key,
                race_date,
                venue,
                int(race_number),
                race_url,
                race_title,
                str(
                    stored_race_conditions.get(
                        "レースグレード"
                    )
                    or ""
                ),
                str(
                    stored_race_conditions.get(
                        "レース区分"
                    )
                    or ""
                ),
                str(
                    stored_race_conditions.get(
                        "レース級別"
                    )
                    or ""
                ),
                safe_int(
                    stored_race_conditions.get(
                        "開催日目"
                    )
                ),
                str(
                    stored_race_conditions.get(
                        "発走時刻"
                    )
                    or ""
                ),
                safe_int(
                    stored_race_conditions.get(
                        "距離m"
                    )
                ),
                safe_int(
                    stored_race_conditions.get(
                        "周回数"
                    )
                ),
                str(
                    stored_race_conditions.get(
                        "天候"
                    )
                    or ""
                ),
                safe_float(
                    stored_race_conditions.get(
                        "気温C"
                    )
                ),
                str(
                    stored_race_conditions.get(
                        "風向"
                    )
                    or ""
                ),
                safe_float(
                    stored_race_conditions.get(
                        "風速mps"
                    )
                ),
                str(
                    stored_race_conditions.get(
                        "並び取得方式"
                    )
                    or ""
                ),
                safe_float(
                    stored_race_conditions.get(
                        "並び信頼度"
                    )
                ),
                1,
                len(riders),
                json.dumps(
                    lineup_groups,
                    ensure_ascii=False,
                ),
                (
                    1
                    if effective_odds_complete
                    else 0
                ),
                now,
                now,
            ),
        )

        connection.execute(
            "DELETE FROM riders WHERE race_id = ?",
            (race_id,),
        )
        if odds_complete:
            connection.execute(
                "DELETE FROM odds WHERE race_id = ?",
                (race_id,),
            )

        for rider in riders:
            car_number = safe_int(
                rider.get("車番")
            )

            if car_number is None:
                continue

            lineup = lineup_metadata.get(
                car_number,
                {
                    "lineup_number": None,
                    "lineup_position": None,
                    "lineup_length": 1,
                },
            )

            connection.execute(
                """
                INSERT INTO riders (
                    race_id,
                    car_number,
                    rider_name,
                    cyclist_id,
                    home_prefecture,
                    class_name,
                    age,
                    generation,
                    ai_mark,
                    competition_score,
                    style,
                    s_count,
                    h_count,
                    b_count,
                    win_rate,
                    quinella_rate,
                    trio_rate,
                    comment,
                    lineup_number,
                    lineup_position,
                    lineup_length,
                    raw_json
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?
                )
                ON CONFLICT(
                    race_id,
                    car_number
                ) DO UPDATE SET
                    rider_name =
                        excluded.rider_name,
                    cyclist_id =
                        excluded.cyclist_id,
                    home_prefecture =
                        excluded.home_prefecture,
                    class_name =
                        excluded.class_name,
                    age =
                        excluded.age,
                    generation =
                        excluded.generation,
                    ai_mark =
                        excluded.ai_mark,
                    competition_score =
                        excluded.competition_score,
                    style =
                        excluded.style,
                    s_count =
                        excluded.s_count,
                    h_count =
                        excluded.h_count,
                    b_count =
                        excluded.b_count,
                    win_rate =
                        excluded.win_rate,
                    quinella_rate =
                        excluded.quinella_rate,
                    trio_rate =
                        excluded.trio_rate,
                    comment =
                        excluded.comment,
                    lineup_number =
                        excluded.lineup_number,
                    lineup_position =
                        excluded.lineup_position,
                    lineup_length =
                        excluded.lineup_length,
                    raw_json =
                        excluded.raw_json
                """,
                (
                    race_id,
                    car_number,
                    rider.get("選手名", ""),
                    rider.get("選手ID", ""),
                    rider.get("府県", ""),
                    rider.get("級班", ""),
                    safe_int(
                        rider.get("年齢")
                    ),
                    safe_int(
                        rider.get("期別")
                    ),
                    rider.get("AI印", ""),
                    safe_float(
                        rider.get("競走得点")
                    ),
                    rider.get("脚質", ""),
                    safe_int(rider.get("S"), 0),
                    safe_int(rider.get("H"), 0),
                    safe_int(rider.get("B"), 0),
                    safe_float(
                        rider.get("勝率")
                    ),
                    safe_float(
                        rider.get("2連対率")
                    ),
                    safe_float(
                        rider.get("3連対率")
                    ),
                    rider.get("コメント", ""),
                    lineup.get(
                        "lineup_number"
                    ),
                    lineup.get(
                        "lineup_position"
                    ),
                    lineup.get(
                        "lineup_length",
                        1,
                    ),
                    json.dumps(
                        rider,
                        ensure_ascii=False,
                    ),
                ),
            )

        for row in odds_rows:
            combination = str(
                row.get("組番", "")
            ).strip()

            odds_value = safe_float(
                row.get("オッズ")
            )

            if (
                not combination
                or odds_value is None
            ):
                continue

            connection.execute(
                """
                INSERT INTO odds (
                    race_id,
                    combination,
                    popularity,
                    odds,
                    collected_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(
                    race_id,
                    combination
                ) DO UPDATE SET
                    popularity =
                        excluded.popularity,
                    odds =
                        excluded.odds,
                    collected_at =
                        excluded.collected_at
                """,
                (
                    race_id,
                    combination,
                    safe_int(
                        row.get("人気")
                    ),
                    odds_value,
                    now,
                ),
            )

        winning_row = connection.execute(
            """
            SELECT winning_combination
            FROM races
            WHERE race_id = ?
            """,
            (race_id,),
        ).fetchone()
        winning_combination = (
            str(
                winning_row[
                    "winning_combination"
                ]
                or ""
            )
            if winning_row is not None
            else ""
        )

        if winning_combination:
            connection.execute(
                """
                UPDATE odds
                SET is_winner = CASE
                    WHEN combination = ?
                    THEN 1
                    ELSE 0
                END
                WHERE race_id = ?
                """,
                (
                    winning_combination,
                    race_id,
                ),
            )

    return race_id


def save_race_snapshot(
    *,
    race_date: str,
    venue: str,
    race_number: int,
    race_url: str,
    race_title: str,
    riders: list[dict[str, Any]],
    odds_rows: list[dict[str, Any]],
    lineup_groups: list[list[int]],
    odds_complete: bool,
    race_conditions: (
        dict[str, Any] | None
    ) = None,
) -> str:
    if not odds_complete:
        raise ValueError(
            "オッズ完全性がNGのため、"
            "期待値学習用データへ"
            "保存できません。"
        )

    return _save_race_snapshot(
        race_date=race_date,
        venue=venue,
        race_number=race_number,
        race_url=race_url,
        race_title=race_title,
        riders=riders,
        odds_rows=odds_rows,
        lineup_groups=lineup_groups,
        odds_complete=True,
        race_conditions=race_conditions,
    )


def save_independent_race_snapshot(
    *,
    race_date: str,
    venue: str,
    race_number: int,
    race_url: str,
    race_title: str,
    riders: list[dict[str, Any]],
    lineup_groups: list[list[int]],
    race_conditions: (
        dict[str, Any] | None
    ) = None,
) -> str:
    return _save_race_snapshot(
        race_date=race_date,
        venue=venue,
        race_number=race_number,
        race_url=race_url,
        race_title=race_title,
        riders=riders,
        odds_rows=[],
        lineup_groups=lineup_groups,
        odds_complete=False,
        race_conditions=race_conditions,
    )


def _normalize_independent_prediction_rows(
    rows: list[dict[str, Any]],
    expected_count: int | None = None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    combinations: set[str] = set()
    ranks: set[int] = set()

    for row in rows:
        combination = str(
            row.get(
                "combination",
                row.get("組番", ""),
            )
        ).strip()
        rank = safe_int(
            row.get(
                "予測順位",
                row.get(
                    "predicted_rank"
                ),
            )
        )
        probability = safe_float(
            row.get(
                "AI確率",
                row.get(
                    "ai_probability"
                ),
            )
        )

        if not re.fullmatch(
            r"[1-9]-[1-9]-[1-9]",
            combination,
        ):
            raise ValueError(
                "予測組番の形式が不正です: "
                f"{combination}"
            )

        parts = combination.split("-")

        if len(set(parts)) != 3:
            raise ValueError(
                "予測組番に重複車番があります: "
                f"{combination}"
            )

        if rank is None or rank <= 0:
            raise ValueError(
                "予測順位は1以上が必要です。"
            )

        if (
            probability is None
            or probability < 0
            or probability > 1
        ):
            raise ValueError(
                "AI確率は0〜1で保存してください。"
            )

        if combination in combinations:
            raise ValueError(
                "予測組番が重複しています: "
                f"{combination}"
            )

        if rank in ranks:
            raise ValueError(
                "予測順位が重複しています: "
                f"{rank}"
            )

        combinations.add(combination)
        ranks.add(rank)
        normalized.append(
            {
                "combination": combination,
                "predicted_rank": rank,
                "ai_probability": (
                    probability
                ),
            }
        )

    normalized.sort(
        key=lambda row: int(
            row["predicted_rank"]
        )
    )

    if not normalized:
        raise ValueError(
            "保存する独立AI予測がありません。"
        )

    expected_ranks = set(
        range(1, len(normalized) + 1)
    )

    if ranks != expected_ranks:
        raise ValueError(
            "予測順位は1位から連番で"
            "保存してください。"
        )

    if (
        expected_count is not None
        and int(expected_count) > 0
        and len(normalized)
        != int(expected_count)
    ):
        raise ValueError(
            "予測件数がモデル出力件数と"
            "一致しません。"
        )

    probability_sum = sum(
        float(row["ai_probability"])
        for row in normalized
    )

    if abs(probability_sum - 1.0) > 1e-6:
        raise ValueError(
            "全組番のAI確率合計が1では"
            "ありません。"
        )

    return normalized


def _evaluate_independent_prediction_runs(
    connection: sqlite3.Connection,
    *,
    race_key: str,
    winning_combination: str,
    payout_per_100: int | None,
    evaluated_at: str,
) -> None:
    runs = connection.execute(
        """
        SELECT run_id
        FROM independent_prediction_runs
        WHERE race_key = ?
        """,
        (race_key,),
    ).fetchall()

    for run in runs:
        run_id = str(run["run_id"])
        winning_row = connection.execute(
            """
            SELECT
                predicted_rank,
                ai_probability
            FROM independent_prediction_rows
            WHERE
                run_id = ?
                AND combination = ?
            """,
            (
                run_id,
                winning_combination,
            ),
        ).fetchone()

        if winning_row is None:
            connection.execute(
                """
                UPDATE independent_prediction_runs
                SET
                    result_status = '照合失敗',
                    winning_combination = ?,
                    winning_rank = NULL,
                    winning_probability = NULL,
                    payout_per_100 = ?,
                    evaluated_at = ?
                WHERE run_id = ?
                """,
                (
                    winning_combination,
                    payout_per_100,
                    evaluated_at,
                    run_id,
                ),
            )
            continue

        connection.execute(
            """
            UPDATE independent_prediction_runs
            SET
                result_status = '確定',
                winning_combination = ?,
                winning_rank = ?,
                winning_probability = ?,
                payout_per_100 = ?,
                evaluated_at = ?
            WHERE run_id = ?
            """,
            (
                winning_combination,
                int(
                    winning_row[
                        "predicted_rank"
                    ]
                ),
                float(
                    winning_row[
                        "ai_probability"
                    ]
                ),
                payout_per_100,
                evaluated_at,
                run_id,
            ),
        )


def _mark_independent_prediction_review(
    connection: sqlite3.Connection,
    *,
    race_key: str,
    evaluated_at: str,
) -> None:
    connection.execute(
        """
        UPDATE independent_prediction_runs
        SET
            result_status = '要確認',
            winning_combination = NULL,
            winning_rank = NULL,
            winning_probability = NULL,
            payout_per_100 = NULL,
            evaluated_at = ?
        WHERE race_key = ?
        """,
        (
            evaluated_at,
            race_key,
        ),
    )


def _prediction_before_race_start(
    *,
    race_date: str,
    predicted_at: str,
    scheduled_start_time: str = "",
) -> tuple[bool, str]:
    try:
        target_date = date.fromisoformat(
            str(race_date)[:10]
        )
        prediction_datetime = (
            datetime.fromisoformat(
                str(predicted_at)
            )
        )
    except ValueError as exc:
        raise ValueError(
            "予測日または開催日の形式が"
            "不正です。"
        ) from exc

    prediction_date = (
        prediction_datetime.date()
    )

    if prediction_date < target_date:
        return True, ""

    if prediction_date > target_date:
        return False, "開催日より後に予測"

    start_text = str(
        scheduled_start_time or ""
    ).strip()

    if not start_text:
        return True, ""

    try:
        start_clock = (
            datetime.strptime(
                start_text,
                "%H:%M",
            ).time()
        )
    except ValueError:
        return True, ""

    start_datetime = datetime.combine(
        target_date,
        start_clock,
    )

    if prediction_datetime.tzinfo is not None:
        start_datetime = (
            start_datetime.replace(
                tzinfo=(
                    prediction_datetime.tzinfo
                )
            )
        )

    if prediction_datetime > start_datetime:
        return False, "発走時刻以後に予測"

    return True, ""


def save_independent_prediction(
    *,
    race_date: str,
    venue: str,
    race_number: int,
    prediction_rows: list[
        dict[str, Any]
    ],
    model_metadata: dict[str, Any],
    input_snapshot: dict[
        str,
        Any,
    ] | None = None,
    predicted_at: str | None = None,
    result_known_at_prediction: (
        bool | None
    ) = None,
) -> dict[str, Any]:
    initialize_database()

    normalized_rows = (
        _normalize_independent_prediction_rows(
            prediction_rows,
            expected_count=safe_int(
                model_metadata.get(
                    "prediction_count"
                )
            ),
        )
    )
    race_key = build_race_key(
        race_date,
        venue,
        race_number,
    )
    normalized_venue = (
        canonical_venue_display(venue)
        or str(venue)
    )
    model_version = str(
        model_metadata.get(
            "model_version",
            "",
        )
        or "unknown"
    )
    model_trained_at = str(
        model_metadata.get(
            "trained_at",
            "",
        )
        or "unknown"
    )
    training_start_date = str(
        model_metadata.get(
            "training_start_date",
            "",
        )
        or ""
    )
    training_end_date = str(
        model_metadata.get(
            "training_end_date",
            "",
        )
        or ""
    )
    training_cutoff_date = str(
        model_metadata.get(
            "training_cutoff_date",
            "",
        )
        or ""
    )
    excluded_after_cutoff_race_count = (
        safe_int(
            model_metadata.get(
                "excluded_after_cutoff_race_count"
            ),
            0,
        )
        or 0
    )
    prediction_timestamp = (
        str(predicted_at)
        if predicted_at
        else datetime.now().isoformat(
            timespec="seconds"
        )
    )
    snapshot_json = json.dumps(
        input_snapshot or {},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    snapshot_hash = hashlib.sha256(
        snapshot_json.encode("utf-8")
    ).hexdigest()

    try:
        target_date = date.fromisoformat(
            str(race_date)[:10]
        )
    except ValueError as exc:
        raise ValueError(
            "開催日の形式が不正です。"
        ) from exc
    snapshot_conditions = dict(
        (
            input_snapshot or {}
        ).get(
            "race_conditions",
            {},
        )
        or {}
    )
    snapshot_start_time = str(
        snapshot_conditions.get(
            "発走時刻",
            snapshot_conditions.get(
                "scheduled_start_time",
                "",
            ),
        )
        or ""
    )
    run_digest = hashlib.sha256(
        (
            f"{race_key}|"
            f"{model_version}|"
            f"{model_trained_at}"
        ).encode("utf-8")
    ).hexdigest()[:24]
    run_id = f"independent_{run_digest}"

    with get_connection() as connection:
        existing = connection.execute(
            """
            SELECT *
            FROM independent_prediction_runs
            WHERE
                race_key = ?
                AND model_version = ?
                AND model_trained_at = ?
            LIMIT 1
            """,
            (
                race_key,
                model_version,
                model_trained_at,
            ),
        ).fetchone()

        if existing is not None:
            output = dict(existing)
            output["created"] = False
            return output

        race = connection.execute(
            """
            SELECT
                result_status,
                winning_combination,
                payout_per_100,
                scheduled_start_time
            FROM races
            WHERE race_key = ?
            LIMIT 1
            """,
            (race_key,),
        ).fetchone()
        database_result_known = (
            race is not None
            and str(
                race["result_status"]
            )
            in ("確定", "要確認")
        )
        result_known = (
            bool(
                result_known_at_prediction
            )
            if (
                result_known_at_prediction
                is not None
            )
            else database_result_known
        )
        scheduled_start_time = (
            str(
                race[
                    "scheduled_start_time"
                ]
                or ""
            )
            if race is not None
            else ""
        ) or snapshot_start_time
        (
            prediction_before_or_on_race,
            prediction_timing_reason,
        ) = _prediction_before_race_start(
            race_date=race_date,
            predicted_at=(
                prediction_timestamp
            ),
            scheduled_start_time=(
                scheduled_start_time
            ),
        )
        previous_official = (
            connection.execute(
                """
                SELECT COUNT(*)
                FROM independent_prediction_runs
                WHERE
                    race_key = ?
                    AND evaluation_eligible = 1
                """,
                (race_key,),
            ).fetchone()[0]
            > 0
        )
        reasons: list[str] = []
        model_end_date: date | None = None

        if not training_end_date:
            reasons.append(
                "学習終了日の記録がないため"
                "モデル再学習が必要"
            )
        else:
            try:
                model_end_date = (
                    date.fromisoformat(
                        training_end_date[
                            :10
                        ]
                    )
                )
            except ValueError:
                reasons.append(
                    "学習終了日の形式が不正"
                )
            else:
                if target_date <= model_end_date:
                    reasons.append(
                        "対象レースが学習期間内"
                    )

        if not training_cutoff_date:
            reasons.append(
                "当日除外の学習締切記録が"
                "ないためモデル再学習が必要"
            )
        else:
            try:
                model_cutoff_date = (
                    date.fromisoformat(
                        training_cutoff_date[
                            :10
                        ]
                    )
                )
            except ValueError:
                reasons.append(
                    "学習締切日の形式が不正"
                )
            else:
                if (
                    model_end_date is not None
                    and model_end_date
                    > model_cutoff_date
                ):
                    reasons.append(
                        "学習データが締切日より後"
                    )

                if target_date <= model_cutoff_date:
                    reasons.append(
                        "対象レースが学習締切日以前"
                    )

        if not prediction_before_or_on_race:
            reasons.append(
                prediction_timing_reason
            )

        if result_known:
            reasons.append(
                "予測時点で結果登録済み"
            )

        if previous_official:
            reasons.append(
                "同一レースの正式予測は"
                "初回のみ"
            )

        evaluation_eligible = not reasons
        connection.execute(
            """
            INSERT INTO independent_prediction_runs (
                run_id,
                race_key,
                race_date,
                venue,
                race_number,
                model_version,
                model_trained_at,
                training_start_date,
                training_end_date,
                training_cutoff_date,
                excluded_after_cutoff_race_count,
                predicted_at,
                input_snapshot_json,
                input_snapshot_hash,
                prediction_before_or_on_race,
                result_known_at_prediction,
                evaluation_eligible,
                eligibility_reason
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                run_id,
                race_key,
                str(race_date)[:10],
                normalized_venue,
                int(race_number),
                model_version,
                model_trained_at,
                training_start_date,
                training_end_date,
                training_cutoff_date,
                excluded_after_cutoff_race_count,
                prediction_timestamp,
                snapshot_json,
                snapshot_hash,
                (
                    1
                    if prediction_before_or_on_race
                    else 0
                ),
                1 if result_known else 0,
                1 if evaluation_eligible else 0,
                "、".join(reasons),
            ),
        )

        connection.executemany(
            """
            INSERT INTO independent_prediction_rows (
                run_id,
                combination,
                predicted_rank,
                ai_probability
            )
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    str(row["combination"]),
                    int(row["predicted_rank"]),
                    float(row["ai_probability"]),
                )
                for row in normalized_rows
            ],
        )

        if race is not None:
            race_status = str(
                race["result_status"]
            )

            if (
                race_status == "確定"
                and race[
                    "winning_combination"
                ]
            ):
                (
                    _evaluate_independent_prediction_runs(
                        connection,
                        race_key=race_key,
                        winning_combination=str(
                            race[
                                "winning_combination"
                            ]
                        ),
                        payout_per_100=safe_int(
                            race[
                                "payout_per_100"
                            ]
                        ),
                        evaluated_at=(
                            prediction_timestamp
                        ),
                    )
                )
            elif race_status == "要確認":
                _mark_independent_prediction_review(
                    connection,
                    race_key=race_key,
                    evaluated_at=(
                        prediction_timestamp
                    ),
                )

        saved = connection.execute(
            """
            SELECT *
            FROM independent_prediction_runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()

    output = dict(saved)
    output["created"] = True
    return output


def sync_independent_prediction_results() -> int:
    initialize_database()
    updated = 0
    now = datetime.now().isoformat(
        timespec="seconds"
    )

    with get_connection() as connection:
        races = connection.execute(
            """
            SELECT
                race_key,
                result_status,
                winning_combination,
                payout_per_100
            FROM races
            WHERE
                result_status IN (
                    '確定',
                    '要確認'
                )
                AND race_key IN (
                    SELECT race_key
                    FROM independent_prediction_runs
                    WHERE
                        result_status = '未確定'
                )
            """
        ).fetchall()

        for race in races:
            race_key = str(race["race_key"])

            if (
                str(race["result_status"])
                == "確定"
                and race[
                    "winning_combination"
                ]
            ):
                _evaluate_independent_prediction_runs(
                    connection,
                    race_key=race_key,
                    winning_combination=str(
                        race[
                            "winning_combination"
                        ]
                    ),
                    payout_per_100=safe_int(
                        race[
                            "payout_per_100"
                        ]
                    ),
                    evaluated_at=now,
                )
            else:
                _mark_independent_prediction_review(
                    connection,
                    race_key=race_key,
                    evaluated_at=now,
                )

            updated += 1

    return updated


def get_independent_evaluation_summary(
) -> dict[str, Any]:
    sync_independent_prediction_results()

    with get_connection() as connection:
        official = connection.execute(
            """
            SELECT
                COUNT(*) AS race_count,
                AVG(winning_rank)
                    AS mean_winner_rank,
                MAX(payout_per_100)
                    AS maximum_payout
            FROM independent_prediction_runs
            WHERE
                evaluation_eligible = 1
                AND result_status = '確定'
            """
        ).fetchone()
        counts = connection.execute(
            """
            SELECT
                SUM(
                    CASE
                        WHEN evaluation_eligible = 0
                        THEN 1
                        ELSE 0
                    END
                ) AS reference_count,
                SUM(
                    CASE
                        WHEN
                            evaluation_eligible = 1
                            AND result_status = '未確定'
                        THEN 1
                        ELSE 0
                    END
                ) AS pending_count,
                SUM(
                    CASE
                        WHEN
                            evaluation_eligible = 1
                            AND result_status IN (
                                '要確認',
                                '照合失敗'
                            )
                        THEN 1
                        ELSE 0
                    END
                ) AS review_count
            FROM independent_prediction_runs
            """
        ).fetchone()
        official_count = int(
            official["race_count"] or 0
        )
        rates: dict[str, float] = {}

        for threshold in (
            1,
            5,
            10,
            20,
            30,
        ):
            hit_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM independent_prediction_runs
                WHERE
                    evaluation_eligible = 1
                    AND result_status = '確定'
                    AND winning_rank <= ?
                """,
                (threshold,),
            ).fetchone()[0]
            rates[f"top{threshold}_hit_rate"] = (
                float(hit_count)
                / official_count
                if official_count
                else 0.0
            )

    return {
        "official_count": official_count,
        "reference_count": int(
            counts["reference_count"] or 0
        ),
        "pending_count": int(
            counts["pending_count"] or 0
        ),
        "review_count": int(
            counts["review_count"] or 0
        ),
        "mean_winner_rank": float(
            official["mean_winner_rank"]
            or 0.0
        ),
        "maximum_payout": int(
            official["maximum_payout"]
            or 0
        ),
        **rates,
    }


def get_recent_independent_evaluations(
    limit: int = 100,
) -> list[dict[str, Any]]:
    sync_independent_prediction_results()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                run_id,
                race_date,
                venue,
                race_number,
                predicted_at,
                model_version,
                model_trained_at,
                training_start_date,
                training_end_date,
                training_cutoff_date,
                excluded_after_cutoff_race_count,
                evaluation_eligible,
                eligibility_reason,
                result_status,
                winning_combination,
                winning_rank,
                winning_probability,
                payout_per_100,
                evaluated_at
            FROM independent_prediction_runs
            ORDER BY
                race_date DESC,
                predicted_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


def get_independent_prediction_detail(
    run_id: str,
) -> dict[str, Any] | None:
    initialize_database()
    normalized_run_id = str(run_id).strip()

    if not normalized_run_id:
        return None

    with get_connection() as connection:
        run = connection.execute(
            """
            SELECT
                run_id,
                race_key,
                race_date,
                venue,
                race_number,
                model_version,
                model_trained_at,
                predicted_at,
                input_snapshot_json,
                evaluation_eligible,
                eligibility_reason,
                result_status,
                winning_combination,
                winning_rank,
                winning_probability,
                payout_per_100,
                evaluated_at
            FROM independent_prediction_runs
            WHERE run_id = ?
            LIMIT 1
            """,
            (normalized_run_id,),
        ).fetchone()

        if run is None:
            return None

        stored_rows = connection.execute(
            """
            SELECT
                combination,
                predicted_rank,
                ai_probability
            FROM independent_prediction_rows
            WHERE run_id = ?
            ORDER BY predicted_rank
            """,
            (normalized_run_id,),
        ).fetchall()

    output = dict(run)
    winning_combination = str(
        output.get(
            "winning_combination",
            "",
        )
        or ""
    )
    prediction_rows = [
        {
            "combination": str(
                row["combination"]
            ),
            "predicted_rank": int(
                row["predicted_rank"]
            ),
            "ai_probability": float(
                row["ai_probability"]
            ),
            "is_winner": (
                bool(winning_combination)
                and str(
                    row["combination"]
                )
                == winning_combination
            ),
        }
        for row in stored_rows
    ]
    rider_names: dict[int, str] = {}

    try:
        input_snapshot = json.loads(
            str(
                output.get(
                    "input_snapshot_json",
                    "{}",
                )
                or "{}"
            )
        )
    except (
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        input_snapshot = {}

    for rider in (
        input_snapshot.get("riders", [])
        if isinstance(
            input_snapshot,
            dict,
        )
        else []
    ):
        if not isinstance(rider, dict):
            continue

        car_number = safe_int(
            rider.get("車番")
        )

        if (
            car_number is None
            or car_number <= 0
        ):
            continue

        rider_names[car_number] = str(
            rider.get("選手名", "")
            or ""
        )

    position_probabilities: dict[
        int,
        list[float],
    ] = {}

    for row in prediction_rows:
        parts = str(
            row["combination"]
        ).split("-")

        if len(parts) != 3:
            continue

        car_numbers = [
            safe_int(value)
            for value in parts
        ]

        if any(
            value is None
            or value <= 0
            for value in car_numbers
        ):
            continue

        probability = float(
            row["ai_probability"]
        )

        for position, car_number in enumerate(
            car_numbers
        ):
            if car_number is None:
                continue

            position_probabilities.setdefault(
                car_number,
                [0.0, 0.0, 0.0],
            )[position] += probability

    rider_probabilities = []

    for car_number in sorted(
        set(rider_names)
        | set(position_probabilities)
    ):
        positions = (
            position_probabilities.get(
                car_number,
                [0.0, 0.0, 0.0],
            )
        )
        first_probability = float(
            positions[0]
        )
        second_probability = float(
            positions[1]
        )
        third_probability = float(
            positions[2]
        )
        rider_probabilities.append(
            {
                "car_number": car_number,
                "rider_name": rider_names.get(
                    car_number,
                    "",
                ),
                "first_probability": (
                    first_probability
                ),
                "second_probability": (
                    second_probability
                ),
                "third_probability": (
                    third_probability
                ),
                "top3_probability": min(
                    1.0,
                    first_probability
                    + second_probability
                    + third_probability,
                ),
            }
        )

    rider_probabilities.sort(
        key=lambda row: (
            -float(
                row[
                    "first_probability"
                ]
            ),
            -float(
                row[
                    "top3_probability"
                ]
            ),
            int(row["car_number"]),
        )
    )
    output["prediction_rows"] = (
        prediction_rows
    )
    output["rider_probabilities"] = (
        rider_probabilities
    )
    output["probability_sum"] = sum(
        float(
            row["ai_probability"]
        )
        for row in prediction_rows
    )
    output.pop(
        "input_snapshot_json",
        None,
    )
    return output


def get_independent_hole_hits(
    limit: int = 50,
) -> list[dict[str, Any]]:
    sync_independent_prediction_results()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                race_date,
                venue,
                race_number,
                winning_combination,
                winning_rank,
                winning_probability,
                payout_per_100,
                predicted_at
            FROM independent_prediction_runs
            WHERE
                evaluation_eligible = 1
                AND result_status = '確定'
                AND winning_rank > 10
            ORDER BY
                payout_per_100 DESC,
                winning_rank DESC,
                race_date DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


def save_race_result(
    *,
    race_id: str,
    first_place: int,
    second_place: int,
    third_place: int,
    payout_per_100: int | None = None,
    result_url: str = "",
    raw_result: dict[str, Any] | None = None,
) -> None:
    initialize_database()

    places = [
        int(first_place),
        int(second_place),
        int(third_place),
    ]

    if len(set(places)) != 3:
        raise ValueError(
            "1着・2着・3着は異なる車番が必要です。"
        )

    if (
        payout_per_100 is not None
        and int(payout_per_100) <= 0
    ):
        raise ValueError(
            "払戻金は1円以上で保存してください。"
        )

    winning_combination = (
        f"{int(first_place)}-"
        f"{int(second_place)}-"
        f"{int(third_place)}"
    )

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    with get_connection() as connection:
        race = connection.execute(
            """
            SELECT race_id, race_key
            FROM races
            WHERE race_id = ?
            """,
            (race_id,),
        ).fetchone()

        if race is None:
            raise ValueError(
                "結果保存先のレースがありません。"
            )

        valid_cars = {
            int(row["car_number"])
            for row in connection.execute(
                """
                SELECT car_number
                FROM riders
                WHERE race_id = ?
                """,
                (race_id,),
            ).fetchall()
        }

        if (
            valid_cars
            and not set(places).issubset(valid_cars)
        ):
            raise ValueError(
                "着順に保存済み出走車番以外の"
                "番号が含まれています。"
            )

        connection.execute(
            """
            UPDATE races
            SET
                result_status = '確定',
                first_place = ?,
                second_place = ?,
                third_place = ?,
                winning_combination = ?,
                payout_per_100 = ?,
                result_url = CASE
                    WHEN TRIM(?) != ''
                    THEN ?
                    ELSE result_url
                END,
                review_reason = NULL,
                result_raw_json = ?,
                updated_at = ?
            WHERE race_id = ?
            """,
            (
                int(first_place),
                int(second_place),
                int(third_place),
                winning_combination,
                payout_per_100,
                str(result_url).strip(),
                str(result_url).strip(),
                (
                    json.dumps(
                        raw_result,
                        ensure_ascii=False,
                    )
                    if raw_result is not None
                    else None
                ),
                now,
                race_id,
            ),
        )

        connection.execute(
            """
            UPDATE odds
            SET is_winner = CASE
                WHEN combination = ?
                THEN 1
                ELSE 0
            END
            WHERE race_id = ?
            """,
            (
                winning_combination,
                race_id,
            ),
        )

        _evaluate_independent_prediction_runs(
            connection,
            race_key=str(race["race_key"]),
            winning_combination=(
                winning_combination
            ),
            payout_per_100=(
                payout_per_100
            ),
            evaluated_at=now,
        )


def save_race_review(
    *,
    race_id: str,
    reason: str,
    result_url: str = "",
    raw_result: dict[str, Any] | None = None,
) -> bool:
    initialize_database()

    normalized_reason = str(reason).strip()

    if not normalized_reason:
        normalized_reason = (
            "自動確定できない結果です。"
        )

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    with get_connection() as connection:
        race = connection.execute(
            """
            SELECT race_key
            FROM races
            WHERE race_id = ?
            """,
            (race_id,),
        ).fetchone()
        cursor = connection.execute(
            """
            UPDATE races
            SET
                result_status = '要確認',
                first_place = NULL,
                second_place = NULL,
                third_place = NULL,
                winning_combination = NULL,
                payout_per_100 = NULL,
                result_url = CASE
                    WHEN TRIM(?) != ''
                    THEN ?
                    ELSE result_url
                END,
                review_reason = ?,
                result_raw_json = ?,
                updated_at = ?
            WHERE
                race_id = ?
                AND result_status != '確定'
            """,
            (
                str(result_url).strip(),
                str(result_url).strip(),
                normalized_reason,
                (
                    json.dumps(
                        raw_result,
                        ensure_ascii=False,
                    )
                    if raw_result is not None
                    else None
                ),
                now,
                race_id,
            ),
        )

        if (
            cursor.rowcount > 0
            and race is not None
        ):
            _mark_independent_prediction_review(
                connection,
                race_key=str(
                    race["race_key"]
                ),
                evaluated_at=now,
            )

    return cursor.rowcount > 0


def get_database_summary() -> dict[str, int]:
    initialize_database()

    with get_connection() as connection:
        race_count = connection.execute(
            "SELECT COUNT(*) FROM races"
        ).fetchone()[0]

        completed_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM races
            WHERE result_status = '確定'
            """
        ).fetchone()[0]

        review_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM races
            WHERE result_status = '要確認'
            """
        ).fetchone()[0]

        independent_only_count = (
            connection.execute(
                """
                SELECT COUNT(*)
                FROM races
                WHERE odds_complete = 0
                """
            ).fetchone()[0]
        )

        odds_count = connection.execute(
            "SELECT COUNT(*) FROM odds"
        ).fetchone()[0]

        rider_count = connection.execute(
            "SELECT COUNT(*) FROM riders"
        ).fetchone()[0]

    return {
        "race_count": int(race_count),
        "completed_count": int(completed_count),
        "review_count": int(review_count),
        "independent_only_count": int(
            independent_only_count
        ),
        "odds_count": int(odds_count),
        "rider_count": int(rider_count),
    }


def get_recent_races(
    limit: int = 50,
) -> list[dict[str, Any]]:
    initialize_database()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                race_id,
                race_date,
                venue,
                race_number,
                race_title,
                rider_count,
                odds_complete,
                result_status,
                winning_combination,
                payout_per_100,
                review_reason,
                collected_at
            FROM races
            ORDER BY
                race_date DESC,
                venue,
                race_number DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


def get_unfinished_races(
    limit: int = 200,
) -> list[dict[str, Any]]:
    initialize_database()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                race_id,
                race_date,
                venue,
                race_number,
                race_url,
                race_title,
                rider_count,
                collected_at
            FROM races
            WHERE result_status = '未確定'
            ORDER BY
                race_date,
                venue,
                race_number
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


def get_race_car_numbers(
    race_id: str,
) -> list[int]:
    initialize_database()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT car_number
            FROM riders
            WHERE race_id = ?
            ORDER BY car_number
            """,
            (race_id,),
        ).fetchall()

    return [
        int(row["car_number"])
        for row in rows
    ]


def update_race_url(
    race_id: str,
    race_url: str,
) -> bool:
    initialize_database()

    normalized_url = str(
        race_url
    ).strip()

    if not normalized_url:
        return False

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE races
            SET
                race_url = ?,
                updated_at = ?
            WHERE race_id = ?
            """,
            (
                normalized_url,
                now,
                race_id,
            ),
        )

    return cursor.rowcount > 0


def get_race_by_identity(
    *,
    race_date: str,
    venue: str,
    race_number: int,
) -> dict[str, Any] | None:
    initialize_database()

    race_key = build_race_key(
        race_date,
        venue,
        race_number,
    )

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM races
            WHERE race_key = ?
            LIMIT 1
            """,
            (race_key,),
        ).fetchone()

    return (
        dict(row)
        if row is not None
        else None
    )


def update_race_urls_by_identity(
    *,
    race_date: str,
    venue: str,
    race_number: int,
    race_url: str = "",
    result_url: str = "",
) -> str | None:
    initialize_database()

    race_key = build_race_key(
        race_date,
        venue,
        race_number,
    )
    now = datetime.now().isoformat(
        timespec="seconds"
    )

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT race_id
            FROM races
            WHERE race_key = ?
            LIMIT 1
            """,
            (race_key,),
        ).fetchone()

        if row is None:
            return None

        race_id = str(row["race_id"])

        connection.execute(
            """
            UPDATE races
            SET
                race_url = CASE
                    WHEN TRIM(?) != ''
                    THEN ?
                    ELSE race_url
                END,
                result_url = CASE
                    WHEN TRIM(?) != ''
                    THEN ?
                    ELSE result_url
                END,
                updated_at = ?
            WHERE race_id = ?
            """,
            (
                str(race_url).strip(),
                str(race_url).strip(),
                str(result_url).strip(),
                str(result_url).strip(),
                now,
                race_id,
            ),
        )

    return race_id


def race_has_complete_learning_data(
    race_id: str,
) -> tuple[bool, str]:
    initialize_database()

    with get_connection() as connection:
        race = connection.execute(
            """
            SELECT odds_complete
            FROM races
            WHERE race_id = ?
            """,
            (race_id,),
        ).fetchone()

        if race is None:
            return False, "レースがありません。"

        riders = [
            {
                "車番": int(row["car_number"]),
            }
            for row in connection.execute(
                """
                SELECT car_number
                FROM riders
                WHERE race_id = ?
                ORDER BY car_number
                """,
                (race_id,),
            ).fetchall()
        ]

        odds_rows = [
            {
                "組番": str(row["combination"]),
                "オッズ": float(row["odds"]),
            }
            for row in connection.execute(
                """
                SELECT combination, odds
                FROM odds
                WHERE race_id = ?
                """,
                (race_id,),
            ).fetchall()
        ]

    complete, message = validate_complete_odds(
        riders,
        odds_rows,
    )

    return (
        bool(race["odds_complete"]) and complete,
        message,
    )


def race_has_enriched_learning_features(
    race_id: str,
) -> bool:
    initialize_database()

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT feature_version
            FROM races
            WHERE race_id = ?
            LIMIT 1
            """,
            (race_id,),
        ).fetchone()

    return bool(
        row is not None
        and safe_int(
            row["feature_version"],
            0,
        )
        >= 1
    )


def get_races_without_url(
    limit: int = 200,
) -> list[dict[str, Any]]:
    initialize_database()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                race_id,
                race_date,
                venue,
                race_number,
                race_title,
                race_url,
                result_status
            FROM races
            WHERE
                race_url IS NULL
                OR TRIM(race_url) = ''
            ORDER BY
                race_date DESC,
                venue,
                race_number
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]
