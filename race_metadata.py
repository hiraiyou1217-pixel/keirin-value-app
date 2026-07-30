from __future__ import annotations

import math
import re
from typing import Any
from urllib.parse import urlparse


PREFECTURES = (
    "北海道",
    "青森",
    "岩手",
    "宮城",
    "秋田",
    "山形",
    "福島",
    "茨城",
    "栃木",
    "群馬",
    "埼玉",
    "千葉",
    "東京",
    "神奈川",
    "新潟",
    "富山",
    "石川",
    "福井",
    "山梨",
    "長野",
    "岐阜",
    "静岡",
    "愛知",
    "三重",
    "滋賀",
    "京都",
    "大阪",
    "兵庫",
    "奈良",
    "和歌山",
    "鳥取",
    "島根",
    "岡山",
    "広島",
    "山口",
    "徳島",
    "香川",
    "愛媛",
    "高知",
    "福岡",
    "佐賀",
    "長崎",
    "熊本",
    "大分",
    "宮崎",
    "鹿児島",
    "沖縄",
)

PREFECTURE_PATTERN = "|".join(
    re.escape(value)
    for value in PREFECTURES
)

REGION_BY_PREFECTURE = {
    **{
        value: "north"
        for value in (
            "北海道",
            "青森",
            "岩手",
            "宮城",
            "秋田",
            "山形",
            "福島",
        )
    },
    **{
        value: "kanto"
        for value in (
            "茨城",
            "栃木",
            "群馬",
            "埼玉",
            "千葉",
            "東京",
            "神奈川",
            "新潟",
            "山梨",
            "長野",
        )
    },
    **{
        value: "chubu"
        for value in (
            "富山",
            "石川",
            "福井",
            "岐阜",
            "静岡",
            "愛知",
            "三重",
        )
    },
    **{
        value: "kinki"
        for value in (
            "滋賀",
            "京都",
            "大阪",
            "兵庫",
            "奈良",
            "和歌山",
        )
    },
    **{
        value: "chugoku"
        for value in (
            "鳥取",
            "島根",
            "岡山",
            "広島",
            "山口",
        )
    },
    **{
        value: "shikoku"
        for value in (
            "徳島",
            "香川",
            "愛媛",
            "高知",
        )
    },
    **{
        value: "kyushu"
        for value in (
            "福岡",
            "佐賀",
            "長崎",
            "熊本",
            "大分",
            "宮崎",
            "鹿児島",
            "沖縄",
        )
    },
}

# 周長・みなし直線・最大カント。
# 出典: Gamboo 競輪場データ集
# https://gamboo.jp/pages/?tid=tohyama_bank_LP
# 2025年10月15日現在として掲載された値。
VENUE_CHARACTERISTICS: dict[
    str,
    tuple[float, float, float],
] = {
    "函館": (400.0, 51.3, 30.61),
    "青森": (400.0, 58.9, 32.25),
    "いわき平": (400.0, 62.7, 32.91),
    "弥彦": (400.0, 63.1, 32.41),
    "前橋": (335.0, 46.7, 36.00),
    "取手": (400.0, 54.8, 31.51),
    "宇都宮": (500.0, 63.3, 25.80),
    "大宮": (500.0, 66.7, 26.28),
    "西武園": (400.0, 47.6, 29.45),
    "京王閣": (400.0, 51.5, 32.18),
    "立川": (400.0, 58.0, 31.22),
    "松戸": (333.0, 38.2, 29.75),
    "川崎": (400.0, 58.0, 32.17),
    "平塚": (400.0, 54.2, 31.48),
    "小田原": (333.0, 36.1, 35.57),
    "伊東": (333.0, 46.6, 34.69),
    "静岡": (400.0, 56.4, 30.72),
    "名古屋": (400.0, 58.8, 34.03),
    "岐阜": (400.0, 59.3, 32.25),
    "大垣": (400.0, 56.0, 30.62),
    "豊橋": (400.0, 60.3, 33.84),
    "富山": (333.0, 43.0, 33.69),
    "松阪": (400.0, 61.5, 34.42),
    "四日市": (400.0, 62.4, 32.25),
    "福井": (400.0, 52.8, 31.48),
    "奈良": (333.0, 38.0, 33.43),
    "向日町": (400.0, 47.3, 30.48),
    "和歌山": (400.0, 59.9, 32.25),
    "岸和田": (400.0, 56.7, 30.93),
    "玉野": (400.0, 47.9, 30.63),
    "広島": (400.0, 57.9, 32.53),
    "防府": (333.0, 42.5, 34.69),
    "高松": (400.0, 54.8, 33.26),
    "小松島": (400.0, 55.5, 29.77),
    "高知": (500.0, 52.0, 24.50),
    "松山": (400.0, 58.6, 34.03),
    "小倉": (400.0, 56.9, 34.03),
    "久留米": (400.0, 50.7, 31.48),
    "武雄": (400.0, 64.4, 32.01),
    "佐世保": (400.0, 40.2, 31.48),
    "別府": (400.0, 59.9, 33.69),
    "熊本": (400.0, 60.3, 34.26),
}

