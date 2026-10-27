# Time + Price daily scanner

Scans **S&P 500 + Nasdaq 100 + major ETFs + SPX** for Carolyn Boroden–style **TIME + PRICE** confluence (walk-forward DTP strength ≥ 0.9 into a Fib zone).

## Page

- **Title:** Time + Price Scanner  
- **canvas_id:** `bf0e6b89-7903-4f36-a2b0-a4f0c4e52937`  
- **URL:** https://cursor.com/canvas/store-14b6a13c-f794-4d04-bcfe-d0893df95e28/bf0e6b89-7903-4f36-a2b0-a4f0c4e52937  

Update **that same Page** on each refresh (do not create a new one).

## Refresh (daily routine)

```bash
cd /workspace/fib-time-price
# FMP_API_KEY must be set
.venv/bin/python scanner/scan.py
.venv/bin/python scanner/render_canvas.py
```

Then ask Grok Bot: *update the Time + Price Scanner Page from `scanner/out/canvas_contents.tsx` using canvas_id `bf0e6b89-7903-4f36-a2b0-a4f0c4e52937`* (WriteCanvas with that id, or EditCanvas if only the data blob changed).

## Chart links

Every ticker opens in a **new tab**:

`https://fib-time-price.onrender.com/?t=<TICKER>&tf=1d&tp=1`

(`tp=1` forces the Time+Price toggle on after deploy of main.)

## Outputs

| Path | What |
|------|------|
| `scanner/out/YYYY-MM-DD.json` / `.csv` | Dated scan |
| `scanner/out/latest.json` / `latest.csv` | Always overwritten |
| `scanner/out/canvas_contents.tsx` | Source for the Page |
| `scanner/cache/bars/` | Per-ticker daily cache (same America/New_York date) |
| `scanner/cache/universe/` | Constituent cache (~24h) |

## Universe

- FMP `stable/sp500-constituent` + `stable/nasdaq-constituent` (cached; seed fallback if FMP fails)
- ETFs: SPY QQQ IWM DIA GLD SLV GDX GDXJ TLT XLE XLF XLK XLV XLI XLY XLP XLU XLB XLRE SMH ARKK
- Index: SPX (FMP `^GSPC`; chart link uses `t=SPX`)
