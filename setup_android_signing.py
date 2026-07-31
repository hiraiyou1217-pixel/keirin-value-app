from __future__ import annotations

import argparse
import base64
import os
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT_DIRECTORY = Path(__file__).resolve().parent
SIGNING_DIRECTORY = (
    ROOT_DIRECTORY / ".android-signing"
)
KEYSTORE_PATH = (
    SIGNING_DIRECTORY
    / "keirin-ai-release.p12"
)
SECRETS_PATH = (
    SIGNING_DIRECTORY
    / "github-actions-secrets.txt"
)
KEY_ALIAS = "keirin-ai"


def find_keytool() -> str | None:
    found = shutil.which("keytool")

    if found:
        return found

    java_home = os.environ.get(
        "JAVA_HOME",
        "",
    )

    if java_home:
        candidate = (
            Path(java_home)
            / "bin"
            / "keytool"
        )

        if candidate.is_file():
            return str(candidate)

    return None


def _run_keytool(
    keytool: str,
    password: str,
) -> None:
    environment = dict(os.environ)
    environment[
        "KEIRIN_SIGNING_PASSWORD"
    ] = password
    command = [
        keytool,
        "-genkeypair",
        "-v",
        "-storetype",
        "PKCS12",
        "-keystore",
        str(KEYSTORE_PATH),
        "-storepass:env",
        "KEIRIN_SIGNING_PASSWORD",
        "-keypass:env",
        "KEIRIN_SIGNING_PASSWORD",
        "-alias",
        KEY_ALIAS,
        "-keyalg",
        "RSA",
        "-keysize",
        "3072",
        "-validity",
        "10000",
        "-dname",
        (
            "CN=Keirin AI,"
            "OU=Personal,"
            "O=Hirai,"
            "L=Tokyo,"
            "ST=Tokyo,"
            "C=JP"
        ),
    ]
    subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )


def _run_openssl(
    openssl: str,
    password: str,
) -> None:
    environment = dict(os.environ)
    environment[
        "KEIRIN_SIGNING_PASSWORD"
    ] = password

    with tempfile.TemporaryDirectory() as name:
        directory = Path(name)
        private_key = (
            directory / "private-key.pem"
        )
        certificate = (
            directory / "certificate.pem"
        )
        subprocess.run(
            [
                openssl,
                "req",
                "-x509",
                "-newkey",
                "rsa:3072",
                "-keyout",
                str(private_key),
                "-out",
                str(certificate),
                "-days",
                "10000",
                "-nodes",
                "-subj",
                (
                    "/CN=Keirin AI"
                    "/OU=Personal"
                    "/O=Hirai"
                    "/L=Tokyo"
                    "/ST=Tokyo"
                    "/C=JP"
                ),
            ],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        subprocess.run(
            [
                openssl,
                "pkcs12",
                "-export",
                "-out",
                str(KEYSTORE_PATH),
                "-inkey",
                str(private_key),
                "-in",
                str(certificate),
                "-name",
                KEY_ALIAS,
                "-passout",
                "env:KEIRIN_SIGNING_PASSWORD",
            ],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )


def create_signing_material(
    *,
    repair: bool = False,
) -> dict[str, str]:
    existing = [
        path
        for path in (
            KEYSTORE_PATH,
            SECRETS_PATH,
        )
        if path.exists()
    ]

    if existing and not repair:
        raise FileExistsError(
            "固定署名ファイルまたは"
            "作成途中のファイルがあります。"
            "作成済みならそのまま使用し、"
            "前回失敗した場合だけ"
            "--repairを付けてください。"
        )

    if repair:
        for path in (
            KEYSTORE_PATH,
            SECRETS_PATH,
        ):
            if path.is_file():
                path.unlink()

    SIGNING_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )
    password = secrets.token_urlsafe(32)
    keytool = find_keytool()

    if keytool:
        try:
            _run_keytool(
                keytool,
                password,
            )
        except subprocess.CalledProcessError:
            if KEYSTORE_PATH.is_file():
                KEYSTORE_PATH.unlink()
            keytool = None

    if not keytool:
        openssl = shutil.which("openssl")

        if not openssl:
            raise RuntimeError(
                "keytoolで署名鍵を作成"
                "できず、代替のopensslも"
                "見つかりません。"
            )

        _run_openssl(
            openssl,
            password,
        )
    encoded = base64.b64encode(
        KEYSTORE_PATH.read_bytes()
    ).decode("ascii")
    content = "\n".join(
        [
            (
                "ANDROID_SIGNING_KEYSTORE_BASE64="
                + encoded
            ),
            (
                "ANDROID_SIGNING_STORE_PASSWORD="
                + password
            ),
            (
                "ANDROID_SIGNING_KEY_ALIAS="
                + KEY_ALIAS
            ),
            (
                "ANDROID_SIGNING_KEY_PASSWORD="
                + password
            ),
            "",
        ]
    )
    SECRETS_PATH.write_text(
        content,
        encoding="utf-8",
    )
    os.chmod(KEYSTORE_PATH, 0o600)
    os.chmod(SECRETS_PATH, 0o600)
    return {
        "keystore": str(KEYSTORE_PATH),
        "secrets": str(SECRETS_PATH),
        "key_alias": KEY_ALIAS,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Galaxy版APKの固定署名鍵と"
            "GitHub Actions登録値を"
            "ローカルに作成します。"
        )
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help=(
            "前回の作成失敗で残った"
            "署名ファイルだけを作り直す"
        ),
    )
    arguments = parser.parse_args()

    try:
        result = create_signing_material(
            repair=arguments.repair
        )
    except Exception as exception:
        print(
            f"{type(exception).__name__}: "
            f"{exception}"
        )
        return 1

    print("固定署名鍵を作成しました。")
    print(
        "キーストア: "
        + result["keystore"]
    )
    print(
        "GitHub登録値: "
        + result["secrets"]
    )
    print(
        "この2ファイルはGitHubへ"
        "Pushせず、安全に保管してください。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
