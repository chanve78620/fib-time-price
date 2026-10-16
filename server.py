#!/usr/bin/env python3
"""Fib Time & Price — serve UI and OHLC swing pivots (Financial Modeling Prep, Yahoo fallback)."""

from __future__ import annotations

import math
import os
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import yfinance as yf
from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=str(ROOT), static_url_path="")

MIN_LEG_DAYS = 40
SUGGEST_REVERSAL_PCT = 0.03
SUGGEST_LAST_LEGS = 5
MAX_PIVOTS = 40


def _iso(d) -> str:
    if hasattr(d, "hour") and (d.hour or d.minute):
        return d.strftime("%Y-%m-%dT%H:%M")
    if hasattr(d, "date"):
        d = d.date()
    return d.isoformat()


def _normalize_ticker(raw: str) -> str:
    t = raw.strip().upper().replace(" ", "")
    if t.endswith("-D"):  # Dynamic Trader style "$SPX-D"
        t = t[:-2]
    # Common continuous / front-month aliases → Yahoo symbols
    aliases = {
        "ES": "ES=F",
        "ES1!": "ES=F",
        "ESZ26": "ES=F",
        "ESZ26-D": "ES=F",
        "NQ": "NQ=F",
        "NQ1!": "NQ=F",
        "YM": "YM=F",
        "RTY": "RTY=F",
        "CL": "CL=F",
        "GC": "GC=F",
        "SI": "SI=F",
        "SI1!": "SI=F",
        "SPX": "^GSPC",
        "$SPX": "^GSPC",
        "GSPC": "^GSPC",
        "NDX": "^NDX",
        "$NDX": "^NDX",
        "COMP": "^IXIC",
        "IXIC": "^IXIC",
        "DJI": "^DJI",
        "DJIA": "^DJI",
        "$DJI": "^DJI",
        "INDU": "^DJI",
        "RUT": "^RUT",
        "$RUT": "^RUT",
        "VIX": "^VIX",
        "$VIX": "^VIX",
        "ZB": "ZB=F",
        "ZN": "ZN=F",
        "NG": "NG=F",
        "HG": "HG=F",
        "BTC": "BTC-USD",
        "ETH": "ETH-USD",
    }
    t = aliases.get(t, t)
    if t.startswith("$"):
        t = t[1:]
    return t


# Timeframes: UI key -> yfinance interval / FMP interval, default and allowed
# periods. Financial Modeling Prep (primary, needs FMP_API_KEY) has years of
# intraday history; Yahoo (fallback) only ~60 days of 15m/30m and 730d of 60m.
# Max intraday lookback is configurable: MAX_15M / MAX_30M / MAX_60M (period
# strings such as "1y", "2y", "3y").
_ALL_INTRADAY_PERIODS = ["5d", "1mo", "3mo", "6mo", "1y", "2y", "3y", "5y"]


def _period_days(p: str) -> int | None:
    """Calendar days for a period string; None = all available."""
    p = (p or "").strip().lower()
    if p == "max":
        return None
    if p == "ytd":
        today = _today()
        return (today - today.replace(month=1, day=1)).days + 1
    try:
        n = int(p[:-2]) if p.endswith("mo") else int(p[:-1])
    except ValueError:
        return 365
    if p.endswith("mo"):
        return int(round(n * 30.5))
    unit = p[-1]
    return n * {"d": 1, "w": 7, "y": 366}.get(unit, 1)


def _intraday_periods(max_p: str) -> list[str]:
    lim = _period_days(max_p) or 10**6
    return [p for p in _ALL_INTRADAY_PERIODS if (_period_days(p) or 0) <= lim] or ["1mo"]


TIMEFRAMES: dict[str, dict[str, Any]] = {
    "1wk": {"interval": "1wk", "fmp": None, "default": "10y",
            "periods": ["1y", "2y", "5y", "10y", "max"]},
    "1d": {"interval": "1d", "fmp": None, "default": "2y",
           "periods": ["6mo", "1y", "2y", "5y", "10y"]},
    "60m": {"interval": "60m", "fmp": "1hour", "default": "3mo", "yahoo_max": 730,
            "chunk": 80, "periods": _intraday_periods(os.environ.get("MAX_60M", "3y"))},
    "30m": {"interval": "30m", "fmp": "30min", "default": "1mo", "yahoo_max": 60,
            "chunk": 25, "periods": _intraday_periods(os.environ.get("MAX_30M", "2y"))},
    "15m": {"interval": "15m", "fmp": "15min", "default": "1mo", "yahoo_max": 60,
            "chunk": 30, "periods": _intraday_periods(os.environ.get("MAX_15M", "1y"))},
}
TF_ALIASES = {"w": "1wk", "wk": "1wk", "weekly": "1wk", "d": "1d", "daily": "1d",
              "60": "60m", "1h": "60m", "30": "30m", "15": "15m"}


