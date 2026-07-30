(() => {
    const clean = value => String(value || "")
        .replace(/\s+/g, " ")
        .trim();
    const pattern = /^\/keirin\/([^/]+)\/racecard\/(\d+)\/(\d+)\/(\d+)\/?$/;
    const venueNames = {
        hakodate: "函館競輪",
        aomori: "青森競輪",
        iwakidaira: "いわき平競輪",
        iwakitaira: "いわき平競輪",
        yahiko: "弥彦競輪",
        maebashi: "前橋競輪",
        toride: "取手競輪",
        utsunomiya: "宇都宮競輪",
        omiya: "大宮競輪",
        seibuen: "西武園競輪",
        keiokaku: "京王閣競輪",
        tachikawa: "立川競輪",
        matsudo: "松戸競輪",
        chiba: "千葉競輪",
        kawasaki: "川崎競輪",
        hiratsuka: "平塚競輪",
        odawara: "小田原競輪",
        ito: "伊東競輪",
        shizuoka: "静岡競輪",
        nagoya: "名古屋競輪",
        gifu: "岐阜競輪",
        ogaki: "大垣競輪",
        toyohashi: "豊橋競輪",
        toyama: "富山競輪",
        matsusaka: "松阪競輪",
        yokkaichi: "四日市競輪",
        fukui: "福井競輪",
        nara: "奈良競輪",
        mukomachi: "向日町競輪",
        wakayama: "和歌山競輪",
        kishiwada: "岸和田競輪",
        tamano: "玉野競輪",
        hiroshima: "広島競輪",
        hofu: "防府競輪",
        takamatsu: "高松競輪",
        komatsushima: "小松島競輪",
        kochi: "高知競輪",
        matsuyama: "松山競輪",
        kokura: "小倉競輪",
        kurume: "久留米競輪",
        takeo: "武雄競輪",
        sasebo: "佐世保競輪",
        beppu: "別府競輪",
        kumamoto: "熊本競輪"
    };

    try {
        const byUrl = new Map();

        for (const anchor of document.querySelectorAll("a[href]")) {
            const url = new URL(anchor.href, location.href);
            const match = url.pathname.match(pattern);

            if (!match) continue;

            const slug = match[1].toLowerCase();
            const raceNumber = Number(match[4]);

            if (
                !venueNames[slug]
                || !Number.isInteger(raceNumber)
                || raceNumber < 1
                || raceNumber > 12
            ) {
                continue;
            }

            const canonical = (
                url.origin
                + url.pathname.replace(/\/$/, "")
            );
            byUrl.set(canonical, {
                url: canonical,
                venue: venueNames[slug],
                raceNumber,
                dayNumber: Number(match[3]),
                linkText: clean(anchor.innerText)
            });
        }

        const races = [...byUrl.values()].sort(
            (left, right) => (
                left.venue.localeCompare(
                    right.venue,
                    "ja"
                )
                || left.raceNumber
                    - right.raceNumber
            )
        );

        return JSON.stringify({
            ok: races.length > 0,
            error: races.length > 0
                ? ""
                : "開催レースを検出できませんでした。",
            pageTitle: document.title,
            pageUrl: location.href,
            races
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
