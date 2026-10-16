# Data sources

* **Primary: Financial Modeling Prep** (`FMP_API_KEY` env var; never commit it).
  * Daily: `stable/historical-price-eod/full` (split-adjusted, dividend-unadjusted = raw, like Dynamic Trader). Weekly bars are resampled from daily (Monday-labelled, same as Yahoo).
  * Intraday: `stable/historical-chart/{15min,30min,1hour}`. FMP returns newest-first with a per-call cap, so the server fetches fixed epoch-aligned calendar chunks (15m: 30d, 30m: 25d, 60m: 80d) in parallel, pages backwards inside a chunk if truncated, and caches past chunks for 6 h (live chunk 60 s). Times are US/Eastern; stocks/indices keep 9:30–16:00 only, futures keep the full Globex session, crypto is converted to UTC.
  * Max intraday lookback: `MAX_15M` (default `1y`), `MAX_30M` (`2y`), `MAX_60M` (`3y`).
  * Symbols: Yahoo-style aliases are kept (SPX→^GSPC, ES→ES=F …); futures map to FMP continuous symbols (ES=F→ESUSD, NQ=F→NQUSD, …), crypto BTC-USD→BTCUSD.
* **Fallback: Yahoo Finance (yfinance)** when no key is set, FMP errors, or FMP has no data for the symbol. Yahoo limits: 15m/30m ≈ 60 days, 60m ≈ 730 days (longer requests are clamped).
* `DATA_SOURCE=auto|fmp|yahoo` (default `auto`). `/api/history` and `/api/pivots` report `"source"`; the status bar and chart footer show it.
