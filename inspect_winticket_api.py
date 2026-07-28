from __future__ import annotations

from html import unescape
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import re
import ssl

import certifi


PAGE_URL = (
    "https://www.winticket.jp/keirin/"
    "tamano/odds/2026072761/2/12"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/126 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "ja-JP,ja;q=0.9",
}

SSL_CONTEXT = ssl.create_default_context(
    cafile=certifi.where()
)


def download(url: str) -> str:
    request = Request(url, headers=HEADERS)

    with urlopen(
        request,
        timeout=30,
        context=SSL_CONTEXT,
    ) as response:
        raw = response.read()
        charset = (
            response.headers.get_content_charset()
            or "utf-8"
        )

    return raw.decode(charset, errors="replace")


html = download(PAGE_URL)

script_sources = re.findall(
    r'<script[^>]+src=["\']([^"\']+)["\']',
    html,
    re.I,
)

script_urls = list(
    dict.fromkeys(
        urljoin(PAGE_URL, unescape(source))
        for source in script_sources
    )
)

print(f"外部JavaScript数: {len(script_urls)}")

output_directory = Path("winticket_js")
output_directory.mkdir(exist_ok=True)

# APIやオッズ取得処理に関係しそうな文字列
patterns = [
    r"https?://[^\"'`\s]+",
    r"/api/[^\"'`\s]+",
    r"/v\d+/[^\"'`\s]+",
    r"graphql",
    r"odds",
    r"trifecta",
    r"popular",
    r"popularity",
    r"raceId",
    r"race_id",
    r"eventId",
    r"event_id",
    r"offset",
    r"limit",
    r"cursor",
    r"startIndex",
    r"start_index",
]

results: list[str] = []

for index, script_url in enumerate(script_urls, start=1):
    print(
        f"[{index}/{len(script_urls)}] "
        f"{script_url}"
    )

    try:
        script = download(script_url)
    except Exception as exc:
        results.append(
            f"\n### 取得失敗\n"
            f"URL: {script_url}\n"
            f"{type(exc).__name__}: {exc}\n"
        )
        continue

    filename = (
        output_directory
        / f"script_{index:02d}.js"
    )
    filename.write_text(
        script,
        encoding="utf-8",
    )

    lower_script = script.lower()

    relevant = any(
        keyword in lower_script
        for keyword in (
            "odds",
            "trifecta",
            "popularity",
            "raceid",
            "race_id",
            "/api/",
            "graphql",
        )
    )

    if not relevant:
        continue

    results.append(
        "\n"
        + "=" * 80
        + f"\nJavaScript: {script_url}\n"
        + f"サイズ: {len(script):,}文字\n"
    )

    found_values: set[str] = set()

    for pattern in patterns:
        for match in re.finditer(
            pattern,
            script,
            re.I,
        ):
            start = max(0, match.start() - 250)
            end = min(
                len(script),
                match.end() + 500,
            )

            snippet = script[start:end]
            snippet = re.sub(
                r"\s+",
                " ",
                snippet,
            )

            if snippet in found_values:
                continue

            found_values.add(snippet)

            results.append(
                "\n--- 候補 ---\n"
                + snippet[:1200]
                + "\n"
            )

            if len(found_values) >= 30:
                break

        if len(found_values) >= 30:
            break


report_path = Path(
    "winticket_api_candidates.txt"
)

report_path.write_text(
    "".join(results),
    encoding="utf-8",
)

print()
print("解析完了")
print(f"候補レポート: {report_path.resolve()}")
print(
    f"保存JavaScript: "
    f"{output_directory.resolve()}"
)
print(
    f"候補レポートサイズ: "
    f"{report_path.stat().st_size:,} bytes"
)
