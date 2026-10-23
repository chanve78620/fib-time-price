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


def check_propulsion() -> bool:
    import re
    import shutil
    import subprocess
    exp = {(0.236, 0.472): (116.09, 118.18), (0.25, 0.5): (116.21, 118.43)}
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"), encoding="utf-8").read()
    m = re.search(r"^function propLevels\(.*$", src, re.M)
    if not m:
        print("  FAIL  propLevels() not found in index.html")
        return False
    ok = True
    node = shutil.which("node")
    for (r1, r2), (ea, eb) in exp.items():
        if node:
            js = m.group(0) + f"\nconst o=propLevels(109.00,117.88,113.99,'up',{r1},{r2});console.log(o.A+' '+o.B);"
            a, b = map(float, subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout.split())
            how = "JS"
        else:  # same formula in Python if node is unavailable
            R = 117.88 - 109.00
            a, b = 113.99 + r1 * R, 113.99 + r2 * R
            how = "py"
        good = round(a, 2) == ea and round(b, 2) == eb
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  TD Propulsion Up {r1}/{r2} ({how}): A={a:.2f} (exp {ea})  B={b:.2f} (exp {eb})")
    # Bloomberg GDXJ 30m (Oct 2026) calibration: trigger 110.7613 and full propulsion 117.305 are
    # reproduced exactly by A = Z + 0.25R and F = Z + 1.0R with X=103.675, Y=112.40, Z=108.58
    # (Bloomberg prints; FMP has 103.68 / 108.59). Bloomberg's 113.2125 is NOT Z + 0.5R (=112.9425).
    if node:
        js = m.group(0) + "\nconst o=propLevels(103.675,112.40,108.58,'up',0.25,0.5);console.log(o.A+' '+o.F);"
        a, f = map(float, subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout.split())
        good = round(a, 4) == 110.7613 and round(f, 4) == 117.305
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  Bloomberg GDXJ calibration (JS): A={a:.4f} (exp 110.7613)  Full={f:.4f} (exp 117.3050)")
    return ok


def check_breakout_qualifiers() -> bool:
    """Unit test of propBreakQual() (DeMark TD Line breakout qualifiers) on synthetic bars."""
    import json
    import re
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        print("  SKIP  breakout qualifiers (node not installed)")
        return True
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"), encoding="utf-8").read()
    m = re.search(r"^function propBreakQual\(.*?^}$", src, re.M | re.S)
    if not m:
        print("  FAIL  propBreakQual() not found in index.html")
        return False
    # (name, o, h, l, c, level, up, expected [Q1, Q2, Q3, Q4], expected qualified)
    cases = [
        ("up Q1 prior down close", [9, 9.6, 9.1], [9.7, 9.8, 10.2], [8.9, 8.0, 9.0], [9.5, 9.2, 10.1], 10, True, [True, False, False, False], True),
        ("up Q2 gap open + follow-through", [9, 9.6, 10.05], [9.7, 9.9, 10.3], [8.9, 9.0, 10.0], [9.5, 9.8, 10.2], 10, True, [False, True, False, True], True),
        ("up gap open, no follow-through", [9, 9.6, 10.05], [9.7, 9.9, 10.05], [8.9, 9.0, 9.9], [9.5, 9.8, 10.0], 10, True, [False, False, False, False], False),
        ("up Q3 demand below level", [9, 9.1, 9.4], [9.2, 9.5, 10.2], [8.9, 9.2, 9.3], [9.0, 9.3, 10.1], 10, True, [False, False, True, True], True),
        ("down Q1 prior up close", [10.6, 10.6, 10.7], [10.9, 12.0, 10.8], [10.4, 10.5, 9.8], [10.5, 10.8, 9.9], 10, False, [True, False, False, False], True),
        ("down none (prior down close, demand too far)", [10.6, 10.6, 10.3], [10.9, 10.7, 10.4], [10.4, 10.2, 9.9], [10.5, 10.3, 10.0], 10, False, [False, False, False, False], False),
    ]
    ok = True
    for name, o, h, l, c, lvl, up, exp_q, exp_ok in cases:
        js = m.group(0) + f"\nconsole.log(JSON.stringify(propBreakQual({o},{h},{l},{c},2,{lvl},{str(up).lower()},0.01)));"
        r = json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout)
        good = r["q"] == exp_q and r["ok"] == exp_ok
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  qualifiers: {name}: q={r['q']} ok={r['ok']} (exp {exp_q} {exp_ok})")
    return ok


