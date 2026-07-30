from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


def normalize_text(value: str) -> str:
    return (
        str(value)
        .replace("　", " ")
        .replace("－", "-")
        .replace("―", "-")
        .replace("ー", "-")
        .replace("→", "-")
        .replace("⇒", "-")
        .replace("=", "-")
    )


def parse_line_groups(
    text: str,
    rider_numbers: list[int],
) -> list[list[int]]:
    """
    並び予想の文字列からラインを抽出する。

    対応例:
    6-3 2-5 7-4-1
    63 25 741
    6 3 / 2 5 / 7 4 1
    """
    normalized = normalize_text(text)
    valid_riders = set(rider_numbers)

    candidates: list[list[list[int]]] = []

    # ハイフン等でつながった表記
    hyphen_groups = []

    for match in re.finditer(
        r"(?<!\d)([1-9](?:\s*-\s*[1-9])+)(?!\d)",
        normalized,
    ):
        numbers = [
            int(value)
            for value in re.findall(r"[1-9]", match.group(1))
        ]

        if (
            len(numbers) >= 2
            and len(numbers) == len(set(numbers))
            and set(numbers).issubset(valid_riders)
        ):
            hyphen_groups.append(numbers)

    if hyphen_groups:
        candidates.append(hyphen_groups)

    # 「741」のような連続車番表記
    compact_groups = []

    for token in re.findall(r"(?<!\d)([1-9]{2,9})(?!\d)", normalized):
        numbers = [int(value) for value in token]

        if (
            len(numbers) >= 2
            and len(numbers) == len(set(numbers))
            and set(numbers).issubset(valid_riders)
        ):
            compact_groups.append(numbers)

    if compact_groups:
        candidates.append(compact_groups)

    # 空白区切りの数字列
    spaced_groups = []

    for line in normalized.splitlines():
        numbers = [
            int(value)
            for value in re.findall(r"(?<!\d)([1-9])(?!\d)", line)
        ]

        if (
            len(numbers) >= 2
            and len(numbers) == len(set(numbers))
            and set(numbers).issubset(valid_riders)
        ):
            spaced_groups.append(numbers)

    if spaced_groups:
        candidates.append(spaced_groups)

    best_groups: list[list[int]] = []
    best_score = -1

    for groups in candidates:
        used: set[int] = set()
        cleaned_groups: list[list[int]] = []

        for group in groups:
            cleaned = []

            for rider in group:
                if rider in used:
                    continue

                cleaned.append(rider)
                used.add(rider)

            if len(cleaned) >= 2:
                cleaned_groups.append(cleaned)

        coverage = len(used)
        duplicate_penalty = sum(len(group) for group in groups) - coverage
        score = coverage * 10 - duplicate_penalty

        if score > best_score:
            best_score = score
            best_groups = cleaned_groups

    # 使われていない車番は単騎として追加
    used = {
        rider
        for group in best_groups
        for rider in group
    }

    for rider in rider_numbers:
        if rider not in used:
            best_groups.append([rider])

    return best_groups


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
                float(
                    item.get(
                        "width",
                        1.0,
                    )
                ),
            ),
        }
        for item in items
        if int(
            item.get("number", 0)
            or 0
        )
        in valid
    ]

    if not candidates:
        return []

    semantic: dict[str, list[
        dict[str, Any]
    ]] = {}

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
            float(
                item.get(
                    "height",
                    1.0,
                )
            )
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
        row.sort(
            key=lambda item: item["x"]
        )

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


