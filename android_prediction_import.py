from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import learning_database
from learning_database import (
    canonical_venue_display,
    save_independent_prediction,
    sync_independent_prediction_results,
)


PREDICTION_FORMAT = (
    "keirin_android_prediction_v1"
)
FILE_PATTERN = "keirin_prediction_*.json"
MAXIMUM_FILE_BYTES = 20 * 1024 * 1024


class AndroidPredictionImportError(
    ValueError
):
    pass


@dataclass(frozen=True)
class PreparedPrediction:
    path: Path
    prediction_id: str
    predicted_at: str
    race_date: str
    venue: str
    race_number: int
    prediction_rows: list[
        dict[str, Any]
    ]
    model_metadata: dict[str, Any]
    input_snapshot: dict[str, Any]


def discover_google_drive_directories(
) -> list[Path]:
    home = Path.home()
    candidates: set[Path] = set()

    for drive_root in (
        home
        / "Library"
        / "CloudStorage"
    ).glob("GoogleDrive-*"):
        for drive_name in (
            "My Drive",
            "マイドライブ",
        ):
            candidate = (
                drive_root
                / drive_name
                / "KeirinAI"
            )

            if candidate.is_dir():
                candidates.add(
                    candidate.resolve()
                )

    for candidate in (
        home
        / "Google Drive"
        / "My Drive"
        / "KeirinAI",
        home
        / "Google Drive"
        / "マイドライブ"
        / "KeirinAI",
    ):
        if candidate.is_dir():
            candidates.add(
                candidate.resolve()
            )

    return sorted(
        candidates,
        key=lambda path: str(path),
    )


