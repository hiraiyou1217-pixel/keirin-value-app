from __future__ import annotations

import io
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from android_prediction_import import (
    MAXIMUM_FILE_BYTES,
    import_android_predictions,
)


APP_DIRECTORY = Path(__file__).resolve().parent
GOOGLE_DRIVE_CONFIG_DIRECTORY = (
    APP_DIRECTORY / "data" / "google_drive"
)
GOOGLE_DRIVE_CLIENT_PATH = (
    GOOGLE_DRIVE_CONFIG_DIRECTORY
    / "oauth_client.json"
)
GOOGLE_DRIVE_TOKEN_PATH = (
    GOOGLE_DRIVE_CONFIG_DIRECTORY
    / "oauth_token.json"
)
GOOGLE_DRIVE_SCOPE = (
    "https://www.googleapis.com/auth/"
    "drive.readonly"
)
GOOGLE_DRIVE_SCOPES = [GOOGLE_DRIVE_SCOPE]
GOOGLE_DRIVE_FOLDER_MIME_TYPE = (
    "application/vnd.google-apps.folder"
)
MAXIMUM_FOLDER_COUNT = 1000
FOLDER_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9_-]{10,}$"
)


class GoogleDrivePredictionImportError(
    RuntimeError
):
    pass


class GoogleDriveAuthorizationRequired(
    GoogleDrivePredictionImportError
):
    pass


def _google_imports() -> dict[str, Any]:
    try:
        from google.auth.transport.requests import (
            Request,
        )
        from google.oauth2.credentials import (
            Credentials,
        )
        from google_auth_oauthlib.flow import (
            InstalledAppFlow,
        )
        from googleapiclient.discovery import (
            build,
        )
        from googleapiclient.http import (
            MediaIoBaseDownload,
        )
    except ImportError as exception:
        raise GoogleDrivePredictionImportError(
            "Google Drive接続ライブラリが"
            "ありません。install.commandを"
            "もう一度実行してください。"
        ) from exception

    return {
        "Request": Request,
        "Credentials": Credentials,
        "InstalledAppFlow": (
            InstalledAppFlow
        ),
        "build": build,
        "MediaIoBaseDownload": (
            MediaIoBaseDownload
        ),
    }