def _norm_tf(raw: str | None) -> str:
    t = (raw or "1d").strip().lower()
    t = TF_ALIASES.get(t, t)
    return t if t in TIMEFRAMES else "1d"


def _session_kind(sym: str) -> str:
    """rth = US cash session 9:30-16:00 ET; fut = CME ~23h; 24x7 = crypto."""
    if sym.endswith("-USD") or sym.endswith("-USDT"):
        return "24x7"
    if sym.endswith("=F") or sym.endswith("=X"):
        return "fut"
    return "rth"


def _clamp_period(tf: str, period: str | None) -> str:
    cfg = TIMEFRAMES[tf]
    p = (period or "").strip()
    if p in cfg["periods"]:
        return p
    if cfg.get("fmp") and _period_days(p) and _period_days(p) > (_period_days(cfg["periods"][-1]) or 0):
        return cfg["periods"][-1]  # longer than the configured max -> max
    if tf in ("1d", "1wk") and p in ("1mo", "3mo", "6mo", "ytd", "1y", "2y", "5y", "10y", "max"):
        return p
    return cfg["default"]


# Simple in-memory cache of yfinance results: avoids hammering Yahoo (which
# rate-limits datacenter IPs) when the UI calls /api/pivots and /api/history.
CACHE_TTL = int(os.environ.get("CACHE_TTL", "600"))  # seconds
CACHE_MAX = 200
_cache: dict[tuple[str, str, str], tuple[float, Any]] = {}
_cache_lock = threading.Lock()


def _fetch_daily(ticker: str, period: str, tf: str = "1d"):
    key = (_normalize_ticker(ticker), period, tf)
    now = time.time()
    ttl = CACHE_TTL if tf in ("1d", "1wk") else min(CACHE_TTL, 120)
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    out = _fetch_daily_uncached(ticker, period, tf)
    if out[1] is None:  # only cache successes
        with _cache_lock:
            if len(_cache) >= CACHE_MAX:
                _cache.pop(min(_cache, key=lambda k: _cache[k][0]), None)
            _cache[key] = (now, out)
    return out


def _fetch_daily_uncached(ticker: str, period: str, tf: str = "1d"):
    t = _normalize_ticker(ticker)
    if not t or len(t) > 24 or not all(c.isalnum() or c in ".-^=" for c in t):
        return None, "Invalid ticker symbol"
    src = DATA_SOURCE
    if src in ("auto", "fmp") and _fmp_key():
        df, err = _fetch_fmp(t, period, tf)
        if df is not None and not df.empty:
            df.attrs["source"] = "fmp"
            return (t, df), None
        app.logger.warning("FMP fetch failed for %s %s %s: %s; falling back to Yahoo", t, tf, period, err)
        if src == "fmp":
            return None, err or f"No data found for ticker '{t}'"
    out = _fetch_yahoo(t, period, tf)
    if out[1] is None:
        out[0][1].attrs["source"] = "yahoo"
    return out


# ---------------------------------------------------------------------------
# Financial Modeling Prep (primary). Key comes only from the FMP_API_KEY env
# var; it is never logged or returned (errors are scrubbed).
FMP_BASE = "https://financialmodelingprep.com/stable/"
DATA_SOURCE = os.environ.get("DATA_SOURCE", "auto").strip().lower()  # auto | fmp | yahoo
FMP_TIMEOUT = float(os.environ.get("FMP_TIMEOUT", "20"))
FMP_WORKERS = int(os.environ.get("FMP_WORKERS", "8"))
_http = requests.Session()
_chunk_cache: dict[tuple, tuple[float, list]] = {}
_chunk_lock = threading.Lock()
CHUNK_CACHE_MAX = 3000
# Yahoo-style symbol -> FMP symbol
FMP_SYMBOLS = {
    "ES=F": "ESUSD", "NQ=F": "NQUSD", "YM=F": "YMUSD", "RTY=F": "RTYUSD",
    "CL=F": "CLUSD", "GC=F": "GCUSD", "SI=F": "SIUSD", "ZB=F": "ZBUSD",
    "ZN=F": "ZNUSD", "NG=F": "NGUSD", "HG=F": "HGUSD",
}