def fetch_lineup(
    racecard_url: str,
    rider_numbers: list[int],
) -> tuple[list[list[int]], str, list[str]]:
    logs = [
        "並び予想取得方式: Google Chrome DOM解析",
        f"出走表URL: {racecard_url}",
    ]

    with sync_playwright() as playwright:
        launch_options = {
            "headless": True,
            "args": [
                "--disable-dev-shm-usage",
                "--disable-background-networking",
                "--disable-extensions",
                "--disable-gpu",
            ],
        }

        try:
            browser = playwright.chromium.launch(
                channel="chrome",
                **launch_options,
            )
            logs.append("ブラウザ: システムのGoogle Chrome")

        except Exception:
            browser = playwright.chromium.launch(
                **launch_options,
            )
            logs.append(
                "ブラウザ: Playwright Chromium"
            )

        context = browser.new_context(
            viewport={
                "width": 1440,
                "height": 1200,
            },
            user_agent=(
                "Mozilla/5.0 "
                "(Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 "
                "Chrome/126 Safari/537.36"
            ),
        )

        page = context.new_page()

        page.goto(
            racecard_url,
            wait_until="domcontentloaded",
            timeout=60_000,
        )

        page.wait_for_timeout(2000)

        source_text = ""
        geometry_items: list[
            dict[str, Any]
        ] = []

        lineup_labels = page.get_by_text(
            re.compile(r"並び予想")
        )

        if lineup_labels.count() > 0:
            source_text = lineup_labels.first.evaluate(
                """
                element => {
                    let current = element;

                    for (let depth = 0; depth < 10; depth += 1) {
                        if (!current) break;

                        const text = (
                            current.innerText ||
                            current.textContent ||
                            ""
                        ).trim();

                        const lineCount = text
                            .split(String.fromCharCode(10))
                            .filter(line => line.trim().length > 0)
                            .length;

                        if (
                            text.includes("並び予想") &&
                            lineCount >= 2 &&
                            lineCount <= 80
                        ) {
                            return text;
                        }

                        current = current.parentElement;
                    }

                    return document.body.innerText;
                }
                """
            )
            geometry_items = (
                lineup_labels.first.evaluate(
                    """
                    element => {
                        let section = element;

                        for (
                            let depth = 0;
                            depth < 10;
                            depth += 1
                        ) {
                            if (!section) break;
                            const text = (
                                section.innerText ||
                                section.textContent ||
                                ""
                            ).trim();
                            const lines = text
                                .split(String.fromCharCode(10))
                                .filter(
                                    line =>
                                        line.trim().length > 0
                                );

                            if (
                                text.includes("並び予想") &&
                                lines.length >= 2 &&
                                lines.length <= 80
                            ) {
                                break;
                            }

                            section =
                                section.parentElement;
                        }

                        if (!section) return [];

                        const validText = value =>
                            /^[1-9]$/.test(
                                (value || "").trim()
                            );
                        const labelRect =
                            element.getBoundingClientRect();
                        const elements = [
                            ...section.querySelectorAll("*")
                        ];
                        const leaves = elements.filter(
                            candidate => {
                                const style =
                                    getComputedStyle(candidate);
                                const rect =
                                    candidate.getBoundingClientRect();
                                const text = (
                                    candidate.innerText ||
                                    candidate.textContent ||
                                    ""
                                ).trim();
                                const childRepeats = [
                                    ...candidate.children
                                ].some(
                                    child => validText(
                                        child.innerText ||
                                        child.textContent
                                    )
                                );

                                return (
                                    validText(text) &&
                                    !childRepeats &&
                                    style.display !== "none" &&
                                    style.visibility !== "hidden" &&
                                    rect.width > 0 &&
                                    rect.height > 0 &&
                                    rect.top >=
                                        labelRect.bottom - 6 &&
                                    rect.top <=
                                        labelRect.bottom + 320
                                );
                            }
                        );
                        const totalNumbers = new Set(
                            leaves.map(
                                leaf => (
                                    leaf.innerText ||
                                    leaf.textContent ||
                                    ""
                                ).trim()
                            )
                        ).size;

                        return leaves.map(leaf => {
                            let current =
                                leaf.parentElement;
                            let selected = leaf;

                            while (
                                current &&
                                current !== section
                            ) {
                                const numbers = [
                                    ...current
                                        .querySelectorAll("*")
                                ].filter(candidate => {
                                    const text = (
                                        candidate.innerText ||
                                        candidate.textContent ||
                                        ""
                                    ).trim();
                                    const childRepeats = [
                                        ...candidate.children
                                    ].some(
                                        child => validText(
                                            child.innerText ||
                                            child.textContent
                                        )
                                    );

                                    return (
                                        validText(text) &&
                                        !childRepeats
                                    );
                                });
                                const unique =
                                    new Set(
                                        numbers.map(
                                            candidate => (
                                                candidate.innerText ||
                                                candidate.textContent ||
                                                ""
                                            ).trim()
                                        )
                                    ).size;

                                if (
                                    unique >= 1 &&
                                    unique < totalNumbers
                                ) {
                                    selected = current;
                                }

                                current =
                                    current.parentElement;
                            }

                            const rect =
                                leaf.getBoundingClientRect();

                            return {
                                number: Number(
                                    (
                                        leaf.innerText ||
                                        leaf.textContent ||
                                        ""
                                    ).trim()
                                ),
                                x: rect.left,
                                y: rect.top,
                                width: rect.width,
                                height: rect.height,
                                groupKey: String(
                                    elements.indexOf(
                                        selected
                                    )
                                )
                            };
                        });
                    }
                    """
                )
            )

        if not source_text:
            body_text = page.locator("body").inner_text()
            marker = body_text.find("並び予想")

            if marker >= 0:
                source_text = body_text[
                    marker:marker + 1500
                ]

        context.close()
        browser.close()

    logs.append(
        "並び予想抽出テキスト: "
        + " / ".join(
            line.strip()
            for line in source_text.splitlines()
            if line.strip()
        )[:1000]
    )

    geometry_groups = (
        group_lineup_geometry(
            geometry_items,
            rider_numbers,
        )
    )
    text_groups = parse_line_groups(
        source_text,
        rider_numbers,
    )
    geometry_informative = (
        len(geometry_groups) >= 2
        and any(
            len(group) >= 2
            for group in geometry_groups
        )
    )
    groups = (
        geometry_groups
        if geometry_informative
        else text_groups
    )

    logs.append(
        "DOM並び解析方式: "
        + (
            "要素グループ・座標"
            if geometry_informative
            else "抽出テキスト"
        )
    )

    logs.append(
        "解析した並び: "
        + " / ".join(
            "-".join(str(rider) for rider in group)
            for group in groups
        )
    )

    return groups, source_text, logs


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--racecard-url",
        required=True,
    )

    parser.add_argument(
        "--riders",
        required=True,
        help="1,2,3,4,5,6,7形式",
    )

    parser.add_argument(
        "--output",
        required=True,
    )

    arguments = parser.parse_args()

    rider_numbers = [
        int(value)
        for value in arguments.riders.split(",")
        if value.strip().isdigit()
    ]

    output_path = Path(arguments.output)

    try:
        groups, source_text, logs = fetch_lineup(
            arguments.racecard_url,
            rider_numbers,
        )

        payload = {
            "success": True,
            "groups": groups,
            "source_text": source_text,
            "logs": logs,
        }

    except Exception as exc:
        payload = {
            "success": False,
            "groups": [],
            "source_text": "",
            "logs": [
                "並び予想Workerでエラーが発生しました。",
                f"{type(exc).__name__}: {exc}",
            ],
        }

    output_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
