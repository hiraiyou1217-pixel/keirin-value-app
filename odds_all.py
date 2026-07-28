from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import ssl

import certifi

from odds_http import (
    racecard_to_odds_url,
    extract_json_blobs,
    extract_from_json,
    extract_from_visible_text,
)


class RangeSelectParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()

        self.form_action: str | None = None
        self.current_form_action: str | None = None

        self.current_select: dict[str, Any] | None = None
        self.current_option: dict[str, Any] | None = None

        self.selects: list[dict[str, Any]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)

        if tag == "form":
            self.current_form_action = attributes.get("action")

        elif tag == "select":
            self.current_select = {
                "name": attributes.get("name"),
                "id": attributes.get("id"),
                "form_action": self.current_form_action,
                "options": [],
            }

        elif tag == "option" and self.current_select is not None:
            self.current_option = {
                "value": attributes.get("value"),
                "text": "",
            }

    def handle_data(self, data: str) -> None:
        if self.current_option is not None:
            self.current_option["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "option" and self.current_option is not None:
            self.current_option["text"] = (
                self.current_option["text"].strip()
            )

            if self.current_select is not None:
                self.current_select["options"].append(
                    self.current_option
                )

            self.current_option = None

        elif tag == "select" and self.current_select is not None:
            self.selects.append(self.current_select)
            self.current_select = None

        elif tag == "form":
            self.current_form_action = None


def create_ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


def download_html(
    url: str,
) -> tuple[str | None, list[str]]:
    logs: list[str] = []

    request = Request(
        url,
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
        with urlopen(
            request,
            timeout=30,
            context=create_ssl_context(),
        ) as response:
            charset = (
                response.headers.get_content_charset()
                or "utf-8"
            )
            raw = response.read()

            logs.append(
                f"HTTP状態: {getattr(response, 'status', 200)}"
            )
            logs.append(f"受信サイズ: {len(raw):,} bytes")

            return raw.decode(
                charset,
                errors="replace",
            ), logs

    except HTTPError as exc:
        logs.append(
            f"HTTPエラー: {exc.code} {exc.reason}"
        )

    except URLError as exc:
        logs.append(f"通信エラー: {exc.reason}")

    except Exception as exc:
        logs.append(
            f"取得エラー: {type(exc).__name__}: {exc}"
        )

    return None, logs


def parse_range_number(label: str) -> tuple[int, int] | None:
    normalized = (
        label.replace(" ", "")
        .replace("〜", "-")
        .replace("～", "-")
        .replace("~", "-")
    )

    parts = normalized.split("-")

    if len(parts) != 2:
        return None

    if not all(part.isdigit() for part in parts):
        return None

    start = int(parts[0])
    end = int(parts[1])

    if start < 1 or end < start:
        return None

    return start, end


def discover_range_selects(
    html: str,
) -> list[dict[str, Any]]:
    parser = RangeSelectParser()
    parser.feed(html)

    matches: list[dict[str, Any]] = []

    for select in parser.selects:
        range_options = []

        for option in select["options"]:
            parsed = parse_range_number(option["text"])

            if parsed is None:
                continue

            range_options.append(
                {
                    "text": option["text"],
                    "value": option["value"],
                    "start": parsed[0],
                    "end": parsed[1],
                }
            )

        if len(range_options) >= 2:
            matches.append(
                {
                    **select,
                    "options": range_options,
                }
            )

    return matches


def replace_query_parameter(
    url: str,
    name: str,
    value: str,
) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query))
    query[name] = value

    return urlunparse(
        parsed._replace(
            query=urlencode(query)
        )
    )


def build_range_url(
    base_url: str,
    select: dict[str, Any],
    option: dict[str, Any],
) -> str | None:
    value = option.get("value")

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    if value.startswith(("http://", "https://", "/", "?")):
        return urljoin(base_url, value)

    form_action = select.get("form_action")
    select_name = select.get("name")

    target_url = (
        urljoin(base_url, form_action)
        if form_action
        else base_url
    )

    if select_name:
        return replace_query_parameter(
            target_url,
            select_name,
            value,
        )

    return None


def extract_rows(
    html: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    logs: list[str] = []
    output: dict[str, dict[str, Any]] = {}

    blobs = extract_json_blobs(html)
    logs.append(f"埋め込みJSON候補: {len(blobs)}個")

    for blob in blobs:
        extract_from_json(blob, output)

    logs.append(f"JSON解析取得: {len(output)}件")

    text_rows = extract_from_visible_text(html)

    for row in text_rows:
        existing = output.get(row["組番"])

        if (
            existing is None
            or row.get("人気", 9999)
            < existing.get("人気", 9999)
        ):
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

    return rows, logs


def fetch_all_trifecta_odds(
    racecard_url: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    odds_url = racecard_to_odds_url(racecard_url)

    logs = [
        "取得方式: HTTP全範囲取得",
        f"オッズ取得元: {odds_url}",
    ]

    initial_html, initial_logs = download_html(odds_url)
    logs.extend(initial_logs)

    if initial_html is None:
        return [], logs

    initial_rows, extraction_logs = extract_rows(initial_html)
    logs.extend(extraction_logs)

    all_rows: dict[str, dict[str, Any]] = {
        row["組番"]: row
        for row in initial_rows
    }

    logs.append(f"初期範囲取得: {len(initial_rows)}件")

    range_selects = discover_range_selects(initial_html)
    logs.append(
        f"範囲プルダウン候補: {len(range_selects)}個"
    )

    if not range_selects:
        logs.append(
            "範囲プルダウンのoption情報を検出できませんでした。"
        )
        logs.append(
            "初期表示の50件のみを返します。"
        )
        return initial_rows, logs

    selected = max(
        range_selects,
        key=lambda item: len(item["options"]),
    )

    logs.append(
        "検出範囲: "
        + "、".join(
            option["text"]
            for option in selected["options"]
        )
    )

    logs.append(
        f"select name: {selected.get('name') or 'なし'}"
    )
    logs.append(
        f"select id: {selected.get('id') or 'なし'}"
    )

    attempted_urls: set[str] = {odds_url}

    for option in selected["options"]:
        if option["start"] == 1:
            continue

        range_url = build_range_url(
            odds_url,
            selected,
            option,
        )

        logs.append(
            f"{option['text']} value="
            f"{option.get('value')!r}"
        )

        if range_url is None:
            logs.append(
                f"{option['text']}: URLを生成できませんでした。"
            )
            continue

        if range_url in attempted_urls:
            continue

        attempted_urls.add(range_url)
        logs.append(
            f"{option['text']}取得URL: {range_url}"
        )

        html, request_logs = download_html(range_url)
        logs.extend(
            f"{option['text']} {message}"
            for message in request_logs
        )

        if html is None:
            continue

        rows, row_logs = extract_rows(html)
        logs.extend(
            f"{option['text']} {message}"
            for message in row_logs
        )

        added = 0

        for row in rows:
            combo = row["組番"]

            if combo not in all_rows:
                added += 1

            all_rows[combo] = row

        logs.append(
            f"{option['text']}: "
            f"{len(rows)}件解析／{added}件追加"
        )

    result = sorted(
        all_rows.values(),
        key=lambda row: (
            row.get("人気", 9999),
            row["組番"],
        ),
    )

    logs.append(f"最終取得件数: {len(result)}件")

    if len(result) == len(initial_rows):
        logs.append(
            "追加範囲のURLは生成できましたが、"
            "初期表示と同じ内容が返された可能性があります。"
        )
        logs.append(
            "取得ログ内のselect name、option value、"
            "取得URLを確認してください。"
        )

    return result, logs