VENUE_REGION = {
    **{
        value: "north"
        for value in (
            "函館",
            "青森",
            "いわき平",
        )
    },
    **{
        value: "kanto"
        for value in (
            "弥彦",
            "前橋",
            "取手",
            "宇都宮",
            "大宮",
            "西武園",
            "京王閣",
            "立川",
        )
    },
    **{
        value: "south_kanto"
        for value in (
            "松戸",
            "川崎",
            "平塚",
            "小田原",
            "伊東",
            "静岡",
        )
    },
    **{
        value: "chubu"
        for value in (
            "名古屋",
            "岐阜",
            "大垣",
            "豊橋",
            "富山",
            "松阪",
            "四日市",
        )
    },
    **{
        value: "kinki"
        for value in (
            "福井",
            "奈良",
            "向日町",
            "和歌山",
            "岸和田",
        )
    },
    **{
        value: "chugoku"
        for value in (
            "玉野",
            "広島",
            "防府",
        )
    },
    **{
        value: "shikoku"
        for value in (
            "高松",
            "小松島",
            "高知",
            "松山",
        )
    },
    **{
        value: "kyushu"
        for value in (
            "小倉",
            "久留米",
            "武雄",
            "佐世保",
            "別府",
            "熊本",
        )
    },
}


def normalize_venue_key(
    value: Any,
) -> str:
    venue = re.sub(
        r"\s+",
        "",
        str(value or "").strip(),
    )

    for suffix in (
        "競輪場",
        "競輪",
    ):
        if venue.endswith(suffix):
            venue = venue[
                : -len(suffix)
            ]
            break

    if venue.lower() in (
        "iwakidaira",
        "iwakitaira",
    ):
        return "いわき平"

    return venue


def get_venue_characteristics(
    venue: Any,
) -> dict[str, Any]:
    venue_key = normalize_venue_key(
        venue
    )
    values = VENUE_CHARACTERISTICS.get(
        venue_key
    )

    if values is None:
        return {
            "venue_key": venue_key,
            "bank_length_m": 0.0,
            "home_straight_m": 0.0,
            "max_cant_degrees": 0.0,
            "venue_characteristics_known": 0.0,
            "venue_region": (
                VENUE_REGION.get(
                    venue_key,
                    "",
                )
            ),
        }

    return {
        "venue_key": venue_key,
        "bank_length_m": values[0],
        "home_straight_m": values[1],
        "max_cant_degrees": values[2],
        "venue_characteristics_known": 1.0,
        "venue_region": (
            VENUE_REGION.get(
                venue_key,
                "",
            )
        ),
    }


