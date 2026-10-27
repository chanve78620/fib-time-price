# Time+Price (royal) confluence flag

Carolyn Boroden–style **time + price** confluence: a strong walk-forward DTP cluster
(normalized strength ≥ 0.9 / top-decile, within ±Band) coinciding with price trading
into an active Fib confluence zone (support for LOW, resistance for HIGH).

## UI
- Toggle **Time+Price** on the toolbar (gold/amber intersecting time×price box + diamond marker).
- Deep-link / scanner: `https://fib-time-price.onrender.com/?t=AAPL&tf=1d&tp=1`
  (`tp=1` turns the toggle on; open with `target=_blank`).

## Reusable Python module (scanner-ready)
Path: `fib_time_price/time_price_flag.py`

```python
from fib_time_price.time_price_flag import (
    Bars, FlagParams, find_time_price_flags, flags_active_now, chart_url, summarize_past_year
)
# bars = Bars.from_dict(api_history_json, ticker="SPX")
# flags = flags_active_now(bars)   # after each daily close, over a universe
# link = chart_url("AAPL")         # .../?t=AAPL&tf=1d&tp=1
```

Do **not** build the scanner in this preview branch — only the shared flag logic + UI.
Future scanner should list ticker (as that chart_url link), low/high, window dates,
zone range, distance to zone, and cluster strength.

## Scanner link contract (future)
Each ticker in the scanner list must be an `<a target="_blank" rel="noopener" href="...">` using `chart_url(ticker)` → `https://fib-time-price.onrender.com/?t=<TICKER>&tf=1d&tp=1` so Time+Price opens on.
