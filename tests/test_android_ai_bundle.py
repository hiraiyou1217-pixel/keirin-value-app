from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
)

from export_android_ai_bundle import (
    DATABASE_FILENAME,
    MANIFEST_FILENAME,
    MODEL_FILENAME,
    create_android_ai_bundle,
)
from portable_independent_model import (
    export_hist_gradient_boosting_package,
    predict_positive_probabilities,
)


def _fitted_package() -> dict[str, object]:
    rows = np.asarray(
        [
            [0.0, 1.0],
            [1.0, 2.0],
            [2.0, 1.0],
            [3.0, 3.0],
            [np.nan, 0.0],
            [4.0, 2.0],
        ]
        * 30,
        dtype=float,
    )
    target = np.asarray(
        [0, 0, 0, 1, 0, 1] * 30,
        dtype=int,
    )
    model = HistGradientBoostingClassifier(
        max_iter=8,
        max_leaf_nodes=4,
        min_samples_leaf=2,
        learning_rate=0.05,
        early_stopping=False,
        random_state=42,
    ).fit(rows, target)

    return {
        "model": model,
        "model_version": 3,
        "model_type": (
            "odds_independent_trifecta"
        ),
        "odds_independent": True,
        "feature_columns": ["first", "second"],
        "trained_at": "2026-07-30T17:06:00",
        "training_start_date": "2026-07-01",
        "training_end_date": "2026-07-29",
        "training_cutoff_date": "2026-07-29",
        "race_count": 10,
        "row_count": 100,
    }


class PortableModelTest(unittest.TestCase):
    def test_matches_sklearn_probability(
        self,
    ) -> None:
        package = _fitted_package()
        portable = (
            export_hist_gradient_boosting_package(
                package
            )
        )
        rows = np.asarray(
            [
                [0.0, 1.0],
                [3.1, 2.7],
                [np.nan, 0.0],
                [-5.0, np.nan],
            ]
        )
        expected = package[
            "model"
        ].predict_proba(rows)[:, 1]
        actual = np.asarray(
            predict_positive_probabilities(
                portable,
                rows,
            )
        )

        np.testing.assert_allclose(
            actual,
            expected,
            rtol=1e-12,
            atol=1e-12,
        )

    def test_creates_verified_private_zip(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            model_path = directory / "model.joblib"
            database_path = directory / "learning.db"
            output_path = directory / "bundle.zip"
            joblib.dump(
                _fitted_package(),
                model_path,
            )

            with sqlite3.connect(
                database_path
            ) as connection:
                connection.executescript(
                    """
                    CREATE TABLE races (
                        race_date TEXT
                    );
                    CREATE TABLE riders (
                        rider_name TEXT
                    );
                    INSERT INTO races VALUES
                        ('2026-07-29');
                    INSERT INTO riders VALUES
                        ('検証選手');
                    PRAGMA user_version=7;
                    """
                )

            result = create_android_ai_bundle(
                model_path=model_path,
                database_path=database_path,
                output_path=output_path,
            )

            self.assertEqual(
                result["validation"]["status"],
                "ok",
            )
            self.assertTrue(output_path.exists())

            with zipfile.ZipFile(
                output_path
            ) as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {
                        MANIFEST_FILENAME,
                        MODEL_FILENAME,
                        DATABASE_FILENAME,
                    },
                )
                manifest = json.loads(
                    archive.read(
                        MANIFEST_FILENAME
                    )
                )

            self.assertEqual(
                manifest["database"][
                    "integrity_check"
                ],
                "ok",
            )
            self.assertEqual(
                manifest["database"][
                    "schema_version"
                ],
                7,
            )
            self.assertLessEqual(
                manifest["validation"][
                    "maximum_absolute_error"
                ],
                1e-12,
            )


if __name__ == "__main__":
    unittest.main()
