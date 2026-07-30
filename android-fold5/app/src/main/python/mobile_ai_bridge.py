from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any


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
RACE_URL_PATTERN = re.compile(
    r"/keirin/([^/]+)/racecard/"
    r"(\d{8})\d*/(\d+)/(\d+)/?$"
)
_MODEL_CACHE: dict[
    str,
    tuple[int, dict[str, Any]],
] = {}


def group_lineup_geometry(
    items: list[dict[str, Any]],
    rider_numbers: list[int],
) -> list[list[int]]:
    valid = set(rider_numbers)
    candidates = [
        {
            **item,
            "number": int(
                item.get("number", 0)
            ),
            "x": float(item.get("x", 0.0)),
            "y": float(item.get("y", 0.0)),
            "width": max(
                1.0,
                float(item.get("width", 1.0)),
            ),
            "height": max(
                1.0,
                float(item.get("height", 1.0)),
            ),
        }
        for item in items
        if int(item.get("number", 0) or 0)
        in valid
    ]

    if not candidates:
        return []

    semantic: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for item in candidates:
        group_key = str(
            item.get("groupKey", "")
        )

        if group_key:
            semantic.setdefault(
                group_key,
                [],
            ).append(item)

    semantic_groups = [
        sorted(
            {
                int(item["number"]): item
                for item in group
            }.values(),
            key=lambda item: (
                item["y"],
                item["x"],
            ),
        )
        for group in semantic.values()
    ]
    semantic_numbers = [
        int(item["number"])
        for group in semantic_groups
        for item in group
    ]

    if (
        len(semantic_groups) >= 2
        and any(
            len(group) >= 2
            for group in semantic_groups
        )
        and len(semantic_numbers)
        == len(set(semantic_numbers))
        and set(semantic_numbers) == valid
    ):
        ordered = sorted(
            semantic_groups,
            key=lambda group: (
                min(
                    item["y"]
                    for item in group
                ),
                min(
                    item["x"]
                    for item in group
                ),
            ),
        )

        return [
            [
                int(item["number"])
                for item in group
            ]
            for group in ordered
        ]

    by_number: dict[
        int,
        dict[str, Any],
    ] = {}

    for item in sorted(
        candidates,
        key=lambda value: (
            value["y"],
            value["x"],
        ),
    ):
        by_number.setdefault(
            int(item["number"]),
            item,
        )

    if set(by_number) != valid:
        return []

    ordered_items = sorted(
        by_number.values(),
        key=lambda item: (
            item["y"],
            item["x"],
        ),
    )
    row_tolerance = max(
        8.0,
        max(
            float(item["height"])
            for item in ordered_items
        )
        * 0.6,
    )
    rows: list[list[dict[str, Any]]] = []

    for item in ordered_items:
        if (
            not rows
            or abs(
                item["y"]
                - rows[-1][0]["y"]
            )
            > row_tolerance
        ):
            rows.append([item])
        else:
            rows[-1].append(item)

    groups: list[list[int]] = []

    for row in rows:
        row.sort(key=lambda item: item["x"])

        if len(row) == 1:
            groups.append(
                [int(row[0]["number"])]
            )
            continue

        edge_gaps = [
            max(
                0.0,
                row[index + 1]["x"]
                - (
                    row[index]["x"]
                    + row[index]["width"]
                ),
            )
            for index in range(
                len(row) - 1
            )
        ]
        sorted_gaps = sorted(edge_gaps)
        typical_gap = sorted_gaps[
            (len(sorted_gaps) - 1) // 2
        ]
        boundary_threshold = max(
            8.0,
            typical_gap * 1.8,
        )
        current = [
            int(row[0]["number"])
        ]

        for index, gap in enumerate(
            edge_gaps
        ):
            if gap >= boundary_threshold:
                groups.append(current)
                current = []

            current.append(
                int(
                    row[index + 1][
                        "number"
                    ]
                )
            )

        groups.append(current)

    flattened = [
        number
        for group in groups
        for number in group
    ]

    if (
        len(flattened)
        != len(set(flattened))
        or set(flattened) != valid
    ):
        return []

    return groups


