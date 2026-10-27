"""Universe: S&P 500 + Nasdaq 100 + major ETFs + SPX (display ticker)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache" / "universe"
FMP_BASE = "https://financialmodelingprep.com/stable/"

MAJOR_ETFS = [
    "SPY", "QQQ", "IWM", "DIA", "GLD", "SLV", "GDX", "GDXJ", "TLT",
    "XLE", "XLF", "XLK", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE",
    "SMH", "ARKK",
]

# display ticker -> FMP symbol for bar fetch
FMP_FETCH_ALIAS = {
    "SPX": "^GSPC",
}


def _key() -> str:
    return os.environ.get("FMP_API_KEY", "").strip()


def _get_list(path: str) -> list[dict] | None:
    k = _key()
    if not k:
        return None
    try:
        r = requests.get(FMP_BASE + path, params={"apikey": k}, timeout=45)
        if r.status_code != 200:
            return None
        j = r.json()
        return j if isinstance(j, list) else None
    except Exception:
        return None


def _symbols_from(rows: list[dict] | None) -> list[str]:
    if not rows:
        return []
    out = []
    for row in rows:
        s = (row.get("symbol") or "").strip().upper()
        if s and s.isascii() and all(c.isalnum() or c in ".-" for c in s):
            out.append(s)
    return out


def load_universe(force_refresh: bool = False) -> dict:
    """Return {tickers: [...], sources: {...}, asof: iso}."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE / "universe.json"
    if cache_path.exists() and not force_refresh:
        age_h = (datetime.now(timezone.utc).timestamp() - cache_path.stat().st_mtime) / 3600
        if age_h < 24:
            return json.loads(cache_path.read_text())

    sp = _symbols_from(_get_list("sp500-constituent"))
    ndx = _symbols_from(_get_list("nasdaq-constituent"))
    sources = {"sp500": "fmp" if sp else "cache_fallback", "nasdaq100": "fmp" if ndx else "cache_fallback"}

    if not sp and cache_path.exists():
        old = json.loads(cache_path.read_text())
        sp = [t for t in old.get("tickers", []) if t not in MAJOR_ETFS and t != "SPX"]
        # keep old if FMP failed — imperfect but better than empty
        sources["sp500"] = "stale_cache"
    if not ndx and cache_path.exists():
        sources["nasdaq100"] = "stale_cache"

    # Fallback static seeds if still empty (small)
    if not sp:
        sp = ["AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "BRK-B", "JPM", "V", "UNH"]
        sources["sp500"] = "seed_fallback"
    if not ndx:
        ndx = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AVGO", "TSLA", "COST", "NFLX"]
        sources["nasdaq100"] = "seed_fallback"

    tickers = sorted(set(sp) | set(ndx) | set(MAJOR_ETFS) | {"SPX"})
    payload = {
        "asof": datetime.now(timezone.utc).isoformat(),
        "tickers": tickers,
        "counts": {
            "sp500": len(sp),
            "nasdaq100": len(ndx),
            "etfs": len(MAJOR_ETFS),
            "index": 1,
            "unique": len(tickers),
        },
        "sources": sources,
        "etfs": MAJOR_ETFS,
    }
    cache_path.write_text(json.dumps(payload, indent=2))
    # also keep constituent snapshots
    (CACHE / "sp500.json").write_text(json.dumps(sp))
    (CACHE / "nasdaq100.json").write_text(json.dumps(ndx))
    return payload


def fmp_symbol(display: str) -> str:
    return FMP_FETCH_ALIAS.get(display.upper(), display.upper())
