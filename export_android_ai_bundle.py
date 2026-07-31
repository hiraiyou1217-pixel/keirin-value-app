from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from learning_database import DATABASE_PATH
from portable_independent_model import (
    apply_probability_calibration,
    export_hist_gradient_boosting_package,
    predict_positive_probabilities,
)
from train_independent_model import (
    INDEPENDENT_MODEL_PATH,
)


ROOT_DIRECTORY = Path(__file__).resolve().parent
DEFAULT_OUTPUT_PATH = (
    ROOT_DIRECTORY
    / "exports"
    / "keirin_android_ai_bundle.zip"
)
BUNDLE_FORMAT = "keirin_android_ai_bundle_v1"
MODEL_FILENAME = "portable_model.json"
DATABASE_FILENAME = "keirin_learning.db"
MANIFEST_FILENAME = "bundle_manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as source:
        for chunk in iter(
            lambda: source.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _database_integrity(path: Path) -> dict[str, Any]:
    uri = f"{path.resolve().as_uri()}?mode=ro"

    with sqlite3.connect(
        uri,
        uri=True,
    ) as connection:
        integrity = str(
            connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        if integrity.lower() != "ok":
            raise RuntimeError(
                "SQLite整合性NG: " + integrity
            )

        tables = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            )
        }
        missing = {"races", "riders"} - tables

        if missing:
            raise RuntimeError(
                "学習DBに必要なテーブルが"
                "ありません: "
                + "、".join(sorted(missing))
            )

        race_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM races"
            ).fetchone()[0]
        )
        rider_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM riders"
            ).fetchone()[0]
        )
        date_range = connection.execute(
            """
            SELECT
                MIN(race_date),
                MAX(race_date)
            FROM races
            """
        ).fetchone()
        schema_version = int(
            connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]
        )

    return {
        "integrity_check": "ok",
        "schema_version": schema_version,
        "race_count": race_count,
        "rider_count": rider_count,
        "first_race_date": str(
            date_range[0] or ""
        ),
        "last_race_date": str(
            date_range[1] or ""
        ),
    }


def backup_sqlite(
    source_path: Path,
    destination_path: Path,
) -> dict[str, Any]:
    _database_integrity(source_path)
    source_uri = (
        f"{source_path.resolve().as_uri()}"
        "?mode=ro"
    )

    with sqlite3.connect(
        source_uri,
        uri=True,
    ) as source:
        with sqlite3.connect(
            destination_path
        ) as destination:
            source.backup(destination)

    return _database_integrity(
        destination_path
    )


def _validation_rows(
    portable_model: dict[str, Any],
    *,
    maximum_rows: int = 4096,
) -> np.ndarray:
    feature_count = int(
        portable_model["feature_count"]
    )
    rows: list[np.ndarray] = [
        np.zeros(feature_count, dtype=float),
        np.ones(feature_count, dtype=float),
        np.full(feature_count, -1.0),
        np.full(feature_count, np.nan),
    ]
    threshold_cases: list[
        tuple[int, float]
    ] = []

    for tree in portable_model["trees"]:
        for node in tree:
            if bool(node[6]):
                continue

            threshold_cases.append(
                (
                    int(node[1]),
                    float(node[2]),
                )
            )

    threshold_cases = list(
        dict.fromkeys(threshold_cases)
    )
    threshold_row_limit = max(
        0,
        maximum_rows - len(rows) - 512,
    )
    threshold_case_limit = (
        threshold_row_limit // 3
    )

    if (
        threshold_case_limit
        and len(threshold_cases)
        > threshold_case_limit
    ):
        positions = np.linspace(
            0,
            len(threshold_cases) - 1,
            threshold_case_limit,
            dtype=int,
        )
        threshold_cases = [
            threshold_cases[int(position)]
            for position in positions
        ]

    for feature_index, threshold in threshold_cases:
        for value in (
            np.nextafter(
                threshold,
                -np.inf,
            ),
            threshold,
            np.nextafter(
                threshold,
                np.inf,
            ),
        ):
            row = np.zeros(
                feature_count,
                dtype=float,
            )
            row[feature_index] = value
            rows.append(row)

    rng = np.random.default_rng(20260731)
    random_count = max(
        0,
        min(
            512,
            maximum_rows - len(rows),
        ),
    )

    if random_count:
        random_rows = rng.normal(
            0.0,
            5.0,
            size=(
                random_count,
                feature_count,
            ),
        )
        missing_mask = rng.random(
            random_rows.shape
        ) < 0.02
        random_rows[missing_mask] = np.nan
        rows.extend(random_rows)

    return np.asarray(
        rows[:maximum_rows],
        dtype=float,
    )