def _target_details(
    racecard_url: str,
) -> dict[str, Any]:
    match = RACE_URL_PATTERN.search(
        str(racecard_url).strip()
    )

    if not match:
        raise RuntimeError(
            "個別出走表URLから"
            "開催日・競輪場・R番号を"
            "確定できません。"
        )

    slug = match.group(1).lower()
    venue = VENUE_NAMES.get(slug)

    if not venue:
        raise RuntimeError(
            "未対応の競輪場URLです: " + slug
        )

    race_date = match.group(2)
    race_date = (
        f"{race_date[:4]}-"
        f"{race_date[4:6]}-"
        f"{race_date[6:8]}"
    )
    race_number = int(match.group(4))

    return {
        "race_date": race_date,
        "venue": venue,
        "day_number": int(match.group(3)),
        "race_number": race_number,
        "race_id": (
            f"{race_date}_{venue}_{race_number}"
        ),
    }


def _load_model(path: Path) -> dict[str, Any]:
    cache_key = str(path.resolve())
    modified = path.stat().st_mtime_ns
    cached = _MODEL_CACHE.get(cache_key)

    if cached and cached[0] == modified:
        return cached[1]

    model = json.loads(
        path.read_text(encoding="utf-8")
    )
    _MODEL_CACHE[cache_key] = (
        modified,
        model,
    )
    return model


def _rider_payload(
    raw_rider: dict[str, Any],
) -> dict[str, Any]:
    from race_metadata import (
        parse_rider_profile,
    )

    name = str(raw_rider.get("name") or "")
    profile_text = str(
        raw_rider.get("profile") or ""
    )
    profile = parse_rider_profile(
        f"{name} {profile_text}",
        raw_rider.get("cyclistUrl", ""),
    )

    return {
        "車番": int(raw_rider["carNumber"]),
        **profile,
        "競走得点": raw_rider.get("score"),
        "脚質": str(
            raw_rider.get("style") or ""
        ),
        "S": raw_rider.get("s"),
        "H": raw_rider.get("h"),
        "B": raw_rider.get("b"),
        "勝率": raw_rider.get("winRate"),
        "2連対率": raw_rider.get(
            "secondRate"
        ),
        "3連対率": raw_rider.get(
            "thirdRate"
        ),
        "コメント": str(
            raw_rider.get("comment") or ""
        ),
    }