def _parse_prediction_datetime(
    value: Any,
) -> datetime:
    normalized = str(value or "").strip()

    if not normalized:
        raise AndroidPredictionImportError(
            "予測日時がありません。"
        )

    try:
        parsed = datetime.fromisoformat(
            normalized.replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError as exception:
        raise AndroidPredictionImportError(
            "予測日時の形式が不正です。"
        ) from exception

    if parsed.tzinfo is None:
        raise AndroidPredictionImportError(
            "予測日時にタイムゾーンが"
            "ありません。"
        )

    return parsed


def _car_numbers(
    payload: dict[str, Any],
) -> list[int]:
    riders = payload.get("riders")

    if not isinstance(riders, list):
        raise AndroidPredictionImportError(
            "選手別確率がありません。"
        )

    numbers: list[int] = []

    for rider in riders:
        if not isinstance(rider, dict):
            raise AndroidPredictionImportError(
                "選手別確率の形式が不正です。"
            )

        try:
            number = int(
                rider.get(
                    "car_number",
                    0,
                )
            )
        except (TypeError, ValueError):
            number = 0

        if number <= 0:
            raise AndroidPredictionImportError(
                "選手の車番が不正です。"
            )

        numbers.append(number)

    if (
        len(numbers) < 3
        or len(numbers) != len(set(numbers))
    ):
        raise AndroidPredictionImportError(
            "出走車番が不足または重複"
            "しています。"
        )

    return sorted(numbers)


def _prediction_rows(
    payload: dict[str, Any],
    car_numbers: list[int],
) -> list[dict[str, Any]]:
    combinations = payload.get(
        "combinations"
    )

    if not isinstance(combinations, list):
        raise AndroidPredictionImportError(
            "3連単予測がありません。"
        )

    expected = {
        f"{first}-{second}-{third}"
        for first in car_numbers
        for second in car_numbers
        for third in car_numbers
        if len(
            {
                first,
                second,
                third,
            }
        )
        == 3
    }
    acquired: set[str] = set()
    ranks: set[int] = set()
    rows: list[dict[str, Any]] = []
    probability_sum = 0.0

    for source in combinations:
        if not isinstance(source, dict):
            raise AndroidPredictionImportError(
                "3連単予測行の形式が不正です。"
            )

        combination = str(
            source.get(
                "combination",
                "",
            )
        ).strip()

        try:
            rank = int(source.get("rank", 0))
            probability = float(
                source.get(
                    "probability",
                    0.0,
                )
            )
        except (TypeError, ValueError) as exception:
            raise AndroidPredictionImportError(
                "3連単順位または確率が不正です。"
            ) from exception

        if combination not in expected:
            raise AndroidPredictionImportError(
                "出走車番と一致しない"
                f"組番です: {combination}"
            )

        if combination in acquired:
            raise AndroidPredictionImportError(
                "重複した3連単組番です: "
                + combination
            )

        if (
            rank <= 0
            or rank > len(expected)
            or rank in ranks
        ):
            raise AndroidPredictionImportError(
                "3連単予測順位が重複または"
                "範囲外です。"
            )

        if (
            not math.isfinite(probability)
            or probability <= 0.0
            or probability > 1.0
        ):
            raise AndroidPredictionImportError(
                "3連単AI確率が不正です: "
                + combination
            )

        acquired.add(combination)
        ranks.add(rank)
        probability_sum += probability
        rows.append(
            {
                "combination": combination,
                "predicted_rank": rank,
                "ai_probability": probability,
            }
        )

    missing = expected - acquired

    if missing:
        preview = "、".join(
            sorted(missing)[:10]
        )
        raise AndroidPredictionImportError(
            f"3連単予測が{len(missing)}組"
            f"不足しています: {preview}"
        )

    if ranks != set(
        range(1, len(expected) + 1)
    ):
        raise AndroidPredictionImportError(
            "3連単予測順位が連続していません。"
        )

    if not math.isclose(
        probability_sum,
        1.0,
        rel_tol=1e-9,
        abs_tol=1e-9,
    ):
        raise AndroidPredictionImportError(
            "3連単AI確率の合計が"
            "1ではありません。"
        )

    rows.sort(
        key=lambda row: int(
            row["predicted_rank"]
        )
    )
    return rows


def prepare_prediction_file(
    path: Path,
) -> PreparedPrediction:
    path = path.expanduser().resolve()

    if not path.is_file():
        raise AndroidPredictionImportError(
            "予測ファイルがありません。"
        )

    if path.stat().st_size > MAXIMUM_FILE_BYTES:
        raise AndroidPredictionImportError(
            "予測ファイルが大きすぎます。"
        )

    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exception:
        raise AndroidPredictionImportError(
            "JSONを読み込めません。"
        ) from exception

    if not isinstance(payload, dict):
        raise AndroidPredictionImportError(
            "予測JSONの形式が不正です。"
        )

    if (
        payload.get("format")
        != PREDICTION_FORMAT
    ):
        raise AndroidPredictionImportError(
            "対応していない予測形式です。"
        )

    prediction_id = str(
        payload.get(
            "prediction_id",
            "",
        )
    ).strip()

    if not prediction_id:
        raise AndroidPredictionImportError(
            "予測IDがありません。"
        )

    predicted_at = str(
        payload.get(
            "predicted_at",
            "",
        )
    ).strip()
    _parse_prediction_datetime(
        predicted_at
    )
    target = payload.get("target")

    if not isinstance(target, dict):
        raise AndroidPredictionImportError(
            "予測対象がありません。"
        )

    race_date = str(
        target.get("race_date", "")
    )[:10]

    try:
        date.fromisoformat(race_date)
    except ValueError as exception:
        raise AndroidPredictionImportError(
            "開催日の形式が不正です。"
        ) from exception

    venue = canonical_venue_display(
        target.get("venue", "")
    )

    try:
        race_number = int(
            target.get(
                "race_number",
                0,
            )
        )
    except (TypeError, ValueError):
        race_number = 0

    if not venue:
        raise AndroidPredictionImportError(
            "競輪場がありません。"
        )

    if not 1 <= race_number <= 12:
        raise AndroidPredictionImportError(
            "R番号が範囲外です。"
        )

    car_numbers = _car_numbers(payload)
    rows = _prediction_rows(
        payload,
        car_numbers,
    )
    model_metadata = payload.get("model")

    if not isinstance(
        model_metadata,
        dict,
    ):
        raise AndroidPredictionImportError(
            "モデル情報がありません。"
        )

    model_metadata = dict(model_metadata)
    model_metadata[
        "prediction_count"
    ] = len(rows)
    input_snapshot = payload.get(
        "input_snapshot"
    )

    if not isinstance(
        input_snapshot,
        dict,
    ):
        input_snapshot = {}
    else:
        input_snapshot = dict(
            input_snapshot
        )

    if not isinstance(
        input_snapshot.get("riders"),
        list,
    ):
        input_snapshot["riders"] = [
            {
                "車番": int(
                    rider["car_number"]
                ),
                "選手名": str(
                    rider.get("name", "")
                ),
            }
            for rider in payload["riders"]
        ]

    input_snapshot[
        "source_prediction_id"
    ] = prediction_id
    input_snapshot[
        "source_device"
    ] = str(
        payload.get(
            "source_device",
            "android",
        )
    )
    input_snapshot[
        "mobile_predicted_at"
    ] = predicted_at

    return PreparedPrediction(
        path=path,
        prediction_id=prediction_id,
        predicted_at=predicted_at,
        race_date=race_date,
        venue=venue,
        race_number=race_number,
        prediction_rows=rows,
        model_metadata=model_metadata,
        input_snapshot=input_snapshot,
    )


def import_android_predictions(
    source_directory: Path,
) -> dict[str, Any]:
    source = (
        Path(source_directory)
        .expanduser()
        .resolve()
    )

    if not source.is_dir():
        raise FileNotFoundError(
            "スマホ予測フォルダが"
            f"ありません: {source}"
        )

    paths = sorted(
        path
        for path in source.rglob(
            FILE_PATTERN
        )
        if path.is_file()
    )
    prepared: list[PreparedPrediction] = []
    failures: list[dict[str, str]] = []

    for path in paths:
        try:
            prepared.append(
                prepare_prediction_file(path)
            )
        except Exception as exception:
            failures.append(
                {
                    "file": str(path),
                    "error": (
                        f"{type(exception).__name__}: "
                        f"{exception}"
                    ),
                }
            )

    prepared.sort(
        key=lambda item: (
            _parse_prediction_datetime(
                item.predicted_at
            ),
            item.prediction_id,
        )
    )
    imported = 0
    duplicates = 0
    records: list[dict[str, Any]] = []

    for item in prepared:
        try:
            result = save_independent_prediction(
                race_date=item.race_date,
                venue=item.venue,
                race_number=(
                    item.race_number
                ),
                prediction_rows=(
                    item.prediction_rows
                ),
                model_metadata=(
                    item.model_metadata
                ),
                input_snapshot=(
                    item.input_snapshot
                ),
                predicted_at=(
                    item.predicted_at
                ),
                result_known_at_prediction=(
                    False
                ),
            )
            created = bool(
                result.get("created")
            )

            if created:
                imported += 1
            else:
                duplicates += 1

            records.append(
                {
                    "prediction_id": (
                        item.prediction_id
                    ),
                    "race_date": (
                        item.race_date
                    ),
                    "venue": item.venue,
                    "race_number": (
                        item.race_number
                    ),
                    "created": created,
                    "run_id": str(
                        result.get(
                            "run_id",
                            "",
                        )
                    ),
                    "evaluation_eligible": (
                        bool(
                            result.get(
                                "evaluation_eligible"
                            )
                        )
                    ),
                    "eligibility_reason": str(
                        result.get(
                            "eligibility_reason",
                            "",
                        )
                        or ""
                    ),
                }
            )
        except Exception as exception:
            failures.append(
                {
                    "file": str(item.path),
                    "error": (
                        f"{type(exception).__name__}: "
                        f"{exception}"
                    ),
                }
            )

    synchronized = (
        sync_independent_prediction_results()
    )
    return {
        "source_directory": str(source),
        "file_count": len(paths),
        "validated_count": len(prepared),
        "imported_count": imported,
        "duplicate_count": duplicates,
        "failed_count": len(failures),
        "synchronized_race_count": (
            synchronized
        ),
        "records": records,
        "failures": failures,
        "database_path": str(
            learning_database.DATABASE_PATH
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Galaxy版オッズ非依存AIの"
            "予測JSONを学習SQLiteへ"
            "安全に取り込みます。"
        )
    )
    parser.add_argument(
        "source",
        nargs="?",
        help=(
            "Google Drive上の"
            "KeirinAIフォルダ"
        ),
    )
    parser.add_argument(
        "--database",
        type=Path,
        help="取込先SQLite",
    )
    arguments = parser.parse_args()

    if arguments.database:
        learning_database.DATABASE_PATH = (
            arguments.database
            .expanduser()
            .resolve()
        )

    if arguments.source:
        source = Path(arguments.source)
    else:
        discovered = (
            discover_google_drive_directories()
        )

        if len(discovered) != 1:
            print(
                "Google DriveのKeirinAI"
                "フォルダを1つに特定"
                "できませんでした。"
            )

            for path in discovered:
                print(f"- {path}")

            return 2

        source = discovered[0]

    try:
        result = import_android_predictions(
            source
        )
    except Exception as exception:
        print(
            f"{type(exception).__name__}: "
            f"{exception}"
        )
        return 1

    print(
        "スマホ予測取込: "
        f"新規{result['imported_count']}件 / "
        f"重複{result['duplicate_count']}件 / "
        f"失敗{result['failed_count']}件 / "
        "結果照合"
        f"{result['synchronized_race_count']}レース"
    )

    for failure in result["failures"]:
        print(
            f"- {failure['file']}: "
            f"{failure['error']}"
        )

    return (
        1
        if result["failed_count"]
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
