from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


COMBO_RE = re.compile(
    r"(?<!\d)([1-9])\s*[-–—]\s*([1-9])\s*[-–—]\s*([1-9])(?!\d)"
)
NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?$")

SCRIPT_JSON_RE = re.compile(
    r'<script[^>]+type=["\']application/json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)

NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if value:
            self.parts.append(value)


def racecard_to_odds_url(racecard_url: str) -> str:
    if "/racecard/" not in racecard_url:
        raise ValueError("WINTICKETの出走表URLではありません。")

    return racecard_url.replace("/racecard/", "/odds/", 1)


def normalise_combo(value: Any) -> str | None:
    if isinstance(value, str):
        match = COMBO_RE.search(value)

        if match and len(set(match.groups())) == 3:
            return "-".join(match.groups())

        digits = re.sub(r"\D", "", value)

        if len(digits) == 3 and len(set(digits)) == 3 and "0" not in digits:
            return "-".join(digits)

    if isinstance(value, (list, tuple)) and len(value) == 3:
        digits = [str(item) for item in value]

        if all(re.fullmatch(r"[1-9]", item) for item in digits):
            if len(set(digits)) == 3:
                return "-".join(digits)

    return None


def normalise_odds(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        odds = float(value)
        return odds if 1.0 < odds < 1_000_000 else None

    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("倍", "").strip()

        if NUMBER_RE.fullmatch(cleaned):
            odds = float(cleaned)
            return odds if 1.0 < odds < 1_000_000 else None

    return None


def normalise_rank(value: Any) -> int | None:
    if isinstance(value, int) and 1 <= value <= 504:
        return value

    if isinstance(value, str):
        digits = re.sub(r"\D", "", value)

        if digits:
            rank = int(digits)

            if 1 <= rank <= 504:
                return rank

    return None


def extract_from_json(
    value: Any,
    output: dict[str, dict[str, Any]],
) -> None:
    if isinstance(value, dict):
        combo = None
        odds = None
        rank = None

        combo_keys = (
            "combination",
            "number",
            "numbers",
            "selection",
            "select",
            "betNumber",
            "oddsNumber",
            "trifecta",
        )

        odds_keys = (
            "odds",
            "ratio",
            "value",
            "displayOdds",
            "oddsValue",
            "minimumOdds",
            "maxOdds",
        )

        rank_keys = (
            "rank",
            "popularity",
            "popular",
            "order",
        )

        for key in combo_keys:
            if key in value:
                combo = normalise_combo(value[key])

                if combo:
                    break

        for key in odds_keys:
            if key in value:
                odds = normalise_odds(value[key])

                if odds is not None:
                    break

        for key in rank_keys:
            if key in value:
                rank = normalise_rank(value[key])

                if rank is not None:
                    break

        if combo is None:
            key_groups = (
                ("first", "second", "third"),
                ("firstNumber", "secondNumber", "thirdNumber"),
                ("number1", "number2", "number3"),
            )

            for keys in key_groups:
                if all(key in value for key in keys):
                    combo = normalise_combo(
                        [value[key] for key in keys]
                    )

                    if combo:
                        break

        if combo and odds is not None:
            row = {
                "組番": combo,
                "オッズ": odds,
                "人気": rank or 9999,
            }

            existing = output.get(combo)

            if existing is None or row["人気"] < existing["人気"]:
                output[combo] = row

        for child in value.values():
            extract_from_json(child, output)

    elif isinstance(value, list):
        for child in value:
            extract_from_json(child, output)


def extract_json_blobs(html: str) -> list[Any]:
    blobs: list[Any] = []

    candidates = (
        NEXT_DATA_RE.findall(html)
        + SCRIPT_JSON_RE.findall(html)
    )

    for raw in candidates:
        try:
            blobs.append(json.loads(unescape(raw).strip()))
        except (json.JSONDecodeError, TypeError):
            continue

    return blobs


def extract_from_visible_text(
    html: str,
) -> list[dict[str, Any]]:
    parser = TextExtractor()
    parser.feed(html)

    lines = [
        unescape(item).strip()
        for item in parser.parts
        if item.strip()
    ]

    rows: dict[str, dict[str, Any]] = {}

    for index, line in enumerate(lines):
        combo = normalise_combo(line)

        if combo is None:
            continue

        neighborhood = lines[
            max(0, index - 3): min(len(lines), index + 5)
        ]

        odds = None

        for item in neighborhood:
            cleaned = (
                item.replace(",", "")
                .replace("倍", "")
                .strip()
            )

            if NUMBER_RE.fullmatch(cleaned):
                number = float(cleaned)

                if 1.0 < number < 1_000_000:
                    odds = number
                    break

        if odds is not None:
            rows[combo] = {
                "組番": combo,
                "オッズ": odds,
                "人気": 9999,
            }

    return list(rows.values())


def fetch_trifecta_odds_http(
    racecard_url: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    odds_url = racecard_to_odds_url(racecard_url)

    logs = [
        "取得方式: HTTP（Chromium不使用）",
        f"オッズ取得元: {odds_url}",
    ]

    request = Request(
        odds_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 Chrome/126 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/json"
            ),
            "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.7",
            "Cache-Control": "no-cache",
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            status = getattr(response, "status", 200)
            charset = (
                response.headers.get_content_charset()
                or "utf-8"
            )
            raw = response.read()

    except HTTPError as exc:
        logs.append(
            f"HTTPエラー: {exc.code} {exc.reason}"
        )
        return [], logs

    except URLError as exc:
        logs.append(f"通信エラー: {exc.reason}")
        return [], logs

    except Exception as exc:
        logs.append(
            f"取得エラー: {type(exc).__name__}: {exc}"
        )
        return [], logs

    html = raw.decode(charset, errors="replace")

    logs.append(f"HTTP状態: {status}")
    logs.append(f"受信サイズ: {len(raw):,} bytes")

    output: dict[str, dict[str, Any]] = {}
    blobs = extract_json_blobs(html)

    logs.append(f"埋め込みJSON候補: {len(blobs)}個")

    for blob in blobs:
        extract_from_json(blob, output)

    logs.append(f"JSON解析取得: {len(output)}件")

    if not output:
        text_rows = extract_from_visible_text(html)

        for row in text_rows:
            output[row["組番"]] = row

        logs.append(
            f"HTMLテキスト解析取得: {len(text_rows)}件"
        )

    rows = sorted(
        output.values(),
        key=lambda row: (
            row.get("人気", 9999),
            row["組番"],
        ),
    )

    if rows and all(
        row.get("人気", 9999) == 9999
        for row in rows
    ):
        rows = sorted(
            rows,
            key=lambda row: (
                row["オッズ"],
                row["組番"],
            ),
        )

        for index, row in enumerate(rows, start=1):
            row["人気"] = index

        logs.append(
            "人気順位はオッズ昇順から補完しました。"
        )

    logs.append(f"最終取得件数: {len(rows)}件")

    if not rows:
        logs.append(
            "ページHTML内にオッズデータを検出できませんでした。"
        )
        logs.append(
            "次の段階では、WINTICKETが内部で使用している"
            "データ通信先を確認します。"
        )

    return rows, logs
