#!/usr/bin/env python3
"""Daily Time+Price confluence scanner.

Universe: S&P 500 + Nasdaq 100 + major ETFs + SPX.
Uses fib_time_price.time_price_flag (walk-forward DTP × Fib zones).

Outputs JSON+CSV under scanner/out/YYYY-MM-DD.* and latest.json / canvas payload.

Env:
  FMP_API_KEY   required
  SCAN_WORKERS  default 6
  SCAN_YEARS    history years for bars (default 2)
"""
from __future__ import annotations

import csv
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fib_time_price.time_price_flag import (  # noqa: E402
    Bars,
    FlagParams,
    chart_url,
    find_time_price_flags,
    summarize_past_year,
)
from scanner.universe import fmp_symbol, load_universe  # noqa: E402

SCANNER = Path(__file__).resolve().parent
OUT = SCANNER / "out"
BAR_CACHE = SCANNER / "cache" / "bars"
FMP_BASE = "https://financialmodelingprep.com/stable/"
SITE = "https://fib-time-price.onrender.com"
ET = ZoneInfo("America/New_York")

_http = requests.Session()
_rl_lock = threading.Lock()
_last_req = 0.0
_min_interval = 0.12  # ~8 req/s soft cap


EARN_CACHE = SCANNER / "cache" / "earnings"


def _next_trading_day(iso: str) -> str:
    """Next Mon–Fri after iso (holiday-agnostic, matches scanner windows)."""
    from datetime import datetime as _dt, timedelta as _td
    d = _dt.strptime(iso[:10], "%Y-%m-%d").date()
    d += _td(days=1)
    while d.weekday() >= 5:
        d += _td(days=1)
    return d.isoformat()


def _dates_in_window(start: str, end: str) -> set[str]:
    """Inclusive calendar dates from start..end (ISO)."""
    from datetime import datetime as _dt, timedelta as _td
    a = _dt.strptime(start[:10], "%Y-%m-%d").date()
    b = _dt.strptime(end[:10], "%Y-%m-%d").date()
    if b < a:
        a, b = b, a
    out = set()
    d = a
    while d <= b:
        out.add(d.isoformat())
        d += _td(days=1)
    return out