def validate_portable_model(
    package: dict[str, Any],
    portable_model: dict[str, Any],
) -> dict[str, Any]:
    rows = _validation_rows(portable_model)
    expected = np.asarray(
        apply_probability_calibration(
            package["model"].predict_proba(
                rows
            )[:, 1],
            package.get(
                "probability_calibration"
            ),
        ),
        dtype=float,
    )
    actual = np.asarray(
        predict_positive_probabilities(
            portable_model,
            rows,
        ),
        dtype=float,
    )
    maximum_error = float(
        np.abs(
            expected - actual
        ).max(initial=0.0)
    )

    if not np.allclose(
        expected,
        actual,
        rtol=1e-12,
        atol=1e-12,
    ):
        raise RuntimeError(
            "端末モデル変換後の確率が"
            "Mac版と一致しません。"
            f" 最大差={maximum_error:.3e}"
        )

    return {
        "status": "ok",
        "sample_count": int(len(rows)),
        "maximum_absolute_error": (
            maximum_error
        ),
        "relative_tolerance": 1e-12,
        "absolute_tolerance": 1e-12,
    }


def _file_manifest(path: Path) -> dict[str, Any]:
    return {
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def create_android_ai_bundle(
    *,
    model_path: Path = INDEPENDENT_MODEL_PATH,
    database_path: Path = DATABASE_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> dict[str, Any]:
    if not model_path.exists():
        raise FileNotFoundError(
            "学習済みモデルがありません: "
            + str(model_path)
        )

    if not database_path.exists():
        raise FileNotFoundError(
            "学習DBがありません: "
            + str(database_path)
        )

    package = joblib.load(model_path)
    portable_model = (
        export_hist_gradient_boosting_package(
            package
        )
    )
    validation = validate_portable_model(
        package,
        portable_model,
    )
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with tempfile.TemporaryDirectory(
        prefix="keirin-android-bundle-"
    ) as temporary_name:
        temporary = Path(temporary_name)
        model_output = (
            temporary / MODEL_FILENAME
        )
        database_output = (
            temporary / DATABASE_FILENAME
        )
        manifest_output = (
            temporary / MANIFEST_FILENAME
        )
        model_output.write_text(
            json.dumps(
                portable_model,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ),
            encoding="utf-8",
        )
        database_summary = backup_sqlite(
            database_path,
            database_output,
        )
        manifest = {
            "format": BUNDLE_FORMAT,
            "bundle_version": 1,
            "created_at": datetime.now()
            .astimezone()
            .isoformat(timespec="seconds"),
            "odds_independent": True,
            "model": portable_model[
                "metadata"
            ],
            "database": database_summary,
            "validation": validation,
            "files": {
                MODEL_FILENAME: _file_manifest(
                    model_output
                ),
                DATABASE_FILENAME: (
                    _file_manifest(
                        database_output
                    )
                ),
            },
        }
        manifest_output.write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            ),
            encoding="utf-8",
        )
        temporary_zip = output_path.with_suffix(
            output_path.suffix + ".tmp"
        )

        with zipfile.ZipFile(
            temporary_zip,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            for path in (
                manifest_output,
                model_output,
                database_output,
            ):
                archive.write(
                    path,
                    arcname=path.name,
                )

        os.replace(
            temporary_zip,
            output_path,
        )

    return {
        **manifest,
        "output_path": str(
            output_path.resolve()
        ),
        "zip_size_bytes": (
            output_path.stat().st_size
        ),
        "zip_sha256": sha256_file(
            output_path
        ),
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Galaxy版オッズ非依存AIへ"
            "取り込む非公開ZIPを作成します。"
        )
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=INDEPENDENT_MODEL_PATH,
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DATABASE_PATH,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
    )
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    result = create_android_ai_bundle(
        model_path=arguments.model,
        database_path=arguments.database,
        output_path=arguments.output,
    )
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
