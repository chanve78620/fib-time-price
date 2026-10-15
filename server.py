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
    if hasattr(d, "date"):
        d = d.date()
    return d.isoformat()


def _normalize_ticker(raw: str) -> str:
    t = raw.strip().upper().replace(" ", "")
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
    }
    return aliases.get(t, t)


# Simple in-memory cache of yfinance results: avoids hammering Yahoo (which
# rate-limits datacenter IPs) when the UI calls /api/pivots and /api/history.
CACHE_TTL = int(os.environ.get("CACHE_TTL", "600"))  # seconds
CACHE_MAX = 200
_cache: dict[tuple[str, str], tuple[float, Any]] = {}
_cache_lock = threading.Lock()


def _fetch_daily(ticker: str, period: str):
    key = (_normalize_ticker(ticker), period)
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL:
            return hit[1]
    out = _fetch_daily_uncached(ticker, period)
    if out[1] is None:  # only cache successes
        with _cache_lock:
            if len(_cache) >= CACHE_MAX:
                _cache.pop(min(_cache, key=lambda k: _cache[k][0]), None)
            _cache[key] = (now, out)
    return out


def _fetch_daily_uncached(ticker: str, period: str):
    t = _normalize_ticker(ticker)
    if not t or len(t) > 24 or not all(c.isalnum() or c in ".-^=" for c in t):
        return None, "Invalid ticker symbol"
    try:
        df = yf.Ticker(t).history(period=period, interval="1d", auto_adjust=True)
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
    ts = pd.to_datetime(df[date_col], utc=True)
    df["_dt"] = ts.dt.tz_convert(None).dt.normalize()
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


def _history_payload(sym: str, df, period: str) -> dict[str, Any]:
    dates = [_iso(d) for d in df["_dt"].tolist()]
    closes = [round(float(x), 4) if not math.isnan(float(x)) else None for x in df["Close"]]
    highs = [round(float(x), 4) if not math.isnan(float(x)) else None for x in df["High"]]
    lows = [round(float(x), 4) if not math.isnan(float(x)) else None for x in df["Low"]]
    return {
        "ticker": sym,
        "period": period,
        "dates": dates,
        "closes": closes,
        "highs": highs,
        "lows": lows,
    }


@app.get("/")
def index():
    return send_from_directory(ROOT, "index.html")


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

    result, err = _fetch_daily(ticker, period)
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

    result, err = _fetch_daily(ticker, period)
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
    return jsonify(_history_payload(sym, df, period))


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True})


def main():
    port = int(os.environ.get("PORT", "8765"))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
