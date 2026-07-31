from __future__ import annotations

import itertools
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import google_drive_prediction_import
import learning_database


class GoogleDrivePredictionImportTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.temporary = (
            tempfile.TemporaryDirectory()
        )
        self.temporary_path = Path(
            self.temporary.name
        )
        self.original_database_path = (
            learning_database.DATABASE_PATH
        )
        learning_database.DATABASE_PATH = (
            self.temporary_path
            / "learning.db"
        )
        learning_database.initialize_database()

    def tearDown(self) -> None:
        learning_database.DATABASE_PATH = (
            self.original_database_path
        )
        self.temporary.cleanup()

    def payload(
        self,
    ) -> dict[str, object]:
        car_numbers = [1, 2, 3, 4, 5]
        combinations = list(
            itertools.permutations(
                car_numbers,
                3,
            )
        )
        probability = 1.0 / len(
            combinations
        )
        return {
            "format": (
                "keirin_android_prediction_v1"
            ),
            "prediction_id": (
                "drive-prediction-001"
            ),
            "predicted_at": (
                "2026-07-31T08:00:00+09:00"
            ),
            "source_device": "android",
            "target": {
                "race_date": "2026-07-31",
                "venue": "青森競輪",
                "race_number": 1,
            },
            "combinations": [
                {
                    "combination": "-".join(
                        str(number)
                        for number in combination
                    ),
                    "rank": rank,
                    "probability": probability,
                }
                for rank, combination in enumerate(
                    combinations,
                    start=1,
                )
            ],
            "riders": [
                {
                    "car_number": number,
                    "name": f"選手{number}",
                }
                for number in car_numbers
            ],
            "model": {
                "model_version": 3,
                "trained_at": (
                    "2026-07-30T20:00:00"
                ),
                "training_start_date": (
                    "2026-01-01"
                ),
                "training_end_date": (
                    "2026-07-30"
                ),
                "training_cutoff_date": (
                    "2026-07-30"
                ),
            },
            "input_snapshot": {
                "riders": [
                    {
                        "車番": number,
                        "選手名": (
                            f"選手{number}"
                        ),
                    }
                    for number in car_numbers
                ],
                "race_conditions": {
                    "発走時刻": "10:00",
                },
            },
        }

    def test_extracts_folder_id(
        self,
    ) -> None:
        folder_id = (
            "1AbCdEfGhIjKlMnOpQrStUv"
        )

        self.assertEqual(
            (
                google_drive_prediction_import
                .extract_google_drive_folder_id(
                    folder_id
                )
            ),
            folder_id,
        )
        self.assertEqual(
            (
                google_drive_prediction_import
                .extract_google_drive_folder_id(
                    "https://drive.google.com/"
                    f"drive/folders/{folder_id}"
                    "?usp=drive_link"
                )
            ),
            folder_id,
        )
        self.assertEqual(
            (
                google_drive_prediction_import
                .extract_google_drive_folder_id(
                    "https://drive.google.com/"
                    f"open?id={folder_id}"
                )
            ),
            folder_id,
        )

        with self.assertRaisesRegex(
            (
                google_drive_prediction_import
                .GoogleDrivePredictionImportError
            ),
            "URL",
        ):
            (
                google_drive_prediction_import
                .extract_google_drive_folder_id(
                    "not a drive folder"
                )
            )

    def test_saves_desktop_oauth_config(
        self,
    ) -> None:
        client_path = (
            self.temporary_path
            / "google_drive"
            / "oauth_client.json"
        )
        token_path = (
            self.temporary_path
            / "google_drive"
            / "oauth_token.json"
        )
        payload = {
            "installed": {
                "client_id": "client-id",
                "client_secret": "secret",
                "auth_uri": (
                    "https://accounts.google.com/"
                    "o/oauth2/auth"
                ),
                "token_uri": (
                    "https://oauth2.googleapis.com/"
                    "token"
                ),
            }
        }

        with (
            patch.object(
                google_drive_prediction_import,
                "GOOGLE_DRIVE_CLIENT_PATH",
                client_path,
            ),
            patch.object(
                google_drive_prediction_import,
                "GOOGLE_DRIVE_TOKEN_PATH",
                token_path,
            ),
        ):
            (
                google_drive_prediction_import
                .save_google_drive_client_config(
                    json.dumps(payload).encode(
                        "utf-8"
                    )
                )
            )
            status = (
                google_drive_prediction_import
                .google_drive_connection_status()
            )

        self.assertTrue(
            status["client_configured"]
        )
        self.assertFalse(status["authorized"])
        self.assertEqual(
            (
                json.loads(
                    client_path.read_text(
                        encoding="utf-8"
                    )
                )
            ),
            payload,
        )
        self.assertEqual(
            client_path.stat().st_mode & 0o777,
            0o600,
        )

    def test_rejects_web_oauth_config(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            (
                google_drive_prediction_import
                .GoogleDrivePredictionImportError
            ),
            "デスクトップアプリ",
        ):
            (
                google_drive_prediction_import
                .save_google_drive_client_config(
                    json.dumps(
                        {
                            "web": {
                                "client_id": (
                                    "wrong-type"
                                )
                            }
                        }
                    ).encode("utf-8")
                )
            )

    def test_imports_downloaded_drive_file(
        self,
    ) -> None:
        metadata = {
            "id": "drive-file-id-001",
            "name": (
                "keirin_prediction_001.json"
            ),
            "size": "1000",
            "modifiedTime": (
                "2026-07-31T08:01:00Z"
            ),
        }

        def fake_download(
            _service: object,
            _files: list[dict[str, object]],
            destination: Path,
        ) -> dict[str, object]:
            output_directory = (
                destination
                / "drive-file-id-001"
            )
            output_directory.mkdir(
                parents=True
            )
            (
                output_directory
                / metadata["name"]
            ).write_text(
                json.dumps(
                    self.payload(),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return {
                "downloaded_count": 1,
                "failures": [],
            }

        with (
            patch.object(
                google_drive_prediction_import,
                "_build_drive_service",
                return_value=object(),
            ),
            patch.object(
                google_drive_prediction_import,
                "resolve_keirin_ai_folder",
                return_value={
                    "id": "drive-folder-id",
                    "name": "KeirinAI",
                },
            ),
            patch.object(
                google_drive_prediction_import,
                "list_prediction_files",
                return_value=[metadata],
            ),
            patch.object(
                google_drive_prediction_import,
                "download_prediction_files",
                side_effect=fake_download,
            ),
        ):
            first = (
                google_drive_prediction_import
                .import_google_drive_predictions()
            )
            second = (
                google_drive_prediction_import
                .import_google_drive_predictions()
            )

        self.assertEqual(
            first["remote_file_count"],
            1,
        )
        self.assertEqual(
            first["downloaded_count"],
            1,
        )
        self.assertEqual(
            first["imported_count"],
            1,
        )
        self.assertEqual(
            second["duplicate_count"],
            1,
        )
        self.assertEqual(
            first["failed_count"],
            0,
        )


if __name__ == "__main__":
    unittest.main()