def parse_rider_profile(
    value: Any,
    cyclist_url: Any = "",
) -> dict[str, Any]:
    text = " ".join(
        str(value or "").split()
    )
    profile_match = re.search(
        rf"\b({PREFECTURE_PATTERN})\s+"
        r"([ASL]\d)\s+"
        r"(\d{1,2})歳\s+"
        r"(\d{1,3})期\b",
        text,
    )
    cyclist_match = re.search(
        r"/keirin/cyclist/(\d+)",
        str(cyclist_url or ""),
    )

    if profile_match:
        name = text[
            : profile_match.start()
        ].strip()
        prefecture = profile_match.group(1)
        class_name = profile_match.group(2)
        age = int(profile_match.group(3))
        generation = int(
            profile_match.group(4)
        )
    else:
        name = text.split()[0] if text else ""
        prefecture = ""
        class_name = ""
        age = None
        generation = None

    return {
        "選手名": name,
        "選手ID": (
            cyclist_match.group(1)
            if cyclist_match
            else ""
        ),
        "府県": prefecture,
        "級班": class_name,
        "年齢": age,
        "期別": generation,
        "選手URL": str(
            cyclist_url or ""
        ),
    }


def _first_stage_line(
    body_text: str,
) -> str:
    stage_words = (
        "予選",
        "準決",
        "決勝",
        "一般",
        "特選",
        "選抜",
        "優秀",
    )

    for raw_line in body_text.splitlines():
        line = " ".join(
            raw_line.split()
        )

        if (
            re.match(
                r"^(?:S級|A級|L級)",
                line,
            )
            and any(
                word in line
                for word in stage_words
            )
            and len(line) <= 20
        ):
            return line

    return ""


def _race_class_from_stage(
    stage: str,
) -> str:
    if stage.startswith("S級"):
        return "S級"

    if stage.startswith("L級"):
        return "L級"

    if stage.startswith("A級チ"):
        return "A級3班"

    if stage.startswith("A級"):
        return "A級"

    return ""


def parse_race_conditions(
    *,
    page_title: Any,
    body_text: Any,
    racecard_url: Any = "",
) -> dict[str, Any]:
    title = str(page_title or "")
    body = str(body_text or "")
    combined = f"{title}\n{body}"
    grade_match = re.search(
        r"(?<![A-Z0-9])"
        r"(KEIRINグランプリ|GP|G[123]|F[12])"
        r"(?![A-Z0-9])",
        combined,
        re.IGNORECASE,
    )
    start_match = re.search(
        r"発走\s*(\d{1,2}:\d{2})",
        body,
    )
    condition_match = re.search(
        r"(\d[\d,]*)m\s*"
        r"\((\d+)周\)\s*"
        r"(晴|曇|雨|雪)\s*"
        r"(-?\d+(?:\.\d+)?)℃\s*"
        r"([東西南北]+)\s*"
        r"(\d+(?:\.\d+)?)m/s",
        body,
    )
    path = urlparse(
        str(racecard_url or "")
    ).path.rstrip("/")
    path_match = re.search(
        r"/racecard/\d+/(\d+)/(\d+)$",
        path,
    )
    stage = _first_stage_line(body)

    return {
        "レースグレード": (
            grade_match.group(1).upper()
            if grade_match
            else ""
        ),
        "レース区分": stage,
        "レース級別": (
            _race_class_from_stage(
                stage
            )
        ),
        "開催日目": (
            int(path_match.group(1))
            if path_match
            else None
        ),
        "発走時刻": (
            start_match.group(1)
            if start_match
            else ""
        ),
        "距離m": (
            int(
                condition_match.group(1)
                .replace(",", "")
            )
            if condition_match
            else None
        ),
        "周回数": (
            int(condition_match.group(2))
            if condition_match
            else None
        ),
        "天候": (
            condition_match.group(3)
            if condition_match
            else ""
        ),
        "気温C": (
            float(condition_match.group(4))
            if condition_match
            else None
        ),
        "風向": (
            condition_match.group(5)
            if condition_match
            else ""
        ),
        "風速mps": (
            float(condition_match.group(6))
            if condition_match
            else None
        ),
    }


