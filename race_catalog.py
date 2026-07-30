from __future__ import annotations

from collections import defaultdict
from datetime import date
import re
from typing import Any
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://www.winticket.jp"

# 現在のWINTICKETレースURL例:
# /keirin/toyohashi/racecard/2026072545/4/1
RACE_URL_RE = re.compile(
    r"/keirin/([^/]+)/racecard/(\d+)/(\d+)/(\d+)/?$"
)

VENUE_NAMES = {
    "hakodate": "函館競輪",
    "aomori": "青森競輪",
    "iwakidaira": "いわき平競輪",
    "iwakitaira": "いわき平競輪",
    "yahiko": "弥彦競輪",
    "maebashi": "前橋競輪",
    "toride": "取手競輪",
    "utsunomiya": "宇都宮競輪",
    "omiya": "大宮競輪",
    "seibuen": "西武園競輪",
    "keiokaku": "京王閣競輪",
    "tachikawa": "立川競輪",
    "matsudo": "松戸競輪",
    "chiba": "千葉競輪",
    "kawasaki": "川崎競輪",
    "hiratsuka": "平塚競輪",
    "odawara": "小田原競輪",
    "ito": "伊東競輪",
    "shizuoka": "静岡競輪",
    "nagoya": "名古屋競輪",
    "gifu": "岐阜競輪",
    "ogaki": "大垣競輪",
    "toyohashi": "豊橋競輪",
    "toyama": "富山競輪",
    "matsusaka": "松阪競輪",
    "yokkaichi": "四日市競輪",
    "fukui": "福井競輪",
    "nara": "奈良競輪",
    "mukomachi": "向日町競輪",
    "wakayama": "和歌山競輪",
    "kishiwada": "岸和田競輪",
    "tamano": "玉野競輪",
    "hiroshima": "広島競輪",
    "hofu": "防府競輪",
    "takamatsu": "高松競輪",
    "komatsushima": "小松島競輪",
    "kochi": "高知競輪",
    "matsuyama": "松山競輪",
    "kokura": "小倉競輪",
    "kurume": "久留米競輪",
    "takeo": "武雄競輪",
    "sasebo": "佐世保競輪",
    "beppu": "別府競輪",
    "kumamoto": "熊本競輪",
}


def fetch_race_catalog(
    selected_date: date,
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
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
        logs.append(
            "install.commandを再実行し、Chromiumが入っているか確認してください。"
        )
        return {}, logs

    seen: set[str] = set()

    for anchor in anchors:
        href = anchor.get("href", "")
        full_url = urljoin(BASE_URL, href)
        match = RACE_URL_RE.search(full_url)

        if not match or full_url in seen:
            continue

        venue_slug, event_id, day_number, race_number_text = match.groups()
        race_number = int(race_number_text)

        if not 1 <= race_number <= 12:
            continue

        venue_name = VENUE_NAMES.get(venue_slug, f"{venue_slug}競輪")

        grouped[venue_name].append(
            {
                "race_number": race_number,
                "url": full_url,
                "venue_slug": venue_slug,
                "event_id": event_id,
                "day_number": int(day_number),
            }
        )
        seen.add(full_url)

    result: dict[str, list[dict[str, Any]]] = {}

    for venue, races in grouped.items():
        unique_by_number: dict[int, dict[str, Any]] = {}
        for race in races:
            unique_by_number[race["race_number"]] = race

        result[venue] = sorted(
            unique_by_number.values(),
            key=lambda item: item["race_number"],
        )

    result = dict(sorted(result.items(), key=lambda item: item[0]))

    logs.append(f"ページ内リンク数: {len(anchors)}")
    logs.append(f"検出競輪場数: {len(result)}")
    logs.append(f"検出レース数: {sum(len(races) for races in result.values())}")

    if result:
        logs.append("検出競輪場: " + "、".join(result.keys()))
    else:
        logs.append(
            "開催情報を検出できませんでした。取得ログとWINTICKETのページ構造を"
            "確認してください。"
        )

    return result, logs
