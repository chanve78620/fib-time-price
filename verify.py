#!/usr/bin/env python3
"""Verify Newton-style Fib TIME math against Oct 1, 2026 tweet worksheet values."""

import os
import sys
from datetime import date, timedelta
from math import floor

RATIOS = [
    0.272, 0.382, 0.414, 0.500, 0.618, 0.707, 0.786, 0.841,
    1.000, 1.272, 1.382, 1.414, 1.500, 1.618, 1.707, 1.786, 1.841,
    2.000, 2.272, 2.382, 2.414, 2.500, 2.618, 2.707, 2.786, 2.841,
    3.000, 3.272,
]

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def format_date(d: date) -> str:
    return f"{d.day}-{MONTHS[d.month - 1]}-{d.year}"


def compute_row(ratio: float, date1: date, date2: date, base_days: int):
    raw = ratio * base_days
    days_disp = round(raw)
    floor_days = floor(raw)
    return {
        "ratio": ratio,
        "days": days_disp,
        "weeks": days_disp / 7,
        "months": days_disp / 29.5,
        "years": days_disp / 365,
        "add1": date1 + timedelta(days=floor_days),
        "add2": date2 + timedelta(days=floor_days),
        "add1_str": format_date(date1 + timedelta(days=floor_days)),
        "add2_str": format_date(date2 + timedelta(days=floor_days)),
    }


# Expected rows from tweet / Excel screenshot
EXPECTED = [
    # ratio, days, add1, add2
    (0.382, 52, "20-May-2026", "3-Oct-2026"),
    (0.618, 84, "22-Jun-2026", "5-Nov-2026"),
    (1.000, 136, "13-Aug-2026", "27-Dec-2026"),
    (1.500, 204, "20-Oct-2026", "5-Mar-2027"),
    (1.618, 220, "5-Nov-2026", "21-Mar-2027"),
]


def main():
    date1 = date(2026, 3, 30)
    date2 = date(2026, 8, 13)
    base_days = (date2 - date1).days

    print(f"Date1={date1}  Date2={date2}  baseDays={base_days}")
    assert base_days == 136, f"baseDays expected 136, got {base_days}"

    failures = []
    for ratio, exp_days, exp_add1, exp_add2 in EXPECTED:
        row = compute_row(ratio, date1, date2, base_days)
        ok = (
            row["days"] == exp_days
            and row["add1_str"] == exp_add1
            and row["add2_str"] == exp_add2
        )
        status = "PASS" if ok else "FAIL"
        print(
            f"  {status}  r={ratio:.3f}  Days={row['days']} (exp {exp_days})  "
            f"Add1={row['add1_str']} (exp {exp_add1})  "
            f"Add2={row['add2_str']} (exp {exp_add2})"
        )
        if not ok:
            failures.append(ratio)
            raw = ratio * base_days
            print(f"         debug: raw={raw} floor={floor(raw)} round={round(raw)}")

    # Sanity: floor vs round split for 0.382
    raw_382 = 0.382 * 136
    assert abs(raw_382 - 51.952) < 1e-9, raw_382
    assert round(raw_382) == 52
    assert floor(raw_382) == 51

    if failures:
        print("FAIL")
        raise SystemExit(1)

    print("PASS")
    return 0


if __name__ == "__main__" and "--levels" not in sys.argv:
    main()


# ---------------------------------------------------------------------------
# Optional UI check: drawn price levels must not have been traded through.
#   python verify.py --levels http://127.0.0.1:8765 [TICKER ...]
# Needs the server running and `pip install playwright` (uses system Chrome
# if PLAYWRIGHT_CHROME is set, else playwright's bundled Chromium).
# Rule: a drawn level is invalid if any bar after its anchor pivot (the bar
# where the level becomes defined, tentative or not) has low <= level <= high.
def check_levels(base: str, tickers: list[str], shots_dir: str | None = None) -> int:
    import json
    import os
    import urllib.request
    from playwright.sync_api import sync_playwright

    failures = 0
    exe = os.environ.get("PLAYWRIGHT_CHROME")
    with sync_playwright() as p:
        kw = {"args": ["--no-sandbox"]}
        if exe:
            kw["executable_path"] = exe
        b = p.chromium.launch(**kw)
        for t in tickers:
            pg = b.new_page(viewport={"width": 1280, "height": 820})
            pg.add_init_script("localStorage.clear()")
            pg.goto(f"{base}/?t={t}&tf=1d")
            pg.wait_for_function("document.getElementById('status').textContent.includes(' bars ·')", timeout=60000)
            info = pg.evaluate("""() => ({
                levels: visibleLevels().map(v => ({price: v.price, txt: lvlText(v), anchor: v.anchorDate, tent: v.anchorTent})),
                zones: ZN.map(z => ({label: z.label, members: z.levels.map(v => v.price)})),
                pivots: P.map(p => ({date: p.date, tent: !!p.tent})),
            })""".replace("lvlText", "lvText"))
            if shots_dir:
                pg.screenshot(path=os.path.join(shots_dir, f"{t.lower().replace('=f', '').replace('^', '')}_nohit.png"))
            pg.close()
            with urllib.request.urlopen(f"{base}/api/history?ticker={t}&tf=1d") as r:
                h = json.load(r)
            dates, hi, lo = h["dates"], h["highs"], h["lows"]
            idx = {d: i for i, d in enumerate(dates)}
            conf = [p["date"] for p in info["pivots"] if not p["tent"]]
            bad = []
            for lv in info["levels"]:
                a = idx[lv["anchor"]]
                start = a + 1
                for j in range(start, len(dates)):
                    if hi[j] is not None and lo[j] <= lv["price"] <= hi[j]:
                        bad.append(f"{lv['txt']} (anchor {lv['anchor']}) touched {dates[j]} [{lo[j]}-{hi[j]}]")
                        break
            print(f"{t}: {len(info['levels'])} drawn levels, {len(info['zones'])} zones -> {'OK' if not bad else 'FAIL'}")
            for x in bad:
                print("   ", x)
            failures += len(bad)
        b.close()
    return failures


if __name__ == "__main__" and "--levels" in sys.argv:
    k = sys.argv.index("--levels")
    base = sys.argv[k + 1] if len(sys.argv) > k + 1 else "http://127.0.0.1:8765"
    tick = [a for a in sys.argv[k + 2:] if not a.startswith("--")] or ["ES=F", "SPX"]
    shots = os.environ.get("SHOTS_DIR")
    sys.exit(1 if check_levels(base, tick, shots) else 0)
