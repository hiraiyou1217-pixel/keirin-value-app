from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from race_metadata import (
    extract_race_conditions_from_riders,
)

SNAPSHOT_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "current_race_snapshot.json"
)


def _json_safe(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, (date, datetime)):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [
            _json_safe(item)
            for item in value
        ]

    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass

    return str(value)


def save_current_race_snapshot(
    *,
    odds_rows: list[dict[str, Any]],
    riders: list[dict[str, Any]],
    lineup_groups: list[list[int]],
    odds_logs: list[str],
    race_date: Any = "",
    venue: str = "",
    race_number: int = 0,
    race_url: str = "",
    race_title: str = "",
) -> None:
    SNAPSHOT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    odds_complete = any(
        str(log).strip()
        == "オッズデータ完全性: OK"
        for log in odds_logs
    )

    payload = {
        "saved_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "race_date": _json_safe(race_date),
        "venue": str(venue),
        "race_number": int(race_number or 0),
        "race_url": str(race_url),
        "race_title": str(race_title),
        "race_conditions": _json_safe(
            extract_race_conditions_from_riders(
                riders
            )
        ),
        "odds_rows": _json_safe(odds_rows),
        "riders": _json_safe(riders),
        "lineup_groups": _json_safe(
            lineup_groups
        ),
        "odds_logs": _json_safe(odds_logs),
        "odds_complete": odds_complete,
    }

    temporary_path = SNAPSHOT_PATH.with_suffix(
        ".json.tmp"
    )

    temporary_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(SNAPSHOT_PATH)


def load_current_race_snapshot() -> dict[str, Any]:
    if not SNAPSHOT_PATH.exists():
        return {}

    try:
        payload = json.loads(
            SNAPSHOT_PATH.read_text(
                encoding="utf-8"
            )
        )
    except (
        json.JSONDecodeError,
        OSError,
    ):
        return {}

    if not isinstance(payload, dict):
        return {}

    return payload


def resolve_prediction_context(
    snapshot: Mapping[str, Any],
    session_values: Mapping[str, Any],
    *,
    default_date: Any = "",
) -> dict[str, Any]:
    """
    予測対象の情報源を1つに固定する。

    JSONがある場合は、対象レース・選手・並びを
    すべて同じJSONから読み、古いセッション値と
    混在させない。JSONがない場合だけセッションを
    まとめて使用する。
    """
    if snapshot:
        return {
            "source": "snapshot",
            "saved_at": str(
                snapshot.get(
                    "saved_at",
                    "",
                )
            ),
            "race_date": snapshot.get(
                "race_date",
                default_date,
            ),
            "venue": str(
                snapshot.get(
                    "venue",
                    "",
                )
            ),
            "race_number": int(
                snapshot.get(
                    "race_number",
                    0,
                )
                or 0
            ),
            "race_url": str(
                snapshot.get(
                    "race_url",
                    "",
                )
            ),
            "race_title": str(
                snapshot.get(
                    "race_title",
                    "",
                )
            ),
            "race_conditions": dict(
                snapshot.get(
                    "race_conditions",
                    {},
                )
                or {}
            ),
            "riders": list(
                snapshot.get(
                    "riders",
                    [],
                )
                or []
            ),
            "lineup_groups": list(
                snapshot.get(
                    "lineup_groups",
                    [],
                )
                or []
            ),
            "odds_complete": bool(
                snapshot.get(
                    "odds_complete",
                    False,
                )
            ),
        }

    return {
        "source": "session",
        "saved_at": "",
        "race_date": session_values.get(
            "selected_date",
            default_date,
        ),
        "venue": str(
            session_values.get(
                "selected_venue",
                session_values.get(
                    "venue",
                    "",
                ),
            )
        ),
        "race_number": int(
            session_values.get(
                "selected_race_number",
                session_values.get(
                    "race_number",
                    0,
                ),
            )
            or 0
        ),
        "race_url": str(
            session_values.get(
                "selected_race_url",
                session_values.get(
                    "racecard_url",
                    "",
                ),
            )
        ),
        "race_title": str(
            session_values.get(
                "race_title",
                "",
            )
        ),
        "race_conditions": (
            extract_race_conditions_from_riders(
                list(
                    session_values.get(
                        "rider_data",
                        [],
                    )
                    or []
                )
            )
        ),
        "riders": list(
            session_values.get(
                "rider_data",
                [],
            )
            or []
        ),
        "lineup_groups": list(
            session_values.get(
                "lineup_groups",
                [],
            )
            or []
        ),
        "odds_complete": False,
    }