def _today():
    """Current US/Eastern date (Render runs in UTC)."""
    return datetime.now(ZoneInfo("America/New_York")).date()


def _fmp_key() -> str:
    return os.environ.get("FMP_API_KEY", "").strip()


def _fmp_symbol(t: str) -> str | None:
    if t in FMP_SYMBOLS:
        return FMP_SYMBOLS[t]
    if t.endswith("=F"):
        return None  # unmapped future -> Yahoo
    if t.endswith("=X"):
        return t[:-2]
    if t.endswith("-USD") or t.endswith("-USDT"):
        return t.replace("-", "")
    return t


def _scrub(msg: str) -> str:
    k = _fmp_key()
    return msg.replace(k, "***") if k else msg


def _fmp_get(path: str, params: dict) -> tuple[list | None, str | None]:
    q = dict(params)
    q["apikey"] = _fmp_key()
    try:
        r = _http.get(FMP_BASE + path, params=q, timeout=FMP_TIMEOUT)
    except Exception as e:  # noqa: BLE001
        return None, _scrub(f"FMP request failed: {type(e).__name__}")
    if r.status_code != 200:
        return None, f"FMP HTTP {r.status_code}"
    try:
        j = r.json()
    except ValueError:
        return None, "FMP returned non-JSON"
    if isinstance(j, dict):  # error payload
        return None, _scrub(str(j.get("Error Message") or j.get("error") or j)[:200])
    return j, None


def _fmp_range(path: str, sym: str, d0, d1, step_back: int) -> tuple[list | None, str | None]:
    """All rows in [d0, d1]. FMP caps rows per call (newest first), so if the
    oldest returned row is well after d0, page backwards until covered."""
    rows: dict[str, dict] = {}
    hi = d1
    for _ in range(12):
        j, err = _fmp_get(path, {"symbol": sym, "from": d0.isoformat(), "to": hi.isoformat()})
        if err:
            return None, err
        if not j:
            break
        for x in j:
            if x.get("date"):
                rows[x["date"]] = x
        oldest = min(x["date"] for x in j if x.get("date"))[:10]
        oldest_d = datetime.strptime(oldest, "%Y-%m-%d").date()
        if (oldest_d - d0).days <= step_back or oldest_d >= hi:
            break
        hi = oldest_d  # re-fetch the (possibly partial) oldest day; dedupe by key
    return list(rows.values()), None