def _rider_probabilities(
    combinations: list[
        dict[str, Any]
    ],
    riders: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    names = {
        int(rider["車番"]): str(
            rider.get("選手名") or ""
        )
        for rider in riders
    }
    totals = {
        number: [0.0, 0.0, 0.0]
        for number in names
    }

    for row in combinations:
        numbers = [
            int(value)
            for value in str(
                row["combination"]
            ).split("-")
        ]
        probability = float(
            row["probability"]
        )

        for position, number in enumerate(
            numbers
        ):
            totals[number][position] += (
                probability
            )

    output = [
        {
            "car_number": number,
            "name": names[number],
            "first_probability": values[0],
            "second_probability": values[1],
            "third_probability": values[2],
            "top3_probability": min(
                1.0,
                sum(values),
            ),
        }
        for number, values in totals.items()
    ]
    output.sort(
        key=lambda item: (
            -item["first_probability"],
            -item["top3_probability"],
            item["car_number"],
        )
    )
    return output


def predict_race(
    payload_json: str,
    model_path: str,
    database_path: str,
) -> str:
    from independent_learning_features import (
        FORBIDDEN_FEATURE_WORDS,
        build_independent_current_dataframe,
    )
    from lineup_from_comments import (
        infer_lineup_from_comments,
        select_authoritative_lineup,
    )
    from portable_independent_model import (
        predict_positive_probabilities,
    )
    from race_metadata import (
        parse_race_conditions,
    )

    payload = json.loads(payload_json)
    target = _target_details(
        payload.get("pageUrl", "")
    )
    raw_riders = list(
        payload.get("riders") or []
    )

    if len(raw_riders) < 3:
        raise RuntimeError(
            "予測に必要な選手データが"
            "3人分以上ありません。"
        )

    riders = [
        _rider_payload(raw_rider)
        for raw_rider in raw_riders
    ]
    rider_numbers = sorted(
        int(rider["車番"])
        for rider in riders
    )
    dom_groups = group_lineup_geometry(
        list(payload.get("lineupItems") or []),
        rider_numbers,
    )
    comment_groups, comment_logs = (
        infer_lineup_from_comments(riders)
    )
    (
        lineup_groups,
        lineup_metadata,
        selection_logs,
    ) = select_authoritative_lineup(
        dom_groups,
        comment_groups,
        rider_numbers,
    )

    if not lineup_groups:
        raise RuntimeError(
            "並びを確定できないため"
            "予測を実行しません。"
        )

    race_conditions = parse_race_conditions(
        page_title=payload.get(
            "pageTitle",
            "",
        ),
        body_text=payload.get(
            "bodyText",
            "",
        ),
        racecard_url=payload.get(
            "pageUrl",
            "",
        ),
    )
    race_conditions.update(
        lineup_metadata
    )
    race_conditions["開催日目"] = (
        target["day_number"]
    )
    dataframe = (
        build_independent_current_dataframe(
            riders=riders,
            lineup_groups=lineup_groups,
            race_id=target["race_id"],
            race_date=target["race_date"],
            venue=target["venue"],
            race_number=target[
                "race_number"
            ],
            race_conditions=race_conditions,
            database_path=Path(
                database_path
            ),
        )
    )

    if dataframe.empty:
        raise RuntimeError(
            "現在レースの特徴量を"
            "作成できませんでした。"
        )

    model = _load_model(Path(model_path))
    feature_columns = list(
        model.get("feature_columns") or []
    )
    forbidden = [
        column
        for column in feature_columns
        if any(
            word in column.lower()
            for word in FORBIDDEN_FEATURE_WORDS
        )
    ]

    if forbidden:
        raise RuntimeError(
            "端末モデルにオッズ関連特徴量が"
            "含まれています: "
            + "、".join(forbidden)
        )

    for column in feature_columns:
        if column not in dataframe.columns:
            dataframe[column] = 0.0

    matrix = dataframe[
        feature_columns
    ].astype(float).to_numpy()
    raw_probabilities = (
        predict_positive_probabilities(
            model,
            matrix,
        )
    )
    safe_probabilities = [
        max(float(value), 1e-15)
        for value in raw_probabilities
    ]
    total = float(sum(safe_probabilities))

    if not math.isfinite(total) or total <= 0:
        raise RuntimeError(
            "AI確率を正規化できません。"
        )

    probabilities = [
        value / total
        for value in safe_probabilities
    ]
    combinations = [
        {
            "combination": str(
                dataframe.iloc[index][
                    "combination"
                ]
            ),
            "probability": probability,
        }
        for index, probability in enumerate(
            probabilities
        )
    ]
    combinations.sort(
        key=lambda item: (
            -item["probability"],
            item["combination"],
        )
    )

    for rank, item in enumerate(
        combinations,
        start=1,
    ):
        item["rank"] = rank

    rider_feature_rows = (
        dataframe.sort_values(
            ["first_car", "combination"]
        )
        .drop_duplicates(
            subset=["first_car"]
        )
    )
    first_feature_row = dataframe.iloc[0]
    result = {
        "ok": True,
        "target": target,
        "lineup_groups": lineup_groups,
        "lineup_source": (
            lineup_metadata.get(
                "並び取得方式",
                "",
            )
        ),
        "lineup_confidence": float(
            lineup_metadata.get(
                "並び信頼度",
                0.0,
            )
        ),
        "lineup_logs": (
            comment_logs + selection_logs
        ),
        "combinations": combinations,
        "riders": _rider_probabilities(
            combinations,
            riders,
        ),
        "model": model.get(
            "metadata",
            {},
        ),
        "feature_coverage": {
            "rider_count": int(
                len(rider_feature_rows)
            ),
            "profile_rider_count": int(
                rider_feature_rows[
                    "first_profile_known"
                ].sum()
            ),
            "recent_history_rider_count": int(
                rider_feature_rows[
                    "first_has_prior_race"
                ].sum()
            ),
            "venue_characteristics_known": bool(
                first_feature_row[
                    "venue_characteristics_known"
                ]
            ),
            "scheduled_start_known": bool(
                first_feature_row[
                    "scheduled_start_known"
                ]
            ),
            "weather_known": bool(
                first_feature_row[
                    "weather_known"
                ]
            ),
            "feature_count": len(
                feature_columns
            ),
        },
    }

    return json.dumps(
        result,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
