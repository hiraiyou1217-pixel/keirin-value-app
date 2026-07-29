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
    tables = page.locator("table")

    for table_index in range(
        tables.count()
    ):
        table = tables.nth(table_index)

        try:
            table_text = normalize_text(
                table.inner_text(
                    timeout=3_000
                )
            )
        except Exception:
            continue

        if not any(
            keyword in table_text
            for keyword in (
                "着",
                "順位",
                "車",
                "選手名",
            )
        ):
            continue

        rows = table.locator("tr")
        detected: list[tuple[int, int]] = []

        for row_index in range(
            rows.count()
        ):
            row = rows.nth(row_index)

            try:
                cells = [
                    normalize_text(value)
                    for value in row.locator(
                        "th, td"
                    ).all_inner_texts()
                ]
            except Exception:
                continue

            if len(cells) < 2:
                continue

            position = None
            car_number = None

            for cell in cells[:4]:
                match = re.fullmatch(
                    r"([1-9])着",
                    cell,
                )

                if match:
                    position = int(
                        match.group(1)
                    )
                    break

            if position is None:
                first_value = parse_integer(
                    cells[0]
                )

                if first_value in (
                    1,
                    2,
                    3,
                ):
                    position = first_value

            for cell in cells[:6]:
                number = parse_integer(cell)

                if number in valid_cars:
                    if number != position:
                        car_number = number
                        break

            if (
                position in (1, 2, 3)
                and car_number in valid_cars
            ):
                detected.append(
                    (position, car_number)
                )

        order_map = {
            position: car
            for position, car in detected
        }

        if all(
            position in order_map
            for position in (
                1,
                2,
                3,
            )
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
        browser = playwright.chromium.launch(
            headless=True,
            channel="chrome",
            args=[
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
            ],
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

        if page_is_unsettled(body_text):
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
                    body_text,
                    valid_cars,
                )
            )

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

        payout = extract_trifecta_payout(
            body_text,
            winning_combination,
        )

        if payout is None:
            browser.close()

            return {
                "success": False,
                "status": "parse_error",
                "message": (
                    "3連単払戻を"
                    "特定できませんでした。"
                ),
                "finish_order": finish_order,
                "winning_combination": (
                    winning_combination
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
