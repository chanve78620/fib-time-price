#!/usr/bin/env python3
"""Fib Time & Price — serve UI and daily OHLC swing pivots via yfinance."""

from __future__ import annotations

import math
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
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


# Timeframes: UI key -> (yfinance interval,
# default period, allowed periods). Yahoo limits: 15m/30m ~60 days of
# history, 60m ~730 days.
TIMEFRAMES: dict[str, dict[str, Any]] = {
    "1wk": {"interval": "1wk", "default": "10y",
            "periods": ["1y", "2y", "5y", "10y", "max"]},
    "1d": {"interval": "1d", "default": "2y",
           "periods": ["6mo", "1y", "2y", "5y", "10y"]},
    "60m": {"interval": "60m", "default": "3mo",
            "periods": ["1mo", "3mo", "6mo", "1y", "730d"]},
    "30m": {"interval": "30m", "default": "1mo",
            "periods": ["5d", "1mo", "60d"]},
    "15m": {"interval": "15m", "default": "1mo",
            "periods": ["5d", "1mo", "60d"]},
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
    cfg = TIMEFRAMES[tf]
    try:
        # Raw (dividend-unadjusted) OHLC like Dynamic Trader; Yahoo still split-adjusts.
        df = yf.Ticker(t).history(period=period, interval=cfg["interval"], auto_adjust=False)
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
    out["session"] = _session_kind(sym)
    out["intraday"] = TIMEFRAMES[tf]["interval"] not in ("1d", "1wk")
    out["tz"] = "UTC" if out["session"] == "24x7" and out["intraday"] else "America/New_York"
    return jsonify(out)


@app.get("/api/timeframes")
def api_timeframes():
    return jsonify({k: {"default": v["default"], "periods": v["periods"]} for k, v in TIMEFRAMES.items()})


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True})


def main():
    port = int(os.environ.get("PORT", "8765"))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