def decorate_riders_with_race_conditions(
    riders: list[dict[str, Any]],
    race_conditions: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            **rider,
            **race_conditions,
        }
        for rider in riders
    ]


def extract_race_conditions_from_riders(
    riders: list[dict[str, Any]],
) -> dict[str, Any]:
    if not riders:
        return {}

    source = riders[0]

    return {
        key: source.get(key)
        for key in (
            "レースグレード",
            "レース区分",
            "レース級別",
            "開催日目",
            "発走時刻",
            "距離m",
            "周回数",
            "天候",
            "気温C",
            "風向",
            "風速mps",
            "並び取得方式",
            "並び信頼度",
        )
        if key in source
    }


def class_ordinal(
    value: Any,
) -> float:
    normalized = (
        str(value or "")
        .replace("級", "")
        .replace("班", "")
        .strip()
    )

    return {
        "A3": 1.0,
        "A2": 2.0,
        "A1": 3.0,
        "L1": 3.0,
        "S2": 4.0,
        "S1": 5.0,
    }.get(normalized, 0.0)


def grade_ordinal(
    value: Any,
) -> float:
    grade = str(value or "").upper()

    return {
        "F2": 1.0,
        "F1": 2.0,
        "G3": 3.0,
        "G2": 4.0,
        "G1": 5.0,
        "GP": 6.0,
        "KEIRINグランプリ": 6.0,
    }.get(grade, 0.0)


def stage_features(
    value: Any,
) -> dict[str, float]:
    stage = str(value or "")

    return {
        "stage_preliminary": float(
            "予選" in stage
        ),
        "stage_semifinal": float(
            "準決" in stage
        ),
        "stage_final": float(
            "決勝" in stage
        ),
        "stage_general": float(
            "一般" in stage
        ),
        "stage_special": float(
            "特選" in stage
            or "選抜" in stage
            or "優秀" in stage
        ),
        "stage_girls": float(
            stage.startswith("L級")
        ),
        "stage_challenge": float(
            stage.startswith("A級チ")
        ),
    }


def weather_features(
    value: Any,
) -> dict[str, float]:
    weather = str(value or "")

    return {
        "weather_sunny": float(
            weather == "晴"
        ),
        "weather_cloudy": float(
            weather == "曇"
        ),
        "weather_rain": float(
            weather == "雨"
        ),
        "weather_snow": float(
            weather == "雪"
        ),
        "weather_known": float(
            weather
            in ("晴", "曇", "雨", "雪")
        ),
    }


def wind_direction_features(
    value: Any,
) -> dict[str, float]:
    direction = str(value or "")
    degrees = {
        "北": 0.0,
        "北東": 45.0,
        "東": 90.0,
        "南東": 135.0,
        "南": 180.0,
        "南西": 225.0,
        "西": 270.0,
        "北西": 315.0,
    }.get(direction)

    if degrees is None:
        return {
            "wind_direction_sin": 0.0,
            "wind_direction_cos": 0.0,
            "wind_direction_known": 0.0,
        }

    radians = math.radians(degrees)

    return {
        "wind_direction_sin": math.sin(
            radians
        ),
        "wind_direction_cos": math.cos(
            radians
        ),
        "wind_direction_known": 1.0,
    }


def same_region_feature(
    prefecture: Any,
    venue: Any,
) -> float:
    rider_region = REGION_BY_PREFECTURE.get(
        str(prefecture or ""),
        "",
    )
    venue_region = VENUE_REGION.get(
        normalize_venue_key(venue),
        "",
    )

    if not rider_region or not venue_region:
        return 0.0

    if venue_region == "south_kanto":
        venue_region = "kanto"

    return float(
        rider_region == venue_region
    )
