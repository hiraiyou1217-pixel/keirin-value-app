from __future__ import annotations

import argparse
import json
import re
import time
import traceback
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
)
from playwright.sync_api import sync_playwright


RACE_MARKER_PATTERN = re.compile(
    r"(?<!\d)"
    r"(?:第\s*)?"
    r"(\d{1,2})\s*"
    r"(?:R|レ[-ー]?ス)"
    r"(?!\d)",
    re.IGNORECASE,
)


def build_result_url(
    race_url: str,
) -> str:
    url = str(race_url).strip()

    if not url:
        raise ValueError(
            "出走表URLが保存されていません。"
        )

    if "/racecard/" in url:
        return url.replace(
            "/racecard/",
            "/raceresult/",
            1,
        )

    if "/odds/" in url:
        return url.replace(
            "/odds/",
            "/raceresult/",
            1,
        )

    if "/raceresult/" in url:
        return url

    raise ValueError(
        f"結果URLへ変換できません: {url}"
    )


def normalize_text(
    value: str,
) -> str:
    text = str(value)

    text = text.replace("\u3000", " ")
    text = text.replace("−", "-")
    text = text.replace("―", "-")
    text = text.replace("–", "-")
    text = text.replace("ー", "-")

    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    return text.strip()


def parse_integer(
    value: str,
) -> int | None:
    digits = re.sub(
        r"[^\d]",
        "",
        str(value),
    )

    if not digits:
        return None

    try:
        return int(digits)
    except ValueError:
        return None


def extract_finish_order_from_tables(
    page: Any,
    valid_cars: set[int],
) -> list[int]:
    """
    「着 | 車 | 選手名」の結果表を列名で判定して取得する。
    """
    tables = page.locator("table")

    for table_index in range(tables.count()):
        table = tables.nth(table_index)

        try:
            rows = table.locator("tr")

            if rows.count() < 4:
                continue

            header_cells = [
                normalize_text(value)
                for value in rows.nth(0)
                .locator("th, td")
                .all_inner_texts()
            ]
        except Exception:
            continue

        normalized_headers = [
            value.replace("\n", "")
            for value in header_cells
        ]

        try:
            position_index = next(
                index
                for index, value
                in enumerate(normalized_headers)
                if value in ("着", "着順", "順位")
            )

            car_index = next(
                index
                for index, value
                in enumerate(normalized_headers)
                if value in ("車", "車番")
            )
        except StopIteration:
            continue

        order_map: dict[int, int] = {}

        for row_index in range(1, rows.count()):
            try:
                cells = [
                    normalize_text(value)
                    for value in rows.nth(row_index)
                    .locator("th, td")
                    .all_inner_texts()
                ]
            except Exception:
                continue

            if (
                position_index >= len(cells)
                or car_index >= len(cells)
            ):
                continue

            position = parse_integer(
                cells[position_index]
            )

            car_number = parse_integer(
                cells[car_index]
            )

            if (
                position in (1, 2, 3)
                and car_number in valid_cars
            ):
                order_map[position] = car_number

        if all(
            position in order_map
            for position in (1, 2, 3)
        ):
            result = [
                order_map[1],
                order_map[2],
                order_map[3],
            ]

            if len(set(result)) == 3:
                return result

    return []

def extract_finish_order_from_text(
    body_text: str,
    valid_cars: set[int],
) -> list[int]:
    patterns = [
        re.compile(
            r"1着\s*([1-9])"
            r".{0,80}?"
            r"2着\s*([1-9])"
            r".{0,80}?"
            r"3着\s*([1-9])",
            re.DOTALL,
        ),
        re.compile(
            r"着順.{0,60}?"
            r"([1-9]).{0,40}?"
            r"([1-9]).{0,40}?"
            r"([1-9])",
            re.DOTALL,
        ),
    ]

    for pattern in patterns:
        match = pattern.search(body_text)

        if not match:
            continue

        result = [
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
        ]

        if (
            len(set(result)) == 3
            and all(
                car in valid_cars
                for car in result
            )
        ):
            return result

    return []