def _write_private_text(
    path: Path,
    text: str,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )
    temporary.write_text(
        text,
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def save_google_drive_client_config(
    content: bytes,
) -> Path:
    if len(content) > 1024 * 1024:
        raise GoogleDrivePredictionImportError(
            "OAuthクライアントJSONが"
            "大きすぎます。"
        )

    try:
        payload = json.loads(
            content.decode("utf-8")
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exception:
        raise GoogleDrivePredictionImportError(
            "OAuthクライアントJSONを"
            "読み込めません。"
        ) from exception

    installed = (
        payload.get("installed")
        if isinstance(payload, dict)
        else None
    )

    if not isinstance(installed, dict):
        raise GoogleDrivePredictionImportError(
            "「デスクトップアプリ」用の"
            "OAuthクライアントJSONでは"
            "ありません。"
        )

    required = (
        "client_id",
        "client_secret",
        "auth_uri",
        "token_uri",
    )
    missing = [
        name
        for name in required
        if not str(
            installed.get(name, "")
        ).strip()
    ]

    if missing:
        raise GoogleDrivePredictionImportError(
            "OAuthクライアントJSONに"
            "必要な項目がありません: "
            + "、".join(missing)
        )

    normalized = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )
    _write_private_text(
        GOOGLE_DRIVE_CLIENT_PATH,
        normalized,
    )
    return GOOGLE_DRIVE_CLIENT_PATH


def google_drive_connection_status(
) -> dict[str, Any]:
    return {
        "client_configured": (
            GOOGLE_DRIVE_CLIENT_PATH.is_file()
        ),
        "authorized": (
            GOOGLE_DRIVE_TOKEN_PATH.is_file()
        ),
        "client_path": str(
            GOOGLE_DRIVE_CLIENT_PATH
        ),
        "token_path": str(
            GOOGLE_DRIVE_TOKEN_PATH
        ),
    }


def disconnect_google_drive() -> bool:
    if not GOOGLE_DRIVE_TOKEN_PATH.exists():
        return False

    GOOGLE_DRIVE_TOKEN_PATH.unlink()
    return True


def _load_google_credentials(
    *,
    interactive: bool,
) -> Any:
    google = _google_imports()
    credentials = None

    if GOOGLE_DRIVE_TOKEN_PATH.is_file():
        try:
            credentials = google[
                "Credentials"
            ].from_authorized_user_file(
                str(GOOGLE_DRIVE_TOKEN_PATH),
                GOOGLE_DRIVE_SCOPES,
            )
        except Exception as exception:
            raise GoogleDrivePredictionImportError(
                "保存済みのGoogle認証情報を"
                "読み込めません。接続を解除して"
                "認証し直してください。"
            ) from exception

    if (
        credentials
        and credentials.expired
        and credentials.refresh_token
    ):
        try:
            credentials.refresh(
                google["Request"]()
            )
        except Exception as exception:
            if not interactive:
                raise (
                    GoogleDriveAuthorizationRequired(
                        "Google認証の有効期限が"
                        "切れました。再接続して"
                        "ください。"
                    )
                ) from exception
            credentials = None

    if not credentials or not credentials.valid:
        if not interactive:
            raise GoogleDriveAuthorizationRequired(
                "Google Driveへ未接続です。"
                "先に「Googleアカウントへ"
                "接続」を押してください。"
            )

        if not GOOGLE_DRIVE_CLIENT_PATH.is_file():
            raise GoogleDriveAuthorizationRequired(
                "OAuthクライアントJSONを"
                "先に登録してください。"
            )

        try:
            flow = google[
                "InstalledAppFlow"
            ].from_client_secrets_file(
                str(
                    GOOGLE_DRIVE_CLIENT_PATH
                ),
                GOOGLE_DRIVE_SCOPES,
            )
            credentials = (
                flow.run_local_server(
                    host="localhost",
                    port=0,
                    open_browser=True,
                    authorization_prompt_message=(
                        "ブラウザでGoogle Driveの"
                        "閲覧を許可してください: "
                        "{url}"
                    ),
                    success_message=(
                        "Google Driveの認証が"
                        "完了しました。この画面を"
                        "閉じて競輪アプリへ戻って"
                        "ください。"
                    ),
                )
            )
        except Exception as exception:
            raise GoogleDrivePredictionImportError(
                "Googleアカウント認証を"
                "完了できませんでした。"
            ) from exception

    _write_private_text(
        GOOGLE_DRIVE_TOKEN_PATH,
        credentials.to_json(),
    )
    return credentials


def connect_google_drive() -> None:
    _load_google_credentials(
        interactive=True
    )


def _build_drive_service(
    *,
    interactive: bool,
) -> Any:
    google = _google_imports()
    credentials = _load_google_credentials(
        interactive=interactive
    )

    try:
        return google["build"](
            "drive",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )
    except Exception as exception:
        raise GoogleDrivePredictionImportError(
            "Google Drive APIへ"
            "接続できませんでした。"
        ) from exception


def extract_google_drive_folder_id(
    value: str,
) -> str:
    normalized = str(value or "").strip()

    if not normalized:
        return ""

    if FOLDER_ID_PATTERN.fullmatch(
        normalized
    ):
        return normalized

    parsed = urlparse(normalized)
    segments = [
        segment
        for segment in parsed.path.split("/")
        if segment
    ]

    if "folders" in segments:
        index = segments.index("folders") + 1

        if index < len(segments):
            candidate = segments[index]

            if FOLDER_ID_PATTERN.fullmatch(
                candidate
            ):
                return candidate

    query_id = parse_qs(
        parsed.query
    ).get("id", [""])[0]

    if FOLDER_ID_PATTERN.fullmatch(query_id):
        return query_id

    raise GoogleDrivePredictionImportError(
        "KeirinAIフォルダのURLまたは"
        "フォルダIDを確認してください。"
    )


def _list_drive_files(
    service: Any,
    *,
    query: str,
) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    page_token: str | None = None

    while True:
        response = (
            service.files()
            .list(
                q=query,
                spaces="drive",
                fields=(
                    "nextPageToken,"
                    "files(id,name,mimeType,"
                    "size,modifiedTime,parents)"
                ),
                pageSize=1000,
                pageToken=page_token,
            )
            .execute()
        )
        rows = response.get("files", [])

        if isinstance(rows, list):
            files.extend(
                row
                for row in rows
                if isinstance(row, dict)
            )

        page_token = response.get(
            "nextPageToken"
        )

        if not page_token:
            return files


def find_keirin_ai_folders(
    service: Any,
) -> list[dict[str, Any]]:
    escaped_name = "KeirinAI".replace(
        "'",
        "\\'",
    )
    folders = _list_drive_files(
        service,
        query=(
            "trashed = false and "
            f"name = '{escaped_name}' and "
            "mimeType = '"
            f"{GOOGLE_DRIVE_FOLDER_MIME_TYPE}'"
        ),
    )
    folders.sort(
        key=lambda row: (
            str(row.get("name", "")),
            str(row.get("id", "")),
        )
    )
    return folders


def resolve_keirin_ai_folder(
    service: Any,
    folder_value: str = "",
) -> dict[str, Any]:
    folder_id = extract_google_drive_folder_id(
        folder_value
    )

    if folder_id:
        try:
            folder = (
                service.files()
                .get(
                    fileId=folder_id,
                    fields=(
                        "id,name,mimeType,"
                        "modifiedTime"
                    ),
                )
                .execute()
            )
        except Exception as exception:
            raise GoogleDrivePredictionImportError(
                "指定されたDriveフォルダを"
                "開けません。アカウントと"
                "共有権限を確認してください。"
            ) from exception

        if (
            folder.get("mimeType")
            != GOOGLE_DRIVE_FOLDER_MIME_TYPE
        ):
            raise GoogleDrivePredictionImportError(
                "指定されたIDはフォルダでは"
                "ありません。"
            )

        return folder

    folders = find_keirin_ai_folders(
        service
    )

    if not folders:
        raise GoogleDrivePredictionImportError(
            "Google DriveにKeirinAI"
            "フォルダが見つかりません。"
        )

    if len(folders) > 1:
        raise GoogleDrivePredictionImportError(
            "KeirinAIフォルダが複数"
            "見つかりました。使用する"
            "フォルダのURLを入力してください。"
        )

    return folders[0]


def list_prediction_files(
    service: Any,
    folder_id: str,
) -> list[dict[str, Any]]:
    pending = [folder_id]
    visited: set[str] = set()
    predictions: list[
        dict[str, Any]
    ] = []

    while pending:
        current_id = pending.pop()

        if current_id in visited:
            continue

        visited.add(current_id)

        if (
            len(visited)
            > MAXIMUM_FOLDER_COUNT
        ):
            raise GoogleDrivePredictionImportError(
                "Drive内のフォルダ数が"
                "上限を超えています。"
            )

        escaped_id = current_id.replace(
            "'",
            "\\'",
        )
        children = _list_drive_files(
            service,
            query=(
                "trashed = false and "
                f"'{escaped_id}' in parents"
            ),
        )

        for child in children:
            mime_type = str(
                child.get("mimeType", "")
            )
            name = str(
                child.get("name", "")
            )

            if (
                mime_type
                == GOOGLE_DRIVE_FOLDER_MIME_TYPE
            ):
                child_id = str(
                    child.get("id", "")
                )

                if child_id:
                    pending.append(child_id)
                continue

            if (
                name.startswith(
                    "keirin_prediction_"
                )
                and name.endswith(".json")
            ):
                predictions.append(child)

    predictions.sort(
        key=lambda row: (
            str(row.get("modifiedTime", "")),
            str(row.get("name", "")),
            str(row.get("id", "")),
        )
    )
    return predictions


def _safe_prediction_filename(
    name: str,
) -> str:
    basename = Path(name).name

    if (
        basename.startswith(
            "keirin_prediction_"
        )
        and basename.endswith(".json")
    ):
        return basename

    raise GoogleDrivePredictionImportError(
        "予測JSONのファイル名が"
        "不正です。"
    )


def download_prediction_files(
    service: Any,
    files: list[dict[str, Any]],
    destination: Path,
) -> dict[str, Any]:
    google = _google_imports()
    destination.mkdir(
        parents=True,
        exist_ok=True,
    )
    downloaded = 0
    failures: list[dict[str, str]] = []

    for metadata in files:
        file_id = str(
            metadata.get("id", "")
        )
        name = str(
            metadata.get("name", "")
        )

        try:
            safe_name = (
                _safe_prediction_filename(name)
            )
            declared_size = int(
                metadata.get("size", 0)
                or 0
            )

            if (
                declared_size
                > MAXIMUM_FILE_BYTES
            ):
                raise (
                    GoogleDrivePredictionImportError(
                        "予測ファイルが"
                        "大きすぎます。"
                    )
                )

            if not file_id:
                raise (
                    GoogleDrivePredictionImportError(
                        "DriveファイルIDが"
                        "ありません。"
                    )
                )

            file_directory = (
                destination / file_id
            )
            file_directory.mkdir(
                parents=True,
                exist_ok=True,
            )
            output_path = (
                file_directory / safe_name
            )
            buffer = io.BytesIO()
            request = (
                service.files().get_media(
                    fileId=file_id
                )
            )
            downloader = google[
                "MediaIoBaseDownload"
            ](
                buffer,
                request,
                chunksize=256 * 1024,
            )
            finished = False

            while not finished:
                _, finished = (
                    downloader.next_chunk()
                )

                if (
                    buffer.tell()
                    > MAXIMUM_FILE_BYTES
                ):
                    raise (
                        GoogleDrivePredictionImportError(
                            "予測ファイルが"
                            "大きすぎます。"
                        )
                    )

            output_path.write_bytes(
                buffer.getvalue()
            )
            downloaded += 1
        except Exception as exception:
            failures.append(
                {
                    "file": name or file_id,
                    "error": (
                        f"{type(exception).__name__}: "
                        f"{exception}"
                    ),
                }
            )

    return {
        "downloaded_count": downloaded,
        "failures": failures,
    }


def import_google_drive_predictions(
    folder_value: str = "",
) -> dict[str, Any]:
    service = _build_drive_service(
        interactive=False
    )
    folder = resolve_keirin_ai_folder(
        service,
        folder_value,
    )
    remote_files = list_prediction_files(
        service,
        str(folder["id"]),
    )

    with tempfile.TemporaryDirectory(
        prefix="keirin-drive-import-"
    ) as temporary:
        download = download_prediction_files(
            service,
            remote_files,
            Path(temporary),
        )
        result = import_android_predictions(
            Path(temporary)
        )

    failures = (
        list(download["failures"])
        + list(result["failures"])
    )
    result.update(
        {
            "source": "google_drive_api",
            "drive_folder_id": str(
                folder.get("id", "")
            ),
            "drive_folder_name": str(
                folder.get("name", "")
            ),
            "remote_file_count": len(
                remote_files
            ),
            "downloaded_count": int(
                download["downloaded_count"]
            ),
            "failed_count": len(failures),
            "failures": failures,
        }
    )
    return result
