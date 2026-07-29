from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


DATABASE_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "keirin_learning.db"
)


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


def initialize_database() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS races (
                race_id TEXT PRIMARY KEY,
                race_date TEXT NOT NULL,
                venue TEXT NOT NULL,
                race_number INTEGER NOT NULL,
                race_url TEXT,
                race_title TEXT,
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
                payout_per_100 INTEGER
            );

            CREATE TABLE IF NOT EXISTS riders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id TEXT NOT NULL,
                car_number INTEGER NOT NULL,
                rider_name TEXT,
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
            """
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
    source = "|".join(
        [
            str(race_date),
            str(venue),
            str(race_number),
            str(race_url),
        ]
    )

    digest = hashlib.sha256(
        source.encode("utf-8")
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
) -> str:
    initialize_database()

    race_id = build_race_id(
        race_date,
        venue,
        race_number,
        race_url,
    )

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    lineup_metadata = build_lineup_metadata(
        lineup_groups
    )

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO races (
                race_id,
                race_date,
                venue,
                race_number,
                race_url,
                race_title,
                rider_count,
                lineup_json,
                odds_complete,
                collected_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(race_id) DO UPDATE SET
                race_title = excluded.race_title,
                rider_count = excluded.rider_count,
                lineup_json = excluded.lineup_json,
                odds_complete = excluded.odds_complete,
                updated_at = excluded.updated_at
            """,
            (
                race_id,
                race_date,
                venue,
                int(race_number),
                race_url,
                race_title,
                len(riders),
                json.dumps(
                    lineup_groups,
                    ensure_ascii=False,
                ),
                1 if odds_complete else 0,
                now,
                now,
            ),
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
                    ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(
                    race_id,
                    car_number
                ) DO UPDATE SET
                    rider_name =
                        excluded.rider_name,
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

    return race_id


def save_race_result(
    *,
    race_id: str,
    first_place: int,
    second_place: int,
    third_place: int,
    payout_per_100: int | None = None,
) -> None:
    initialize_database()

    winning_combination = (
        f"{int(first_place)}-"
        f"{int(second_place)}-"
        f"{int(third_place)}"
    )

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    with get_connection() as connection:
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
                updated_at = ?
            WHERE race_id = ?
            """,
            (
                int(first_place),
                int(second_place),
                int(third_place),
                winning_combination,
                payout_per_100,
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

        odds_count = connection.execute(
            "SELECT COUNT(*) FROM odds"
        ).fetchone()[0]

        rider_count = connection.execute(
            "SELECT COUNT(*) FROM riders"
        ).fetchone()[0]

    return {
        "race_count": int(race_count),
        "completed_count": int(completed_count),
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