def _norm_earn_time(raw) -> str | None:
    """Map FMP time fields to BMO/AMC when present."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    if s in ("bmo", "before market open", "before-market", "pre-market", "premarket"):
        return "BMO"
    if s in ("amc", "after market close", "after-market", "post-market", "postmarket"):
        return "AMC"
    if "before" in s or s == "bmo":
        return "BMO"
    if "after" in s or s == "amc":
        return "AMC"
    # pass through short codes
    if s.upper() in ("BMO", "AMC"):
        return s.upper()
    return None


def fetch_earnings_calendar(d0: str, d1: str) -> dict[str, list[dict]]:
    """Day-chunked FMP stable/earnings-calendar → {SYMBOL: [{date, time}, ...]}.

    Wide from/to ranges hit a 4000-row cap and drop US names; one day at a time
    stays under the cap. Disk-cached per day under cache/earnings/.
    """
    from datetime import datetime as _dt, timedelta as _td
    EARN_CACHE.mkdir(parents=True, exist_ok=True)
    a = _dt.strptime(d0[:10], "%Y-%m-%d").date()
    b = _dt.strptime(d1[:10], "%Y-%m-%d").date()
    by_sym: dict[str, list[dict]] = {}
    d = a
    while d <= b:
        iso = d.isoformat()
        cache_path = EARN_CACHE / f"{iso}.json"
        rows = None
        if cache_path.exists():
            try:
                rows = json.loads(cache_path.read_text())
            except Exception:
                rows = None
        if rows is None:
            params = {"from": iso, "to": iso, "apikey": _key()}
            rows = []
            for attempt in range(4):
                _throttle()
                try:
                    r = _http.get(FMP_BASE + "earnings-calendar", params=params, timeout=40)
                except Exception:
                    time.sleep(1.2 * (attempt + 1))
                    continue
                if r.status_code == 429:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                if r.status_code == 200:
                    j = r.json()
                    rows = j if isinstance(j, list) else []
                break
            cache_path.write_text(json.dumps(rows))
        for x in rows or []:
            sym = str(x.get("symbol") or "").strip().upper()
            # Keep hyphenated US (BF-B); drop exchange suffixes like 018250.KS
            if not sym or "." in sym:
                continue
            ed = str(x.get("date") or "")[:10]
            if not ed:
                continue
            timing = _norm_earn_time(x.get("time") or x.get("hour") or x.get("when"))
            by_sym.setdefault(sym, []).append({"date": ed, "time": timing})
        d += _td(days=1)
    return by_sym


def annotate_earnings(rows: list[dict]) -> list[dict]:
    """Set earnings_date, earnings_timing, earnings_flag on each row."""
    if not rows:
        return rows
    starts = [r["window_start"][:10] for r in rows if r.get("window_start")]
    ends = [r["window_end"][:10] for r in rows if r.get("window_end")]
    d0 = min(starts)
    # pad +5 calendar days past furthest next-trading-day
    from datetime import datetime as _dt, timedelta as _td
    d1 = (_dt.strptime(max(ends), "%Y-%m-%d").date() + _td(days=10)).isoformat()
    cal = fetch_earnings_calendar(d0, d1)
    for r in rows:
        t = (r.get("ticker") or "").upper()
        # SPX/ETF index aliases: no single-stock earnings
        events = cal.get(t) or []
        # also try FMP alias if different display (rare)
        ws, we = r["window_start"][:10], r["window_end"][:10]
        danger = _dates_in_window(ws, we)
        danger.add(_next_trading_day(we))
        hit = None
        for ev in events:
            if ev["date"] in danger:
                hit = ev
                break
        if hit:
            r["earnings_date"] = hit["date"]
            r["earnings_timing"] = hit.get("time")  # BMO/AMC or None
            r["earnings_flag"] = True
        else:
            r["earnings_date"] = None
            r["earnings_timing"] = None
            r["earnings_flag"] = False
    return rows



def _today_et() -> str:
    return datetime.now(ET).date().isoformat()

def _fwd_date(bars: Bars, xi: int) -> str:
    """Calendar date for bar index xi (past or synthetic future weekday)."""
    if xi < bars.n:
        return bars.dates[xi]
    from datetime import datetime as _dt, timedelta as _td
    d = _dt.strptime(bars.dates[-1][:10], "%Y-%m-%d").date()
    left = xi - (bars.n - 1)
    while left > 0:
        d += _td(days=1)
        if d.weekday() < 5:  # Mon-Fri approx (ignores holidays)
            left -= 1
    return d.isoformat()



def _key() -> str:
    k = os.environ.get("FMP_API_KEY", "").strip()
    if not k:
        raise SystemExit("FMP_API_KEY is not set")
    return k


def _throttle():
    global _last_req
    with _rl_lock:
        now = time.time()
        wait = _min_interval - (now - _last_req)
        if wait > 0:
            time.sleep(wait)
        _last_req = time.time()


def fetch_daily(display: str, years: float = 2.0) -> Bars | None:
    """Fetch ~years of daily bars from FMP; disk-cache by date."""
    BAR_CACHE.mkdir(parents=True, exist_ok=True)
    day = _today_et()
    cache_path = BAR_CACHE / f"{display.upper()}.json"
    if cache_path.exists():
        try:
            blob = json.loads(cache_path.read_text())
            if blob.get("asof") == day and blob.get("bars"):
                return Bars.from_dict(blob["bars"], ticker=display.upper())
        except Exception:
            pass

    sym = fmp_symbol(display)
    d1 = datetime.now(ET).date()
    d0 = d1 - timedelta(days=int(365 * years) + 20)
    params = {"symbol": sym, "from": d0.isoformat(), "to": d1.isoformat(), "apikey": _key()}
    for attempt in range(5):
        _throttle()
        try:
            r = _http.get(FMP_BASE + "historical-price-eod/full", params=params, timeout=40)
        except Exception:
            time.sleep(1.5 * (attempt + 1))
            continue
        if r.status_code == 429:
            time.sleep(2.5 * (attempt + 1))
            continue
        if r.status_code != 200:
            return None
        rows = r.json()
        if not isinstance(rows, list) or not rows:
            return None
        # FMP returns newest first
        rows = sorted(rows, key=lambda x: x.get("date") or "")
        dates, o, h, l, c = [], [], [], [], []
        for x in rows:
            if not x.get("date") or x.get("high") is None or x.get("low") is None or x.get("close") is None:
                continue
            dates.append(str(x["date"])[:10])
            cl = float(x["close"])
            o.append(float(x["open"]) if x.get("open") is not None else cl)
            h.append(float(x["high"]))
            l.append(float(x["low"]))
            c.append(cl)
        if len(dates) < 80:
            return None
        bars = {"dates": dates, "opens": o, "highs": h, "lows": l, "closes": c, "ticker": display.upper()}
        cache_path.write_text(json.dumps({"asof": day, "fmp_symbol": sym, "bars": bars}))
        return Bars.from_dict(bars, ticker=display.upper())
    return None


def _trading_days_ahead(bars: Bars, n: int = 3) -> int:
    """Index offset: last bar + n (approx; future slots are bar counts)."""
    return bars.n - 1 + n


def row_from_flag(f, last_close: float, hit_rate: float | None, status: str) -> dict:
    zmid = 0.5 * (f.zone_lo + f.zone_hi)
    dist_pct = None if zmid == 0 else (last_close - zmid) / zmid * 100.0
    return {
        "ticker": f.ticker,
        "kind": f.kind,  # low / high
        "status": status,  # now | upcoming
        "window_start": f.date0,
        "window_end": f.date1,
        "zone_lo": round(f.zone_lo, 4),
        "zone_hi": round(f.zone_hi, 4),
        "zone_label": f.zone_label,
        "zone_n": f.zone_n,
        "last_close": round(last_close, 4),
        "dist_to_zone_pct": round(dist_pct, 3) if dist_pct is not None else None,
        "strength": round(f.peak_strength, 3),
        "hit_rate_1y": round(hit_rate, 3) if hit_rate is not None else None,
        "chart_url": chart_url(f.ticker, base=SITE),
        "future": bool(f.future),
        "in_zone_now": bool(f.in_zone_now),
        "earnings_date": None,
        "earnings_timing": None,
        "earnings_flag": False,
    }


def scan_ticker(display: str, params: FlagParams, years: float) -> list[dict]:
    bars = fetch_daily(display, years=years)
    if bars is None or bars.n < 80:
        return []
    try:
        flags = find_time_price_flags(bars, params, include_future=True, lookback_bars=260)
    except Exception:
        return []
    n1 = bars.n - 1
    ahead = _trading_days_ahead(bars, 3)
    last = bars.c[n1]
    hits: list = []
    need_hr = False
    tol = max(1, int(round(params.band)))
    for f in flags:
        if f.future:
            # Upcoming: peak/window starts within the next 3 trading bars
            if n1 < f.i0 <= ahead:
                hits.append((f, "upcoming"))
                need_hr = True
            # Now: live cluster already overlapping the last bar AND price in/near zone
            elif f.i0 <= n1 <= f.i1 + tol and f.in_zone_now:
                hits.append((f, "now"))
                need_hr = True
        else:
            # Past walk-forward cluster still covering the last bar (±Band)
            if f.i0 - tol <= n1 <= f.i1 + tol:
                hits.append((f, "now"))
                need_hr = True

    if not hits:
        return []
    hr = None
    if need_hr:
        try:
            s = summarize_past_year(bars, params)
            hr = s.get("hit_rate")
        except Exception:
            hr = None
    out = []
    for f, status in hits:
        # normalize +Nb future labels to estimated calendar dates
        f.date0 = _fwd_date(bars, f.i0) if str(f.date0).startswith("+") or f.i0 >= bars.n else f.date0
        f.date1 = _fwd_date(bars, f.i1) if str(f.date1).startswith("+") or f.i1 >= bars.n else f.date1
        out.append(row_from_flag(f, last, hr, status))
    return out


def write_outputs(rows: list[dict], meta: dict) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    day = meta["scan_date"]
    # de-dupe ticker+kind+status keep strongest
    best: dict[tuple, dict] = {}
    for r in rows:
        key = (r["ticker"], r["kind"], r["status"])
        prev = best.get(key)
        if prev is None or (r.get("strength") or 0) > (prev.get("strength") or 0):
            best[key] = r
    rows = sorted(best.values(), key=lambda r: (r["status"] != "now", r["kind"], -(r.get("strength") or 0), r["ticker"]))

    payload = {**meta, "rows": rows, "n_now": sum(1 for r in rows if r["status"] == "now"),
               "n_upcoming": sum(1 for r in rows if r["status"] == "upcoming"),
               "n_low": sum(1 for r in rows if r["kind"] == "low"),
               "n_high": sum(1 for r in rows if r["kind"] == "high")}
    json_path = OUT / f"{day}.json"
    json_path.write_text(json.dumps(payload, indent=2))
    (OUT / "latest.json").write_text(json.dumps(payload, indent=2))

    csv_path = OUT / f"{day}.csv"
    cols = [
        "ticker", "kind", "status", "window_start", "window_end", "zone_label",
        "zone_lo", "zone_hi", "last_close", "dist_to_zone_pct", "strength",
        "hit_rate_1y", "earnings_date", "earnings_timing", "earnings_flag", "chart_url",
    ]
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    (OUT / "latest.csv").write_text(csv_path.read_text())
    return json_path


def main() -> int:
    t0 = time.time()
    years = float(os.environ.get("SCAN_YEARS", "2"))
    workers = int(os.environ.get("SCAN_WORKERS", "6"))
    uni = load_universe()
    tickers = uni["tickers"]
    params = FlagParams()
    day = _today_et()
    print(f"scan {day} universe={len(tickers)} workers={workers}", flush=True)

    rows: list[dict] = []
    errors = 0
    done = 0
    lock = threading.Lock()

    def work(t: str):
        nonlocal errors, done
        try:
            r = scan_ticker(t, params, years)
        except Exception:
            with lock:
                errors += 1
            r = []
        with lock:
            done += 1
            if done % 50 == 0 or done == len(tickers):
                print(f"  progress {done}/{len(tickers)} hits_so_far={len(rows)+len(r)} errors={errors}", flush=True)
        return r

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(work, t): t for t in tickers}
        for fut in as_completed(futs):
            try:
                rows.extend(fut.result() or [])
            except Exception:
                errors += 1

    elapsed = round(time.time() - t0, 1)
    meta = {
        "scan_date": day,
        "scanned_at": datetime.now(ET).isoformat(),
        "universe_size": len(tickers),
        "universe_counts": uni.get("counts"),
        "universe_sources": uni.get("sources"),
        "runtime_sec": elapsed,
        "errors": errors,
        "params": {
            "swing": params.swing,
            "band": params.band,
            "min_strength": params.min_strength,
            "zone_tol_pct": params.zone_tol_pct,
            "years": years,
        },
        "site": SITE,
    }
    rows = annotate_earnings(rows)
    n_earn = sum(1 for r in rows if r.get("earnings_flag"))
    meta["n_earnings_flag"] = n_earn
    path = write_outputs(rows, meta)
    payload = json.loads(path.read_text())
    print(
        f"DONE now={payload['n_now']} upcoming={payload['n_upcoming']} "
        f"low={payload['n_low']} high={payload['n_high']} "
        f"earnings_flag={payload.get('n_earnings_flag', meta.get('n_earnings_flag'))} "
        f"runtime={elapsed}s -> {path}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