def check_ipo_grid() -> bool:
    """IPO grid: JS ipoLevels() line generation, server split math and 424B4 cover-price parser."""
    import json
    import re
    import shutil
    import subprocess
    ok = True
    node = shutil.which("node")
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"), encoding="utf-8").read()
    m = re.search(r"^function ipoLevels\(.*?^}$", src, re.M | re.S)
    if not node or not m:
        print("  SKIP  ipoLevels (node not installed)" if not node else "  FAIL  ipoLevels() not found in index.html")
        ok &= bool(not node)
    else:
        # (name, ipo, mult, lo, hi, below, expected-first-and-count or exact list)
        cases = [
            ("IPO 10, step 0.5x -> 10,15,20,25,30", 10, 0.5, 8, 31, False, [10, 15, 20, 25, 30]),
            ("below IPO, never <= 0 (5,10,..)", 10, 0.5, 0, 30, True, [5, 10, 15, 20, 25, 30]),
            ("no lines below when 'Below' off", 10, 0.5, 0, 30, False, [10, 15, 20, 25, 30]),
            ("step 1.0x", 68, 1.0, 100, 300, True, [136, 204, 272]),
            ("range entirely below IPO", 68, 0.5, 5, 20, True, [])
        ]
        for name, ipo, mult, lo, hi, below, exp in cases:
            js = m.group(0) + f"\nconsole.log(JSON.stringify(ipoLevels({ipo},{mult},{lo},{hi},{str(below).lower()},5000)));"
            got = json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout)
            good = [round(x, 6) for x in got] == exp
            ok &= good
            print(f"  {'PASS' if good else 'FAIL'}  ipoLevels: {name}: {got} (exp {exp})")
        js = m.group(0) + "\nconst a=ipoLevels(10,0.5,0,100000,true,5000);console.log(a.length+' '+a[a.length-1]);"
        n, last = subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout.split()
        good = (int(n), float(last)) == (5000, 25000.0)  # no upper limit other than the 5000-line safety cap
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  ipoLevels: very tall range reaches {last} with {n} lines (cap 5000)")
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import server as S
    except Exception as e:  # noqa: BLE001
        print(f"  SKIP  server-side IPO checks (cannot import server.py: {type(e).__name__})")
        return ok
    from datetime import date
    nvda = [{"date": d, "numerator": n, "denominator": dn} for d, n, dn in
            [("2000-06-27", 2, 1), ("2001-09-12", 2, 1), ("2006-04-07", 2, 1), ("2007-09-11", 3, 2), ("2021-07-20", 4, 1), ("2024-06-10", 10, 1)]]
    f, _ = S._split_factor(nvda, date(1999, 1, 22))
    good = abs(f - 480) < 1e-9 and abs(12 / f - 0.025) < 1e-12
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  NVDA splits after 1999-01-22: factor {f:g} (exp 480), $12 -> {12 / f:g} (exp 0.025)")
    f, _ = S._split_factor([{"date": "2015-01-05", "numerator": 1, "denominator": 10}, {"date": "2010-01-01", "numerator": 2, "denominator": 1}], date(2012, 1, 1))
    good = abs(f - 0.1) < 1e-12 and abs(20 / f - 200) < 1e-9
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  reverse split 1:10 after IPO (2:1 before IPO ignored): factor {f:g} (exp 0.1), $20 -> {20 / f:g} (exp 200)")
    covers = [
        ("META 2012 cover", "PRICE $38.00 A SHARE Price to Public Underwriting Discounts Per share $38.00 $0.418 $37.582", 38.0),
        ("NVDA 1999 cover (SGML text)", "PRICE $12 A SHARE ---- Per Share....... $12.00 $.84 $11.16", 12.0),
        ("ABNB 2020 cover", "The initial public offering price is $68.00 per share. Per Share Total Initial public offering price $ 68.0000", 68.0),
        ("table only", "Price to Public Underwriting discounts Per Share $ 17.00 $1.19 $15.81", 17.0),
        ("no price", "This prospectus supplement relates to resales", None),
    ]
    for name, text, exp in covers:
        got = S._parse_offer_price(text)
        good = got == exp
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  424B4 cover parser: {name}: {got} (exp {exp})")
    return ok