def extract_trifecta_rows_from_tables(
    page: Any,
) -> tuple[list[dict[str, Any]], bool]:
    """3連単払戻表を取得し、複数払戻も省略せず返す。"""
    tables = page.locator("table")
    output: list[dict[str, Any]] = []
    ambiguous = False

    for table_index in range(tables.count()):
        rows = tables.nth(table_index).locator("tr")

        for row_index in range(rows.count()):
            try:
                cells = [
                    normalize_text(value)
                    for value in rows.nth(row_index)
                    .locator("th, td")
                    .all_inner_texts()
                ]
            except Exception:
                continue

            if not cells:
                continue

            joined = " | ".join(cells)

            if "3連単" not in joined:
                continue

            combinations = [
                "-".join(match)
                for match in re.findall(
                    r"(?<!\d)([1-9])\s*-\s*"
                    r"([1-9])\s*-\s*([1-9])(?!\d)",
                    joined,
                )
            ]

            payouts = [
                int(
                    value.replace(",", "")
                )
                for value in re.findall(
                    r"([\d,]+)\s*円",
                    joined,
                )
                if int(
                    value.replace(",", "")
                )
                >= 100
            ]

            if (
                len(combinations) != len(payouts)
                or not combinations
            ):
                ambiguous = True
                continue

            for combination, payout in zip(
                combinations,
                payouts,
                strict=True,
            ):
                item = {
                    "combination": combination,
                    "payout_per_100": payout,
                }

                if item not in output:
                    output.append(item)

    return output, ambiguous


def extract_trifecta_from_tables(
    page: Any,
) -> tuple[str, int] | None:
    rows, ambiguous = (
        extract_trifecta_rows_from_tables(
            page
        )
    )

    if ambiguous or len(rows) != 1:
        return None

    return (
        str(rows[0]["combination"]),
        int(rows[0]["payout_per_100"]),
    )

def extract_trifecta_payout(
    body_text: str,
    winning_combination: str,
) -> int | None:
    escaped_combination = re.escape(
        winning_combination
    )

    patterns = [
        re.compile(
            rf"3連単"
            rf".{{0,120}}?"
            rf"{escaped_combination}"
            rf".{{0,80}}?"
            rf"([\d,]+)\s*円",
            re.DOTALL,
        ),
        re.compile(
            rf"{escaped_combination}"
            rf".{{0,80}}?"
            rf"([\d,]+)\s*円"
            rf".{{0,80}}?"
            rf"3連単",
            re.DOTALL,
        ),
        re.compile(
            r"3連単"
            r".{0,160}?"
            r"([\d,]+)\s*円",
            re.DOTALL,
        ),
    ]

    for pattern in patterns:
        match = pattern.search(body_text)

        if not match:
            continue

        payout = parse_integer(
            match.group(1)
        )

        if (
            payout is not None
            and payout >= 100
        ):
            return payout

    return None


def page_is_unsettled(
    body_text: str,
) -> bool:
    unsettled_keywords = (
        "レース前",
        "結果はまだありません",
        "レース結果はありません",
        "確定までお待ちください",
        "集計中",
        "審議中",
    )

    return any(
        keyword in body_text
        for keyword in unsettled_keywords
    )


def extract_race_number_from_url(
    result_url: str,
) -> int | None:
    path = urlparse(
        str(result_url)
    ).path.rstrip("/")
    match = re.search(
        r"/raceresult/\d+/\d+/(\d+)$",
        path,
    )

    if not match:
        return None

    race_number = int(match.group(1))

    if 1 <= race_number <= 12:
        return race_number

    return None


def extract_race_scoped_text(
    body_text: str,
    race_number: int | None,
) -> str:
    normalized = normalize_text(
        body_text
    )

    if race_number is None:
        return normalized

    markers = list(
        RACE_MARKER_PATTERN.finditer(
            normalized
        )
    )

    if not markers:
        return normalized

    segments: list[str] = []

    for index, marker in enumerate(markers):
        if int(marker.group(1)) != int(
            race_number
        ):
            continue

        next_start = (
            markers[index + 1].start()
            if index + 1 < len(markers)
            else min(
                len(normalized),
                marker.start() + 6_000,
            )
        )
        segments.append(
            normalized[
                marker.start():next_start
            ]
        )

    if not segments:
        return normalized

    return "\n".join(segments)


