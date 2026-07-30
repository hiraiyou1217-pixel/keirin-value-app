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


def resolve_referenced_rider(
    referenced_name: str,
    rider_by_number: dict[
        int,
        dict[str, Any],
    ],
    surname_to_numbers: dict[
        str,
        list[int],
    ],
) -> int | None:
    exact_candidates = surname_to_numbers.get(
        referenced_name,
        [],
    )

    if len(exact_candidates) == 1:
        return exact_candidates[0]

    if len(exact_candidates) > 1:
        return None

    # WINTICKETのコメントは「中君」のように
    # 1文字姓を使う一方、出走表の姓名に空白がない
    # 場合がある。先頭一致が1人だけなら照合する。
    candidates = []

    for number, rider in rider_by_number.items():
        rider_name = "".join(
            str(
                rider.get(
                    "選手名",
                    "",
                )
            ).split()
        )

        if rider_name.startswith(
            referenced_name
        ):
            candidates.append(number)

    if len(candidates) == 1:
        return candidates[0]

    return None


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

    surname_to_numbers: dict[
        str,
        list[int],
    ] = {}

    for number, rider in rider_by_number.items():
        surname = surname_from_name(
            str(rider.get("選手名", ""))
        )

        if surname:
            surname_to_numbers.setdefault(
                surname,
                [],
            ).append(number)

    # follower -> leader
    follows: dict[int, int] = {}

    for number, rider in rider_by_number.items():
        comment = str(
            rider.get("コメント", "")
        )

        surname = referenced_surname(comment)

        if not surname:
            continue

        leader = resolve_referenced_rider(
            surname,
            rider_by_number,
            surname_to_numbers,
        )

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


def merge_dom_order_with_comment_groups(
    dom_groups: list[list[int]],
    comment_groups: list[list[int]],
    rider_numbers: list[int],
) -> tuple[list[list[int]], list[str]]:
    """
    DOMの画面表示順を、コメントから判明した連携単位で分割する。

    例:
    DOM順   4-1-6-2-7-3-5
    コメント 4-1 / 2-7 / 3-5
    結果     4-1-6 / 2-7 / 3-5
    """
    logs = ["並び統合方式: DOM順＋コメント連携"]

    flat_order: list[int] = []

    if (
        len(dom_groups) == 1
        and len(dom_groups[0]) >= 2
    ):
        flat_order = [
            int(value)
            for value in dom_groups[0]
        ]
    else:
        flat_order = [
            int(value)
            for group in dom_groups
            for value in group
        ]

    if (
        len(flat_order) != len(rider_numbers)
        or set(flat_order) != set(rider_numbers)
    ):
        logs.append(
            "DOM順が全車番を含まないため、コメント解析を採用"
        )
        return comment_groups, logs

    linked_pairs: set[tuple[int, int]] = set()

    for group in comment_groups:
        if len(group) < 2:
            continue

        for index in range(len(group) - 1):
            linked_pairs.add(
                (
                    int(group[index]),
                    int(group[index + 1]),
                )
            )

    groups: list[list[int]] = []
    current_group: list[int] = []

    for index, rider in enumerate(flat_order):
        current_group.append(rider)

        if index == len(flat_order) - 1:
            groups.append(current_group)
            break

        current = rider
        following = flat_order[index + 1]

        directly_linked = (
            (current, following) in linked_pairs
        )

        #
        # 次の車からコメントで別ラインが始まる場合は区切る。
        # ただし、現在の並びが2車以上で、次の次に既知連携が
        # ある場合は、現在車を3番手として残して区切る。
        #
        next_starts_known_line = any(
            first == following
            for first, _ in linked_pairs
        )

        current_has_known_follower = any(
            first == current
            for first, _ in linked_pairs
        )

        if directly_linked:
            continue

        if next_starts_known_line:
            groups.append(current_group)
            current_group = []
            continue

        if current_has_known_follower:
            continue

        #
        # 次の車とその次の車が既知連携なら、
        # 次の車を新ライン先頭として区切る。
        #
        if index + 2 < len(flat_order):
            next_pair = (
                following,
                flat_order[index + 2],
            )

            if next_pair in linked_pairs:
                groups.append(current_group)
                current_group = []

    cleaned_groups: list[list[int]] = []
    used: set[int] = set()

    for group in groups:
        cleaned = []

        for rider in group:
            if rider in used:
                continue

            cleaned.append(rider)
            used.add(rider)

        if cleaned:
            cleaned_groups.append(cleaned)

    for rider in rider_numbers:
        if rider not in used:
            cleaned_groups.append([rider])

    logs.append(
        "統合後並び: "
        + " / ".join(
            "-".join(str(value) for value in group)
            for group in cleaned_groups
        )
    )

    return cleaned_groups, logs


