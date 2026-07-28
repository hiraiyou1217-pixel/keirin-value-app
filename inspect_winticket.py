from __future__ import annotations

import html
import re
import ssl
from pathlib import Path
from urllib.request import Request, urlopen

import certifi


URL = "https://www.winticket.jp/keirin/tamano/odds/2026072761/2/12"

request = Request(
    URL,
    headers={
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 Chrome/126 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/json",
        "Accept-Language": "ja-JP,ja;q=0.9",
    },
)

context = ssl.create_default_context(cafile=certifi.where())

with urlopen(request, timeout=30, context=context) as response:
    raw = response.read()

text = raw.decode("utf-8", errors="replace")
decoded = html.unescape(text)

Path("winticket_debug.html").write_text(text, encoding="utf-8")

print(f"受信サイズ: {len(raw):,} bytes")
print(f"scriptタグ数: {len(re.findall(r'<script', text, re.I))}")
print(f'文字列 "51 〜 100": {decoded.count("51 〜 100")}件')
print(f'文字列 "201 〜 210": {decoded.count("201 〜 210")}件')
print(f'文字列 "7.8": {decoded.count("7.8")}件')

patterns = {
    "配列型": r'[\["\']7["\']\s*,\s*["\']4["\']\s*,\s*["\']3["\']\s*,\s*7\.8',
    "文字列型": r'7[^0-9]{1,20}4[^0-9]{1,20}3[^0-9]{1,30}7\.8',
    "oddsキー": r'.{0,150}odds.{0,300}7\.8.{0,150}',
}

for name, pattern in patterns.items():
    matches = list(re.finditer(pattern, decoded, re.I | re.S))
    print(f"\n{name}: {len(matches)}件")

    for match in matches[:3]:
        start = max(0, match.start() - 300)
        end = min(len(decoded), match.end() + 300)
        snippet = decoded[start:end]
        snippet = re.sub(r"\s+", " ", snippet)
        print("---")
        print(snippet[:1200])

script_sources = re.findall(
    r'<script[^>]+src=["\']([^"\']+)["\']',
    text,
    re.I,
)

print(f"\n外部JavaScript数: {len(script_sources)}")

for source in script_sources:
    print(source)

print("\n診断HTML保存先:")
print(Path("winticket_debug.html").resolve())