def detect_manual_review_reasons(
    body_text: str,
    *,
    race_number: int | None = None,
    has_settled_result: bool = False,
) -> list[str]:
    keyword_labels = {
        "同着": "同着",
        "失格": "失格",
        "中止": "中止",
        "不成立": "不成立",
    }
    scoped_text = extract_race_scoped_text(
        body_text,
        race_number,
    )
    has_target_marker = (
        race_number is not None
        and any(
            int(marker.group(1))
            == int(race_number)
            for marker
            in RACE_MARKER_PATTERN.finditer(
                normalize_text(body_text)
            )
        )
    )

    return [
        f"{label}の記載があります"
        for keyword, label
        in keyword_labels.items()
        if keyword in scoped_text
        and not (
            has_settled_result
            and not has_target_marker
            and keyword
            in ("中止", "不成立")
        )
    ]


def detect_duplicate_top_positions(
    page: Any,
) -> bool:
    tables = page.locator("table")

    for table_index in range(tables.count()):
        rows = tables.nth(table_index).locator(
            "tr"
        )

        if rows.count() < 2:
            continue

        try:
            headers = [
                normalize_text(value).replace(
                    "\n",
                    "",
                )
                for value in rows.nth(0)
                .locator("th, td")
                .all_inner_texts()
            ]
        except Exception:
            continue

        try:
            position_index = next(
                index
                for index, value
                in enumerate(headers)
                if value in ("着", "着順", "順位")
            )
        except StopIteration:
            continue

        positions: list[int] = []

        for row_index in range(
            1,
            rows.count(),
        ):
            try:
                cells = [
                    normalize_text(value)
                    for value in rows.nth(
                        row_index
                    )
                    .locator("th, td")
                    .all_inner_texts()
                ]
            except Exception:
                continue

            if position_index >= len(cells):
                continue

            position = parse_integer(
                cells[position_index]
            )

            if position in (1, 2, 3):
                positions.append(position)

        if len(positions) != len(
            set(positions)
        ):
            return True

    return False