def _complete_lineup(
    groups: list[list[int]],
    rider_numbers: list[int],
) -> bool:
    flattened = [
        int(number)
        for group in groups
        for number in group
    ]

    return (
        len(flattened)
        == len(set(flattened))
        and set(flattened)
        == set(rider_numbers)
    )


def select_authoritative_lineup(
    dom_groups: list[list[int]],
    comment_groups: list[list[int]],
    rider_numbers: list[int],
) -> tuple[
    list[list[int]],
    dict[str, Any],
    list[str],
]:
    logs = [
        "並び採用判定: DOM構造優先＋"
        "選手コメント整合性確認"
    ]
    dom_complete = _complete_lineup(
        dom_groups,
        rider_numbers,
    )
    comment_complete = _complete_lineup(
        comment_groups,
        rider_numbers,
    )
    dom_informative = (
        dom_complete
        and len(dom_groups) >= 2
        and any(
            len(group) >= 2
            for group in dom_groups
        )
    )
    comment_pairs = {
        (
            int(group[index]),
            int(group[index + 1]),
        )
        for group in comment_groups
        if len(group) >= 2
        for index in range(
            len(group) - 1
        )
    }
    dom_pairs = {
        (
            int(group[index]),
            int(group[index + 1]),
        )
        for group in dom_groups
        if len(group) >= 2
        for index in range(
            len(group) - 1
        )
    }
    comment_consistent = (
        not comment_pairs
        or comment_pairs.issubset(
            dom_pairs
        )
    )

    if (
        dom_informative
        and comment_consistent
    ):
        groups = dom_groups
        metadata = {
            "並び取得方式": (
                "DOM構造＋コメント確認"
            ),
            "並び信頼度": 0.95,
        }
        logs.append(
            "採用理由: DOMでライン境界を検出し、"
            "コメント連携とも整合"
        )
    elif (
        comment_complete
        and comment_pairs
    ):
        groups = comment_groups
        metadata = {
            "並び取得方式": (
                "選手コメント推定"
            ),
            "並び信頼度": 0.60,
        }
        logs.append(
            "採用理由: DOM境界が不明または"
            "コメントと不整合のためコメント推定"
        )
    elif dom_complete:
        groups = dom_groups
        metadata = {
            "並び取得方式": (
                "DOM順・境界低信頼"
            ),
            "並び信頼度": 0.35,
        }
        logs.append(
            "採用理由: コメント連携がなく、"
            "完全なDOM順を低信頼で採用"
        )
    else:
        groups = [
            [int(number)]
            for number in rider_numbers
        ]
        metadata = {
            "並び取得方式": "未判定",
            "並び信頼度": 0.0,
        }
        logs.append(
            "採用理由: 完全な並びを取得できず"
            "全車単騎として保持"
        )

    logs.append(
        "最終採用並び: "
        + " / ".join(
            "-".join(
                str(number)
                for number in group
            )
            for group in groups
        )
    )
    logs.append(
        "並びメタデータ: "
        f"方式={metadata['並び取得方式']} "
        f"信頼度={metadata['並び信頼度']}"
    )

    return groups, metadata, logs
