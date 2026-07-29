from __future__ import annotations

from typing import Any


def normalize_racecard_url(url: Any) -> str:
    value = str(url or "").strip()

    if not value:
        return ""

    if "/odds/" in value:
        return value.replace(
            "/odds/",
            "/racecard/",
            1,
        )

    if "/raceresult/" in value:
        return value.replace(
            "/raceresult/",
            "/racecard/",
            1,
        )

    return value


def infer_racecard_url(
    *,
    explicit_url: Any = "",
    logs: list[Any] | None = None,
) -> str:
    normalized = normalize_racecard_url(
        explicit_url
    )

    if normalized:
        return normalized

    prefixes = (
        "出走表URL:",
        "オッズ取得元:",
        "結果URL:",
    )

    for raw_log in logs or []:
        log = str(raw_log).strip()

        for prefix in prefixes:
            if not log.startswith(prefix):
                continue

            candidate = log[
                len(prefix):
            ].strip()

            normalized = normalize_racecard_url(
                candidate
            )

            if normalized:
                return normalized

    return ""
