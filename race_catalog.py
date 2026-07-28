from __future__ import annotations

from collections import defaultdict
from datetime import date
import re
from typing import Any
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://www.winticket.jp"
VENUE_RE = re.compile(r"/keirin/([^/]+)/racecard/(\d{10,})/?$")
RACE_TEXT_RE = re.compile(r"(?<!\d)(1[0-2]|[1-9])\s*R\b", re.IGNORECASE)


def _venue_name_from_text(text: str, slug: str) -> str:
    cleaned = " ".join(text.split())
    match = re.search(r"([^\s]{1,12}競輪)", cleaned)
    if match:
        return match.group(1)
    return slug


def _race_number_from_url_or_text(url: str, text: str) -> int | None:
    match = RACE_TEXT_RE.search(text)
    if match:
        return int(match.group(1))

    digits_match = re.search(r"/racecard/(\d{10,})/?$", url)
    if not digits_match:
        return None

    digits = digits_match.group(1)
    # WINTICKETのイベントID末尾を候補として扱う。
    candidates = []
    if len(digits) >= 2:
        candidates.append(int(digits[-2:]))
    candidates.append(int(digits[-1:]))

    for candidate in candidates:
        if 1 <= candidate <= 12:
            return candidate
    return None


def fetch_race_catalog(selected_date: date) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    date_text = selected_date.strftime("%Y%m%d")
    source_url = f"{BASE_URL}/keirin/racecard/{date_text}"
    logs = [f"取得元: {source_url}"]

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={"width": 1440, "height": 1100},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/126 Safari/537.36"
                ),
            )
            page.goto(source_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3500)

            logs.append(f"ページタイトル: {page.title()}")
            anchors = page.locator("a").evaluate_all(
                """els => els.map(a => ({
                    href: a.getAttribute('href') || '',
                    text: (a.innerText || a.textContent || '').trim()
                }))"""
            )
            browser.close()

    except PlaywrightTimeoutError:
        logs.append("エラー: ページの読み込みがタイムアウトしました。")
        return {}, logs
    except Exception as exc:
        logs.append(f"エラー: {type(exc).__name__}: {exc}")
        logs.append("install.commandを再実行し、Chromiumが入っているか確認してください。")
        return {}, logs

    seen: set[str] = set()
    for anchor in anchors:
        href = anchor.get("href", "")
        text = anchor.get("text", "")
        full_url = urljoin(BASE_URL, href)
        match = VENUE_RE.search(full_url)
        if not match or full_url in seen:
            continue

        slug = match.group(1)
        race_number = _race_number_from_url_or_text(full_url, text)
        if race_number is None:
            continue

        venue_name = _venue_name_from_text(text, slug)
        grouped[venue_name].append(
            {
                "race_number": race_number,
                "url": full_url,
                "venue_slug": slug,
            }
        )
        seen.add(full_url)

    result: dict[str, list[dict[str, Any]]] = {}
    for venue, races in grouped.items():
        unique_by_number = {}
        for race in races:
            unique_by_number[race["race_number"]] = race
        result[venue] = sorted(unique_by_number.values(), key=lambda x: x["race_number"])

    result = dict(sorted(result.items(), key=lambda x: x[0]))
    logs.append(f"検出競輪場数: {len(result)}")
    logs.append(f"検出レース数: {sum(len(v) for v in result.values())}")

    if not result:
        logs.append(
            "開催情報を検出できませんでした。開催のない日、未来日の未掲載、"
            "またはWINTICKETの画面変更が考えられます。"
        )

    return result, logs