def _fmp_intraday_chunk(sym: str, interval: str, k: int, size: int):
    """Fixed calendar chunk k (size days, epoch-aligned). Past chunks are
    immutable and cached for hours; the live chunk briefly."""
    from datetime import date, timedelta
    epoch = date(2000, 1, 3)
    d0 = epoch + timedelta(days=k * size)
    d1 = d0 + timedelta(days=size - 1)
    today = _today()
    key = (sym, interval, k, size)
    ttl = 60 if d1 >= today - timedelta(days=1) else 6 * 3600
    now = time.time()
    with _chunk_lock:
        hit = _chunk_cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1], None
    rows, err = _fmp_range(f"historical-chart/{interval}", sym, d0, min(d1, today + timedelta(days=1)), 4)
    if err is None:
        with _chunk_lock:
            if len(_chunk_cache) >= CHUNK_CACHE_MAX:
                for kk in sorted(_chunk_cache, key=lambda x: _chunk_cache[x][0])[: CHUNK_CACHE_MAX // 10]:
                    _chunk_cache.pop(kk, None)
            _chunk_cache[key] = (now, rows)
    return rows, err


def _fmp_frame(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
    df["_dt"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates("_dt").sort_values("_dt")
    for c in ("Open", "High", "Low", "Close"):
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    df = df.dropna(subset=["High", "Low", "Close"])
    df["Open"] = df["Open"].fillna(df["Close"])
    return df[["_dt", "Open", "High", "Low", "Close"] + (["Volume"] if "Volume" in df else [])].reset_index(drop=True)


def _fetch_fmp(t: str, period: str, tf: str):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import date, timedelta
    sym = _fmp_symbol(t)
    if not sym:
        return None, "no FMP symbol"
    cfg = TIMEFRAMES[tf]
    today = _today()
    days = _period_days(period)
    if cfg["fmp"] is None:  # daily / weekly (weekly = resampled daily)
        d0 = date(1900, 1, 1) if days is None else today - timedelta(days=days)
        rows, err = _fmp_range("historical-price-eod/full", sym, d0, today + timedelta(days=1), 7)
        if err or not rows:
            return None, err or "no FMP data"
        df = _fmp_frame(rows)
        df["_dt"] = df["_dt"].dt.normalize()
        if tf == "1wk":
            wk = df["_dt"] - pd.to_timedelta(df["_dt"].dt.weekday, unit="D")  # Monday label (as Yahoo)
            g = df.groupby(wk)
            df = pd.DataFrame({"Open": g["Open"].first(), "High": g["High"].max(),
                               "Low": g["Low"].min(), "Close": g["Close"].last()})
            df.index.name = "_dt"
            df = df.reset_index()
        return df, None
    # intraday: fixed epoch-aligned chunks fetched in parallel, cached
    size = int(cfg["chunk"])
    epoch = date(2000, 1, 3)
    d0 = today - timedelta(days=days or 365)
    k0 = (d0 - epoch).days // size
    k1 = (today - epoch).days // size
    ks = list(range(k0, k1 + 1))
    with ThreadPoolExecutor(max_workers=max(1, min(FMP_WORKERS, len(ks)))) as ex:
        res = list(ex.map(lambda k: _fmp_intraday_chunk(sym, cfg["fmp"], k, size), ks))
    errs = [e for _, e in res if e]
    if errs:
        return None, errs[0]
    rows = [x for r, _ in res for x in (r or [])]
    if not rows:
        return None, "no FMP intraday data"
    df = _fmp_frame(rows)
    df = df[df["_dt"] >= pd.Timestamp(d0)]
    if _session_kind(t) == "24x7":  # FMP stamps crypto in US/Eastern; UI expects UTC (as Yahoo)
        df["_dt"] = (df["_dt"].dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward")
                     .dt.tz_convert("UTC").dt.tz_localize(None))
        df = df.dropna(subset=["_dt"])
    if _session_kind(t) == "rth":  # regular session only (FMP times are US/Eastern)
        m = df["_dt"].dt.hour * 60 + df["_dt"].dt.minute
        df = df[(m >= 570) & (m < 960) & (df["_dt"].dt.weekday < 5)]
    return df.reset_index(drop=True), None


# ---------------------------------------------------------------------------
# Yahoo (fallback)
def _yahoo_period(tf: str, period: str) -> str:
    cfg = TIMEFRAMES[tf]
    lim = cfg.get("yahoo_max")
    if lim is None:
        return period
    d = _period_days(period) or 10**6
    if d <= lim:
        return period
    return "60d" if lim <= 60 else "730d"


def _fetch_yahoo(t: str, period: str, tf: str = "1d"):
    cfg = TIMEFRAMES[tf]
    try:
        # Raw (dividend-unadjusted) OHLC like Dynamic Trader; Yahoo still split-adjusts.
        df = yf.Ticker(t).history(period=_yahoo_period(tf, period), interval=cfg["interval"], auto_adjust=False)
    except Exception as e:  # noqa: BLE001
        return None, f"Failed to fetch data: {e}"
    if df is None or df.empty:
        return None, f"No data found for ticker '{t}' (unknown or delisted)"
    need = {"High", "Low", "Close"}
    if not need.issubset(set(df.columns)):
        return None, f"Incomplete OHLC data for '{t}'"
    df = df.copy()
    df = df.reset_index()
    # Column may be Date or Datetime
    date_col = "Date" if "Date" in df.columns else df.columns[0]
    ts = pd.to_datetime(df[date_col])
    if cfg["interval"] in ("1d", "1wk"):
        local = ts.dt.tz_localize(None) if ts.dt.tz is not None else ts
        df["_dt"] = local.dt.normalize()
    else:
        # keep exchange-local wall-clock time, drop tz (naive local)
        df["_dt"] = ts.dt.tz_localize(None) if ts.dt.tz is not None else ts
        if "Open" not in df.columns:
            df["Open"] = df["Close"]
        df = df.dropna(subset=["High", "Low", "Close"])
    df = df.reset_index(drop=True)
    return (t, df), None


def detect_pivots(df, lookback: int) -> list[dict[str, Any]]:
    """Swing highs/lows: High[i] max (Low[i] min) of window i-N..i+N."""
    n = int(lookback)
    if n < 1:
        n = 5
    highs = df["High"].to_numpy(dtype=float)
    lows = df["Low"].to_numpy(dtype=float)
    closes = df["Close"].to_numpy(dtype=float)
    dates = df["_dt"].tolist()
    raw: list[dict[str, Any]] = []
    for i in range(n, len(df) - n):
        wh = highs[i - n : i + n + 1]
        wl = lows[i - n : i + n + 1]
        if highs[i] >= wh.max() and not math.isnan(highs[i]):
            raw.append(
                {
                    "i": i,
                    "date": _iso(dates[i]),
                    "price": float(highs[i]),
                    "kind": "high",
                    "close": float(closes[i]),
                }
            )
        if lows[i] <= wl.min() and not math.isnan(lows[i]):
            raw.append(
                {
                    "i": i,
                    "date": _iso(dates[i]),
                    "price": float(lows[i]),
                    "kind": "low",
                    "close": float(closes[i]),
                }
            )
    raw.sort(key=lambda p: (p["i"], 0 if p["kind"] == "low" else 1))
    return _dedupe_adjacent(raw)


def _dedupe_adjacent(pivots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep more extreme when consecutive same-kind pivots."""
    out: list[dict[str, Any]] = []
    for p in pivots:
        if out and out[-1]["i"] == p["i"] and out[-1]["kind"] == p["kind"]:
            continue
        if out and out[-1]["kind"] == p["kind"]:
            prev = out[-1]
            if p["kind"] == "high" and p["price"] >= prev["price"]:
                out[-1] = p
            elif p["kind"] == "low" and p["price"] <= prev["price"]:
                out[-1] = p
            # else keep existing (more extreme)
        else:
            out.append(p)
    return out


def _coarsen_by_reversal(
    pivots: list[dict[str, Any]], min_pct: float
) -> list[dict[str, Any]]:
    """Drop opposite pivots that reverse less than min_pct (for suggestion only)."""
    if not pivots:
        return []
    out = [pivots[0]]
    for p in pivots[1:]:
        prev = out[-1]
        if p["kind"] == prev["kind"]:
            if p["kind"] == "high" and p["price"] >= prev["price"]:
                out[-1] = p
            elif p["kind"] == "low" and p["price"] <= prev["price"]:
                out[-1] = p
            continue
        base = prev["price"]
        if base == 0 or abs(p["price"] - base) / abs(base) < min_pct:
            continue
        out.append(p)
    return _dedupe_adjacent(out)


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def suggest_swing(pivots: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Latest meaningful alternating high↔low leg (≥40d when possible)."""
    if len(pivots) < 2:
        return None
    coarse = _coarsen_by_reversal(pivots, SUGGEST_REVERSAL_PCT)
    if len(coarse) < 2:
        coarse = pivots

    legs: list[tuple[float, int, dict, dict]] = []
    for a, b in zip(coarse, coarse[1:]):
        if a["kind"] == b["kind"]:
            continue
        days = (_parse_date(b["date"]) - _parse_date(a["date"])).days
        if days < MIN_LEG_DAYS:
            continue
        move = abs(b["price"] - a["price"])
        legs.append((move, days, a, b))

    if not legs:
        # Fallback: most recent adjacent opposite pair
        for a, b in zip(pivots, pivots[1:]):
            if a["kind"] == b["kind"]:
                continue
            days = (_parse_date(b["date"]) - _parse_date(a["date"])).days
            move = abs(b["price"] - a["price"])
            legs.append((move, days, a, b))
        if not legs:
            return None

    # Prefer the most recent qualifying leg (project off latest swing H/L)
    move, days, a, b = legs[-1]
    direction = f"{a['kind']} → {b['kind']}"
    return {
        "date1": a["date"],
        "date2": b["date"],
        "price1": round(a["price"], 4),
        "price2": round(b["price"], 4),
        "label": f"{direction} · {days}d · Δ{move:.2f} · latest",
    }


def _history_payload(sym: str, df, period: str, intraday: bool = False) -> dict[str, Any]:
    if intraday:
        dates = [d.strftime("%Y-%m-%dT%H:%M") for d in df["_dt"].tolist()]
    else:
        dates = [_iso(d) for d in df["_dt"].tolist()]
    closes = [round(float(x), 4) if not math.isnan(float(x)) else None for x in df["Close"]]
    highs = [round(float(x), 4) if not math.isnan(float(x)) else None for x in df["High"]]
    lows = [round(float(x), 4) if not math.isnan(float(x)) else None for x in df["Low"]]
    if "Open" in df.columns:
        opens = [round(float(x), 4) if not math.isnan(float(x)) else None for x in df["Open"]]
    else:
        opens = list(closes)
    return {
        "ticker": sym,
        "period": period,
        "dates": dates,
        "closes": closes,
        "highs": highs,
        "lows": lows,
        "opens": opens,
    }


@app.get("/")
def index():
    return send_from_directory(ROOT, "index.html")


@app.get("/classic")
def classic():
    return send_from_directory(ROOT, "classic.html")


@app.get("/api/pivots")
def api_pivots():
    ticker = (request.args.get("ticker") or "").strip()
    period = (request.args.get("period") or "2y").strip() or "2y"
    try:
        lookback = int(request.args.get("lookback") or 5)
    except ValueError:
        return jsonify({"error": "lookback must be an integer"}), 400
    if lookback < 1 or lookback > 30:
        return jsonify({"error": "lookback must be between 1 and 30"}), 400

    if not ticker:
        return jsonify({"error": "Missing ticker parameter"}), 400

    tf = _norm_tf(request.args.get("tf") or request.args.get("interval"))
    period = _clamp_period(tf, period)
    result, err = _fetch_daily(ticker, period, tf)
    if err:
        # Unknown / empty → 404; malformed → 400 already handled somewhat
        status = 400 if "Invalid" in err else 404
        return jsonify({"error": err, "ticker": ticker.strip().upper(), "pivots": []}), status

    sym, df = result
    pivots = detect_pivots(df, lookback)
    # Cap to most recent ~40, chronological
    if len(pivots) > MAX_PIVOTS:
        pivots = pivots[-MAX_PIVOTS:]

    # Strip internal index for JSON
    public = [
        {
            "date": p["date"],
            "price": round(p["price"], 4),
            "kind": p["kind"],
            "close": round(p["close"], 4),
        }
        for p in pivots
    ]
    suggested = suggest_swing(pivots)

    return jsonify(
        {
            "ticker": sym,
            "period": period,
            "lookback": lookback,
            "tf": tf,
            "source": df.attrs.get("source", "yahoo"),
            "pivots": public,
            "suggested": suggested,
        }
    )


@app.get("/api/history")
def api_history():
    """Daily OHLC arrays for chart context: dates, closes, highs, lows."""
    ticker = (request.args.get("ticker") or "").strip()
    period = (request.args.get("period") or "2y").strip() or "2y"

    if not ticker:
        return jsonify({"error": "Missing ticker parameter"}), 400

    tf = _norm_tf(request.args.get("tf") or request.args.get("interval"))
    period = _clamp_period(tf, period)
    result, err = _fetch_daily(ticker, period, tf)
    if err:
        status = 400 if "Invalid" in err else 404
        return jsonify(
            {
                "error": err,
                "ticker": ticker.strip().upper(),
                "dates": [],
                "closes": [],
                "highs": [],
                "lows": [],
            }
        ), status

    sym, df = result
    out = _history_payload(sym, df, period, TIMEFRAMES[tf]["interval"] not in ("1d", "1wk"))
    out["tf"] = tf
    out["source"] = df.attrs.get("source", "yahoo")
    out["session"] = _session_kind(sym)
    out["intraday"] = TIMEFRAMES[tf]["interval"] not in ("1d", "1wk")
    out["tz"] = "UTC" if out["session"] == "24x7" and out["intraday"] else "America/New_York"
    return jsonify(out)


@app.get("/api/timeframes")
def api_timeframes():
    fmp = DATA_SOURCE != "yahoo" and bool(_fmp_key())
    return jsonify({"source": "fmp" if fmp else "yahoo",
                    "timeframes": {k: {"default": v["default"], "periods": v["periods"],
                                       "yahoo_max_days": v.get("yahoo_max")} for k, v in TIMEFRAMES.items()}})


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True})


def main():
    port = int(os.environ.get("PORT", "8765"))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
