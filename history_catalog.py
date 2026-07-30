from __future__ import annotations

from datetime import date
from html.parser import HTMLParser
import re
import ssl
from typing import Any
from urllib.parse import urljoin
from urllib.error import URLError
from urllib.request import Request, urlopen


BASE_URL = "https://www.winticket.jp"
RESULT_URL_RE = re.compile(
    r"^https://www\.winticket\.jp/"
    r"keirin/([^/]+)/raceresult/"
    r"(\d+)/(\d+)/(\d+)/?$"
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


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() != "a":
            return

        attributes = dict(attrs)
        href = str(
            attributes.get("href") or ""
        ).strip()

        if href:
            self.hrefs.append(href)


def result_to_racecard_url(
    result_url: str,
) -> str:
    normalized = str(result_url).strip()

    if not RESULT_URL_RE.fullmatch(normalized):
        raise ValueError(
            "WINTICKETの結果URLではありません: "
            f"{normalized}"
        )

    return normalized.replace(
        "/raceresult/",
        "/racecard/",
        1,
    )


def parse_result_catalog_html(
    html: str,
    race_date: str,
) -> list[dict[str, Any]]:
    parser = _AnchorParser()
    parser.feed(str(html))

    output: dict[str, dict[str, Any]] = {}

    for href in parser.hrefs:
        result_url = urljoin(
            BASE_URL,
            href,
        ).split("#", 1)[0].split("?", 1)[0]
        match = RESULT_URL_RE.fullmatch(
            result_url
        )

        if not match:
            continue

        (
            venue_slug,
            event_id,
            day_number_text,
            race_number_text,
        ) = match.groups()
        race_number = int(race_number_text)

        if not 1 <= race_number <= 12:
            continue

        venue = VENUE_NAMES.get(
            venue_slug,
            f"{venue_slug}競輪",
        )

        output[result_url] = {
            "race_date": str(race_date),
            "venue": venue,
            "venue_slug": venue_slug,
            "race_number": race_number,
            "event_id": event_id,
            "day_number": int(
                day_number_text
            ),
            "result_url": result_url,
            "racecard_url": (
                result_to_racecard_url(
                    result_url
                )
            ),
        }

    return sorted(
        output.values(),
        key=lambda item: (
            str(item["venue"]),
            int(item["race_number"]),
            str(item["result_url"]),
        ),
    )


def _ssl_contexts() -> list[ssl.SSLContext]:
    contexts = [
        ssl.create_default_context(),
    ]

    try:
        import certifi
    except ImportError:
        return contexts

    contexts.append(
        ssl.create_default_context(
            cafile=certifi.where()
        )
    )
    return contexts


def fetch_result_catalog(
    selected_date: date,
    timeout_seconds: int = 45,
) -> tuple[list[dict[str, Any]], list[str]]:
    date_text = selected_date.strftime(
        "%Y%m%d"
    )
    race_date = selected_date.isoformat()
    source_url = (
        f"{BASE_URL}/keirin/results/"
        f"{date_text}"
    )
    logs = [
        f"結果一覧取得元: {source_url}",
    ]

    request = Request(
        source_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 "
                "Chrome/126 Safari/537.36"
            ),
            "Accept-Language": "ja-JP,ja;q=0.9",
        },
    )

    last_error: URLError | None = None
    html = ""

    for context in _ssl_contexts():
        try:
            with urlopen(
                request,
                timeout=int(
                    timeout_seconds
                ),
                context=context,
            ) as response:
                encoding = (
                    response.headers
                    .get_content_charset()
                    or "utf-8"
                )
                html = response.read().decode(
                    encoding,
                    errors="replace",
                )
            break
        except URLError as exc:
            last_error = exc

    if not html:
        if last_error is not None:
            raise last_error

        raise RuntimeError(
            "結果一覧HTMLを取得できませんでした。"
        )

    entries = parse_result_catalog_html(
        html,
        race_date,
    )

    venues = sorted(
        {
            str(item["venue"])
            for item in entries
        }
    )

    logs.append(
        f"発見競輪場数: {len(venues)}"
    )
    logs.append(
        f"発見結果URL数: {len(entries)}"
    )

    if venues:
        logs.append(
            "発見競輪場: "
            + "、".join(venues)
        )

    return entries, logs
