from __future__ import annotations

import re
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


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _parse_popularity_text(text: str) -> list[dict[str, Any]]:
    """
    人気順表示の並び:
    人気順位 → 1着車番 → 2着車番 → 3着車番 → オッズ
    を連続行から抽出する。
    """
    lines = _clean_lines(text)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[int, int, int]] = set()

    for i in range(0, max(0, len(lines) - 4)):
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

        if not 1 <= rank <= 504:
            continue
        if odds <= 1.0:
            continue
        if combo in seen:
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


def _select_popularity_mode(page) -> None:
    # 「3連単」「人気順」を明示的に選択。既に選択済みなら何もしない。
    for label in ("3連単", "人気順"):
        try:
            locator = page.get_by_text(label, exact=True)
            if locator.count() > 0:
                locator.first.click(timeout=3000)
                page.wait_for_timeout(800)
        except Exception:
            pass


def _range_selectors(page) -> list[tuple[Any, list[str]]]:
    candidates = []
    for i in range(page.locator("select").count()):
        selector = page.locator("select").nth(i)
        try:
            options = selector.locator("option").all_text_contents()
        except Exception:
            continue

        range_options = [opt.strip() for opt in options if RANGE_RE.match(opt.strip())]
        if range_options:
            candidates.append((selector, range_options))
    return candidates


def fetch_trifecta_odds(
    racecard_url: str,
    headless: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    odds_url = racecard_to_odds_url(racecard_url)
    logs = [f"オッズ取得元: {odds_url}"]
    all_rows: dict[str, dict[str, Any]] = {}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            page = browser.new_page(
                viewport={"width": 1440, "height": 1200},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/126 Safari/537.36"
                ),
            )
            page.goto(odds_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)
            logs.append(f"ページタイトル: {page.title()}")

            _select_popularity_mode(page)

            initial_rows = _parse_popularity_text(page.locator("body").inner_text())
            for row in initial_rows:
                all_rows[row["組番"]] = row
            logs.append(f"初期表示から取得: {len(initial_rows)}件")

            candidates = _range_selectors(page)
            logs.append(f"範囲選択候補: {len(candidates)}個")

            if candidates:
                selector, options = max(candidates, key=lambda item: len(item[1]))
                logs.append("検出範囲: " + "、".join(options))

                for option in options:
                    try:
                        selector.select_option(label=option)
                        page.wait_for_timeout(1200)
                        text = page.locator("body").inner_text()
                        rows = _parse_popularity_text(text)
                        for row in rows:
                            all_rows[row["組番"]] = row
                        logs.append(f"{option}: {len(rows)}件")
                    except Exception as exc:
                        logs.append(f"{option}: 切替失敗 {type(exc).__name__}: {exc}")
            else:
                logs.append(
                    "50件範囲のselect要素を検出できませんでした。"
                    "初期表示分のみを返します。"
                )

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
    if len(rows) < 50:
        logs.append(
            "取得件数が少なすぎます。発売前・発売終了・画面変更・"
            "人気順以外の表示になっている可能性があります。"
        )
    elif len(rows) < 210:
        logs.append(
            "210通り未満です。出走人数が7車未満、または一部範囲の切替に"
            "失敗した可能性があります。"
        )

    return rows, logs
