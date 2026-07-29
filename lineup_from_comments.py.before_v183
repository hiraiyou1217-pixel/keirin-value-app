from __future__ import annotations

import re
from typing import Any


PREFECTURES = (
    "北海道", "青森", "岩手", "宮城", "秋田", "山形", "福島",
    "茨城", "栃木", "群馬", "埼玉", "千葉", "東京", "神奈川",
    "新潟", "富山", "石川", "福井", "山梨", "長野", "岐阜",
    "静岡", "愛知", "三重", "滋賀", "京都", "大阪", "兵庫",
    "奈良", "和歌山", "鳥取", "島根", "岡山", "広島", "山口",
    "徳島", "香川", "愛媛", "高知", "福岡", "佐賀", "長崎",
    "熊本", "大分", "宮崎", "鹿児島", "沖縄",
)


def surname_from_name(name: str) -> str:
    cleaned = " ".join(str(name).split())

    if not cleaned:
        return ""

    # 「取鳥雄吾」のような空白なし姓名では、
    # コメント照合のため先頭2文字を優先する。
    if " " not in cleaned:
        return cleaned[:2]

    return cleaned.split()[0]


def referenced_surname(comment: str) -> str:
    text = str(comment).strip()

    match = re.search(
        r"([一-龥々]{1,5})君",
        text,
    )

    if match:
        return match.group(1)

    return ""


def infer_lineup_from_comments(
    riders: list[dict[str, Any]],
) -> tuple[list[list[int]], list[str]]:
    logs: list[str] = [
        "並び推定方式: 選手コメント連携解析"
    ]

    rider_by_number = {
        int(rider["車番"]): rider
        for rider in riders
        if rider.get("車番") is not None
    }

    surname_to_number: dict[str, int] = {}

    for number, rider in rider_by_number.items():
        surname = surname_from_name(
            str(rider.get("選手名", ""))
        )

        if surname:
            surname_to_number[surname] = number

    # follower -> leader
    follows: dict[int, int] = {}

    for number, rider in rider_by_number.items():
        comment = str(
            rider.get("コメント", "")
        )

        surname = referenced_surname(comment)

        if not surname:
            continue

        leader = surname_to_number.get(surname)

        if leader is None or leader == number:
            continue

        follows[number] = leader

        logs.append(
            f"連携検出: {number}番 → {leader}番 "
            f"コメント={comment}"
        )

    # leader -> direct followers
    followers: dict[int, list[int]] = {}

    for follower, leader in follows.items():
        followers.setdefault(leader, []).append(follower)

    # 先頭候補は、誰かに付かず、後ろがいる選手
    roots = sorted(
        number
        for number in rider_by_number
        if number not in follows
        and number in followers
    )

    groups: list[list[int]] = []
    used: set[int] = set()

    for root in roots:
        group = [root]
        current = root

        while current in followers:
            candidates = [
                value
                for value in followers[current]
                if value not in used
                and value not in group
            ]

            if not candidates:
                break

            # 通常は直接の追走者は1名。
            # 複数の場合は車番順で安定化する。
            next_rider = sorted(candidates)[0]
            group.append(next_rider)
            current = next_rider

        if len(group) >= 2:
            groups.append(group)
            used.update(group)

    # 既存グループに含まれていない連携を補完
    for follower, leader in follows.items():
        if follower in used and leader in used:
            continue

        group = [leader, follower]

        # followerにさらに追走者がいる場合
        current = follower

        while current in followers:
            candidates = [
                value
                for value in followers[current]
                if value not in group
            ]

            if not candidates:
                break

            next_rider = sorted(candidates)[0]
            group.append(next_rider)
            current = next_rider

        groups.append(group)
        used.update(group)

    # 残りは単騎
    for number in sorted(rider_by_number):
        if number not in used:
            groups.append([number])

    logs.append(
        "コメント推定並び: "
        + " / ".join(
            "-".join(str(value) for value in group)
            for group in groups
        )
    )

    return groups, logs