def check_ipo_api(base: str) -> bool:
    """Live /api/ipo checks (needs the server running with FMP_API_KEY; SEC_USER_AGENT enables the EDGAR cross-check)."""
    import json
    import urllib.request
    exp = {"ABNB": (68, 1.0), "DASH": (102, 1.0), "RIVN": (78, 1.0), "TSLA": (17, 15.0)}
    ok = True
    for sym, (offer, f) in exp.items():
        with urllib.request.urlopen(f"{base}/api/ipo?symbol={sym}", timeout=120) as r:
            j = json.load(r)
        good = j.get("found") and abs(j["offer"] - offer) < 1e-9 and abs(j["splitFactor"] - f) < 1e-9 and abs(j["adjustedOffer"] - offer / f) < 1e-3
        ok &= bool(good)
        print(f"  {'PASS' if good else 'FAIL'}  /api/ipo {sym}: offer={j.get('offer')} splitFactor={j.get('splitFactor')} adjusted={j.get('adjustedOffer')} ({j.get('source')})")
    for sym, why in (("AAPL", "pre-EDGAR IPO (1980)"), ("ZZZZQ", "unknown ticker"), ("ES", "futures")):
        with urllib.request.urlopen(f"{base}/api/ipo?symbol={sym}", timeout=120) as r:
            j = json.load(r)
        good = j.get("found") is False
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  /api/ipo {sym} not found ({why}): {j.get('message')}")
    return ok


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

    # TD Propulsion (Perl, USD/JPY Fig. 6.7): run the chart's own JS propLevels()
    if not check_propulsion():
        failures.append("propulsion")
    if not check_breakout_qualifiers():
        failures.append("breakout qualifiers")
    if not check_ipo_grid():
        failures.append("ipo grid")
    if "--ipo" in sys.argv:
        k = sys.argv.index("--ipo")
        if not check_ipo_api(sys.argv[k + 1] if len(sys.argv) > k + 1 else "http://127.0.0.1:8765"):
            failures.append("ipo api")

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
# where the level becomes defined, tentative or not) has low <= level <= high,
# except a "held" level exactly touched by the latest pivot's extreme (then:
# no bar since its anchor may trade through it).
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
            pg.goto(f"{base}/?t={t}&tf=1d")  # daily
            pg.wait_for_function("document.getElementById('status').textContent.includes(' bars ·')", timeout=60000)
            info = pg.evaluate("""() => ({
                levels: visibleLevels().map(v => ({price: v.price, txt: lvlText(v), anchor: v.anchorDate, tent: v.anchorTent, held: !!v.held, heldAt: v.heldAt || null, kind: v.held ? P.find(p => p.date === v.heldAt).kind : null})),
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
            closes = h["closes"]
            for lv in info["levels"]:
                a = idx[lv["anchor"]]
                if lv["held"]:
                    # held marker: never traded THROUGH since its anchor (a wick exactly at it is ok)
                    is_low = lv["kind"] == "low"
                    for j in range(a + 1, len(dates)):
                        if hi[j] is not None and ((lo[j] < lv["price"]) if is_low else (hi[j] > lv["price"])):
                            bad.append(f"{lv['txt']} held at {lv['heldAt']} but traded through {dates[j]} [{lo[j]}-{hi[j]}]")
                            break
                    continue
                start = a + 1
                for j in range(start, len(dates)):
                    if hi[j] is not None and lo[j] <= lv["price"] <= hi[j]:
                        bad.append(f"{lv['txt']} (anchor {lv['anchor']}) touched {dates[j]} [{lo[j]}-{hi[j]}]")
                        break
            nh = sum(1 for lv in info["levels"] if lv["held"])
            print(f"{t}: {len(info['levels'])} drawn levels ({nh} held), {len(info['zones'])} zones -> {'OK' if not bad else 'FAIL'}")
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