def fetch_result(
    *,
    race_url: str,
    valid_car_numbers: list[int],
) -> dict[str, Any]:
    result_url = build_result_url(
        race_url
    )

    valid_cars = {
        int(number)
        for number in valid_car_numbers
    }

    logs = [
        "結果取得方式: Google Chrome DOM解析",
        f"結果URL: {result_url}",
    ]

    with sync_playwright() as playwright:
        launch_options = {
            "headless": True,
            "args": [
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
            ],
        }

        try:
            browser = playwright.chromium.launch(
                channel="chrome",
                **launch_options,
            )
            logs.append(
                "ブラウザ: システムのGoogle Chrome"
            )
        except Exception:
            browser = playwright.chromium.launch(
                **launch_options,
            )
            logs.append(
                "ブラウザ: Playwright Chromium"
            )

        context = browser.new_context(
            locale="ja-JP",
        )

        page = context.new_page()
        page.set_default_timeout(15_000)

        loaded = False

        for attempt in range(1, 4):
            logs.append(
                f"ページ読込試行: {attempt}/3"
            )

            try:
                page.goto(
                    result_url,
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )

                page.wait_for_timeout(
                    2_000
                )

                loaded = True
                logs.append(
                    f"ページ読込成功: 試行{attempt}"
                )
                break

            except PlaywrightTimeoutError:
                logs.append(
                    f"ページ読込タイムアウト: 試行{attempt}"
                )

                if attempt < 3:
                    time.sleep(2)

        if not loaded:
            browser.close()

            return {
                "success": False,
                "status": "error",
                "message": (
                    "結果ページを読み込めませんでした。"
                ),
                "logs": logs,
            }

        logs.append(
            f"ページタイトル: {page.title()}"
        )

        body_text = normalize_text(
            page.locator("body").inner_text()
        )
        race_number = (
            extract_race_number_from_url(
                result_url
            )
        )
        scoped_body_text = (
            extract_race_scoped_text(
                body_text,
                race_number,
            )
        )

        if race_number is not None:
            logs.append(
                f"判定対象レース: {race_number}R"
            )

        if page_is_unsettled(
            scoped_body_text
        ):
            browser.close()

            return {
                "success": True,
                "status": "unsettled",
                "message": "結果未確定です。",
                "result_url": result_url,
                "logs": logs,
            }

        finish_order = (
            extract_finish_order_from_tables(
                page,
                valid_cars,
            )
        )

        if not finish_order:
            finish_order = (
                extract_finish_order_from_text(
                    scoped_body_text,
                    valid_cars,
                )
            )

        trifecta_rows, payout_ambiguous = (
            extract_trifecta_rows_from_tables(
                page
            )
        )
        has_settled_result = (
            len(finish_order) == 3
            and len(trifecta_rows) == 1
            and not payout_ambiguous
        )
        review_reasons = (
            detect_manual_review_reasons(
                body_text,
                race_number=race_number,
                has_settled_result=(
                    has_settled_result
                ),
            )
        )

        if detect_duplicate_top_positions(
            page
        ):
            review_reasons.append(
                "1〜3着に同順位があります"
            )

        if payout_ambiguous:
            review_reasons.append(
                "3連単の組番と払戻を"
                "一意に対応付けできません"
            )

        if len(trifecta_rows) > 1:
            review_reasons.append(
                "3連単の払戻が複数あります"
            )

        if review_reasons:
            unique_reasons = list(
                dict.fromkeys(review_reasons)
            )

            browser.close()

            return {
                "success": True,
                "status": "review",
                "message": (
                    "自動確定せず要確認として保存します。"
                ),
                "review_reasons": unique_reasons,
                "trifecta_rows": trifecta_rows,
                "result_url": result_url,
                "logs": logs,
            }

        if len(finish_order) != 3:
            browser.close()

            return {
                "success": False,
                "status": "parse_error",
                "message": (
                    "1着・2着・3着を"
                    "特定できませんでした。"
                ),
                "result_url": result_url,
                "logs": logs,
            }

        winning_combination = "-".join(
            str(number)
            for number in finish_order
        )

        if len(trifecta_rows) != 1:
            browser.close()

            return {
                "success": False,
                "status": "parse_error",
                "message": (
                    "3連単払戻表を一意に"
                    "特定できませんでした。"
                ),
                "finish_order": finish_order,
                "winning_combination": (
                    winning_combination
                ),
                "result_url": result_url,
                "logs": logs,
            }

        table_combination = str(
            trifecta_rows[0]["combination"]
        )
        payout = int(
            trifecta_rows[0]["payout_per_100"]
        )

        if table_combination != winning_combination:
            browser.close()

            return {
                "success": False,
                "status": "validation_error",
                "message": (
                    "着順表と3連単払戻表の"
                    "組番が一致しません。"
                ),
                "finish_order": finish_order,
                "winning_combination": (
                    winning_combination
                ),
                "payout_combination": (
                    table_combination
                ),
                "result_url": result_url,
                "logs": logs,
            }

        logs.append(
            f"確定着順: {winning_combination}"
        )
        logs.append(
            f"3連単払戻: {payout:,}円"
        )

        browser.close()

        return {
            "success": True,
            "status": "settled",
            "message": "結果を取得しました。",
            "finish_order": finish_order,
            "winning_combination": (
                winning_combination
            ),
            "payout_per_100": payout,
            "result_url": result_url,
            "logs": logs,
        }


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        required=True,
    )
    parser.add_argument(
        "--output",
        required=True,
    )

    arguments = parser.parse_args()

    input_path = Path(arguments.input)
    output_path = Path(arguments.output)

    try:
        payload = json.loads(
            input_path.read_text(
                encoding="utf-8"
            )
        )

        result = fetch_result(
            race_url=str(
                payload.get(
                    "race_url",
                    "",
                )
            ),
            valid_car_numbers=[
                int(number)
                for number in payload.get(
                    "valid_car_numbers",
                    [],
                )
            ],
        )

    except Exception as exc:
        result = {
            "success": False,
            "status": "error",
            "message": (
                f"{type(exc).__name__}: {exc}"
            ),
            "logs": [
                "結果取得Workerでエラーが発生しました。",
                traceback.format_exc(),
            ],
        }

    output_path.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
