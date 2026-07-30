from __future__ import annotations

import html
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    ROOT
    / "app"
    / "src"
    / "main"
    / "assets"
    / "extract_racecard.js"
)
CATALOG_SCRIPT_PATH = (
    ROOT
    / "app"
    / "src"
    / "main"
    / "assets"
    / "extract_catalog.js"
)


def _row(
    car_number: int,
    *,
    omit_frame: bool = False,
) -> str:
    values = [
        str(car_number),
        str(car_number),
        (
            f"検証選手{car_number}\n"
            f"東京 A3 30歳 {120 + car_number}期"
        ),
        "",
        f"{70 + car_number}.25",
        str(car_number),
        str(car_number + 1),
        str(car_number + 2),
        "逃" if car_number == 1 else "追",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "10.0",
        "20.0",
        "30.0",
        "3.92",
        f"{car_number}番のコメント。",
        "",
    ]

    if omit_frame:
        values.pop(0)

    cells = "".join(
        "<td>"
        + html.escape(value).replace(
            "\n",
            "<br>",
        )
        + "</td>"
        for value in values
    )
    return f"<tr>{cells}</tr>"


def main() -> None:
    headers = [
        "枠",
        "車",
        "選手名",
        "AI",
        "競走得点",
        "S",
        "H",
        "B",
        "脚",
        "逃",
        "捲",
        "差",
        "マ",
        "1着",
        "2着",
        "3着",
        "着外",
        "勝率",
        "２連対率",
        "３連対率",
        "ギヤ倍率",
        "コメント",
        "メモ",
    ]
    header_html = "".join(
        f"<th>{html.escape(value)}</th>"
        for value in headers
    )
    body_html = "".join(
        _row(
            number,
            omit_frame=number == 7,
        )
        for number in range(1, 8)
    )
    lineup_html = "".join(
        (
            "<span style='display:inline-block;"
            "width:24px;height:24px;margin-right:6px'>"
            f"{number}</span>"
        )
        for number in (1, 5, 7, 2, 6, 3, 4)
    )
    document = f"""
    <!doctype html>
    <html>
      <head><title>青森競輪 1レース 出走表</title></head>
      <body>
        <table>
          <tr><th>別表</th></tr>
          <tr><td>対象外</td></tr>
        </table>
        <table>
          <tr>{header_html}</tr>
          {body_html}
        </table>
        <section>
          <h2>並び予想</h2>
          <div>{lineup_html}</div>
        </section>
      </body>
    </html>
    """
    script = SCRIPT_PATH.read_text(
        encoding="utf-8"
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True
        )
        page = browser.new_page(
            viewport={
                "width": 1200,
                "height": 1000,
            }
        )
        page.set_content(document)
        payload = json.loads(
            page.evaluate(script)
        )
        page.set_content(
            """
            <a href="https://www.winticket.jp/keirin/aomori/racecard/2026073012/1/1">
              青森 1R
            </a>
            <a href="https://www.winticket.jp/keirin/aomori/racecard/2026073012/1/2">
              青森 2R
            </a>
            <a href="https://example.com/not-a-race">
              対象外
            </a>
            """
        )
        catalog_payload = json.loads(
            page.evaluate(
                CATALOG_SCRIPT_PATH.read_text(
                    encoding="utf-8"
                )
            )
        )
        browser.close()

    assert payload["ok"] is True
    assert len(payload["riders"]) == 7
    assert payload["riders"][0]["name"] == (
        "検証選手1"
    )
    assert payload["riders"][6]["carNumber"] == 7
    assert payload["riders"][6]["comment"] == (
        "7番のコメント。"
    )
    assert len(payload["lineupItems"]) == 7
    assert catalog_payload["ok"] is True
    assert len(catalog_payload["races"]) == 2
    assert (
        catalog_payload["races"][0]["venue"]
        == "青森競輪"
    )
    print(
        json.dumps(
            {
                "success": True,
                "riders": len(
                    payload["riders"]
                ),
                "lineup_items": len(
                    payload["lineupItems"]
                ),
                "catalog_races": len(
                    catalog_payload["races"]
                ),
                "omitted_frame_cell": True,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
