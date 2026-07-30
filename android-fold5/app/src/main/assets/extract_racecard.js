(() => {
    const clean = value => String(value || "").trim();
    const normalize = value => clean(value)
        .replace(/[\n\r\s　]/g, "")
        .replace(/２/g, "2")
        .replace(/３/g, "3")
        .replace(/二/g, "2")
        .replace(/三/g, "3");
    const parseNumber = value => {
        const match = clean(value)
            .replace(/,/g, "")
            .match(/-?\d+(?:\.\d+)?/);
        return match ? Number(match[0]) : null;
    };
    const visible = element => {
        if (!element) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== "none"
            && style.visibility !== "hidden"
            && rect.width > 0
            && rect.height > 0;
    };
    const headerIndex = (headers, names) => {
        const normalized = headers.map(normalize);

        for (const name of names) {
            const target = normalize(name);
            const exact = normalized.indexOf(target);
            if (exact >= 0) return exact;

            const partial = normalized.findIndex(
                value => value.includes(target)
            );
            if (partial >= 0) return partial;
        }

        return -1;
    };
    const cell = (cells, index) => (
        index >= 0 && index < cells.length
            ? clean(cells[index])
            : ""
    );

    try {
        const tableCandidates = [
            ...document.querySelectorAll("table")
        ].map((table, tableIndex) => {
            const rows = [
                ...table.querySelectorAll("tr")
            ];
            let headers = [];

            for (const row of rows) {
                const values = [
                    ...row.querySelectorAll("th")
                ].map(item => clean(item.innerText));

                if (values.length > headers.length) {
                    headers = values;
                }
            }

            const normalized = headers.map(normalize);
            const score = [
                "車",
                "選手名",
                "競走得点",
                "コメント"
            ].filter(
                expected => normalized.some(
                    actual => actual.includes(
                        normalize(expected)
                    )
                )
            ).length;

            return {
                table,
                tableIndex,
                rows,
                headers,
                score
            };
        }).sort(
            (left, right) => (
                right.score - left.score
                || right.rows.length - left.rows.length
            )
        );
        const selected = tableCandidates[0];

        if (!selected || selected.score < 3) {
            return JSON.stringify({
                ok: false,
                error: "選手表を検出できませんでした。",
                pageTitle: document.title,
                pageUrl: location.href,
                tableCount: tableCandidates.length
            });
        }

        const headers = selected.headers;
        const positions = {
            frame: headerIndex(headers, ["枠"]),
            car: headerIndex(headers, ["車"]),
            name: headerIndex(headers, ["選手名"]),
            ai: headerIndex(headers, ["AI"]),
            score: headerIndex(headers, ["競走得点"]),
            s: headerIndex(headers, ["S"]),
            h: headerIndex(headers, ["H"]),
            b: headerIndex(headers, ["B"]),
            style: headerIndex(headers, ["脚"]),
            winRate: headerIndex(headers, ["勝率"]),
            secondRate: headerIndex(
                headers,
                ["2連対率", "２連対率"]
            ),
            thirdRate: headerIndex(
                headers,
                ["3連対率", "３連対率"]
            ),
            comment: headerIndex(headers, ["コメント"])
        };
        const riders = [];

        for (const [rowIndex, row] of selected.rows.entries()) {
            let cells = [
                ...row.querySelectorAll("td")
            ].map(item => clean(item.innerText));

            if (!cells.length) continue;

            if (
                positions.frame >= 0
                && cells.length === headers.length - 1
            ) {
                cells = [
                    ...cells.slice(0, positions.frame),
                    "",
                    ...cells.slice(positions.frame)
                ];
            }

            const carNumber = parseNumber(
                cell(cells, positions.car)
            );

            if (
                carNumber === null
                || carNumber < 1
                || carNumber > 9
            ) {
                continue;
            }

            const profileText = cell(
                cells,
                positions.name
            );
            const profileLines = profileText
                .split(/\n+/)
                .map(clean)
                .filter(Boolean);
            riders.push({
                rowIndex,
                frame: cell(cells, positions.frame),
                carNumber,
                name: profileLines[0] || profileText,
                profile: profileLines.slice(1).join(" "),
                aiMark: cell(cells, positions.ai),
                score: parseNumber(
                    cell(cells, positions.score)
                ),
                s: parseNumber(cell(cells, positions.s)),
                h: parseNumber(cell(cells, positions.h)),
                b: parseNumber(cell(cells, positions.b)),
                style: cell(cells, positions.style),
                winRate: parseNumber(
                    cell(cells, positions.winRate)
                ),
                secondRate: parseNumber(
                    cell(cells, positions.secondRate)
                ),
                thirdRate: parseNumber(
                    cell(cells, positions.thirdRate)
                ),
                comment: cell(cells, positions.comment)
            });
        }

        const lineupLabels = [
            ...document.querySelectorAll("body *")
        ].filter(element => {
            const text = clean(
                element.innerText || element.textContent
            );
            const childHasSame = [
                ...element.children
            ].some(child => clean(
                child.innerText || child.textContent
            ) === "並び予想");
            return text === "並び予想"
                && !childHasSame
                && visible(element);
        });
        let lineupText = "";
        let lineupItems = [];

        if (lineupLabels.length) {
            const label = lineupLabels[0];
            let section = label;

            for (let depth = 0; depth < 10; depth += 1) {
                if (!section) break;
                const text = clean(
                    section.innerText || section.textContent
                );
                const lines = text
                    .split(/\n/)
                    .map(clean)
                    .filter(Boolean);

                if (
                    text.includes("並び予想")
                    && lines.length >= 2
                    && lines.length <= 80
                ) {
                    break;
                }

                section = section.parentElement;
            }

            if (section) {
                lineupText = clean(
                    section.innerText
                    || section.textContent
                );
                const validNumber = value => (
                    /^[1-9]$/.test(clean(value))
                );
                const labelRect =
                    label.getBoundingClientRect();
                const elements = [
                    ...section.querySelectorAll("*")
                ];
                const leaves = elements.filter(candidate => {
                    const text = clean(
                        candidate.innerText
                        || candidate.textContent
                    );
                    const childRepeats = [
                        ...candidate.children
                    ].some(child => validNumber(
                        child.innerText
                        || child.textContent
                    ));
                    const rect =
                        candidate.getBoundingClientRect();

                    return validNumber(text)
                        && !childRepeats
                        && visible(candidate)
                        && rect.top
                            >= labelRect.bottom - 6
                        && rect.top
                            <= labelRect.bottom + 320;
                });
                const totalNumbers = new Set(
                    leaves.map(leaf => clean(
                        leaf.innerText
                        || leaf.textContent
                    ))
                ).size;

                lineupItems = leaves.map(leaf => {
                    let current = leaf.parentElement;
                    let selectedGroup = leaf;

                    while (
                        current
                        && current !== section
                    ) {
                        const numbers = [
                            ...current.querySelectorAll("*")
                        ].filter(candidate => {
                            const text = clean(
                                candidate.innerText
                                || candidate.textContent
                            );
                            const childRepeats = [
                                ...candidate.children
                            ].some(child => validNumber(
                                child.innerText
                                || child.textContent
                            ));
                            return validNumber(text)
                                && !childRepeats;
                        });
                        const uniqueCount = new Set(
                            numbers.map(item => clean(
                                item.innerText
                                || item.textContent
                            ))
                        ).size;

                        if (
                            uniqueCount >= 1
                            && uniqueCount < totalNumbers
                        ) {
                            selectedGroup = current;
                        }

                        current = current.parentElement;
                    }

                    const rect =
                        leaf.getBoundingClientRect();
                    return {
                        number: Number(clean(
                            leaf.innerText
                            || leaf.textContent
                        )),
                        x: rect.left,
                        y: rect.top,
                        width: rect.width,
                        height: rect.height,
                        groupKey: String(
                            elements.indexOf(selectedGroup)
                        )
                    };
                });
            }
        }

        const uniqueRiders = [];
        const used = new Set();

        for (const rider of riders) {
            if (!used.has(rider.carNumber)) {
                used.add(rider.carNumber);
                uniqueRiders.push(rider);
            }
        }

        return JSON.stringify({
            ok: true,
            pageTitle: document.title,
            pageUrl: location.href,
            tableCount: tableCandidates.length,
            selectedTableIndex: selected.tableIndex,
            headers,
            positions,
            riders: uniqueRiders,
            lineupText,
            lineupItems
        });
    } catch (error) {
        return JSON.stringify({
            ok: false,
            error: String(
                error && error.stack
                    ? error.stack
                    : error
            ),
            pageTitle: document.title,
            pageUrl: location.href
        });
    }
})()
