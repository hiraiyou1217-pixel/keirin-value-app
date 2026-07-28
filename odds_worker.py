from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


RANGE_RE = re.compile(r"^\s*(\d+)\s*[〜~\-]\s*(\d+)\s*$")
ODDS_RE = re.compile(r"^\d+(?:\.\d+)?$")
DIGIT_RE = re.compile(r"^[1-9]$")
RANK_RE = re.compile(r"^\d{1,3}$")


def racecard_to_odds_url(racecard_url: str) -> str:
    if "/racecard/" not in racecard_url:
        raise ValueError("WINTICKETの出走表URLではありません。")
    return racecard_url.replace("/racecard/", "/odds/", 1)


def clean_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_popularity_text(text: str) -> list[dict[str, Any]]:
    lines = clean_lines(text)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[int, int, int]] = set()

    for i in range(max(0, len(lines) - 4)):
        rank_text, first, second, third, odds_text = lines[i:i + 5]

        if not RANK_RE.fullmatch(rank_text):
            continue
        if not all(DIGIT_RE.fullmatch(x) for x in (first, second, third)):
            continue
        if len({first, second, third}) != 3:
            continue
        if not ODDS_RE.fullmatch(odds_text):
            continue

        rank = int(rank_text)
        odds = float(odds_text)
        combo = (int(first), int(second), int(third))

        if not 1 <= rank <= 504 or odds <= 1.0 or combo in seen:
            continue

        rows.append(
            {
                "組番": f"{combo[0]}-{combo[1]}-{combo[2]}",
                "オッズ": odds,
                "人気": rank,
            }
        )
        seen.add(combo)

    return rows


def click_if_present(page, label: str) -> None:
    try:
        locator = page.get_by_text(label, exact=True)
        if locator.count() > 0:
            locator.first.click(timeout=3000)
            page.wait_for_timeout(700)
    except Exception:
        pass


def fetch_rows(racecard_url: str, headless: bool) -> tuple[list[dict[str, Any]], list[str]]:
    odds_url = racecard_to_odds_url(racecard_url)
    logs = [f"オッズ取得元: {odds_url}"]
    all_rows: dict[str, dict[str, Any]] = {}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=headless,
                args=["--disable-dev-shm-usage"],
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 1200},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/126 Safari/537.36"
                ),
            )
            page = context.new_page()
            page.goto(odds_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2500)
            logs.append(f"ページタイトル: {page.title()}")

            click_if_present(page, "3連単")
            click_if_present(page, "人気順")

            initial_rows = parse_popularity_text(page.locator("body").inner_text())
            for row in initial_rows:
                all_rows[row["組番"]] = row
            logs.append(f"初期表示から取得: {len(initial_rows)}件")

            range_options: list[str] = []
            range_selector_index: int | None = None

            select_count = page.locator("select").count()
            for index in range(select_count):
                selector = page.locator("select").nth(index)
                options = selector.locator("option").all_text_contents()
                matches = [opt.strip() for opt in options if RANGE_RE.match(opt.strip())]
                if len(matches) > len(range_options):
                    range_options = matches
                    range_selector_index = index

            logs.append(f"範囲選択候補: {1 if range_selector_index is not None else 0}個")

            if range_selector_index is not None:
                logs.append("検出範囲: " + "、".join(range_options))

                for option in range_options:
                    try:
                        # ページ再描画に備えて毎回locatorを取り直す
                        selector = page.locator("select").nth(range_selector_index)
                        selector.select_option(label=option)
                        page.wait_for_timeout(900)
                        rows = parse_popularity_text(page.locator("body").inner_text())
                        for row in rows:
                            all_rows[row["組番"]] = row
                        logs.append(f"{option}: {len(rows)}件")
                    except Exception as exc:
                        logs.append(f"{option}: 切替失敗 {type(exc).__name__}: {exc}")
            else:
                logs.append("範囲選択を検出できず、初期表示分のみ取得しました。")

            context.close()
            browser.close()

    except PlaywrightTimeoutError:
        logs.append("エラー: オッズページの読み込みがタイムアウトしました。")
        return [], logs
    except Exception as exc:
        logs.append(f"エラー: {type(exc).__name__}: {exc}")
        return [], logs

    rows = sorted(
        all_rows.values(),
        key=lambda row: (row.get("人気", 9999), row["組番"]),
    )
    logs.append(f"最終取得件数: {len(rows)}件")
    return rows, logs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--racecard-url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    rows, logs = fetch_rows(args.racecard_url, args.headless)
    Path(args.output).write_text(
        json.dumps(
            {"rows": rows, "logs": logs},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
