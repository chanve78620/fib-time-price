#!/usr/bin/env python3
"""Emit compact WriteCanvas source from scanner/out/latest.json → canvas_contents.tsx."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"

def main() -> int:
    data = json.loads((OUT / "latest.json").read_text())
    slim = []
    for r in data["rows"]:
        ed = r.get("earnings_date")
        et = r.get("earnings_timing")
        earn_label = None
        if ed:
            earn_label = ed[5:] if len(ed) >= 10 else ed  # MM-DD
            if et:
                earn_label = f"{earn_label} {et}"
        slim.append({
            "t": r["ticker"],
            "k": "l" if r["kind"] == "low" else "h",
            "s": "n" if r["status"] == "now" else "u",
            "a": r["window_start"][5:] if len(r.get("window_start", "")) >= 10 else r["window_start"],
            "b": r["window_end"][5:] if len(r.get("window_end", "")) >= 10 else r["window_end"],
            "z": r["zone_label"],
            "c": round(r["last_close"], 2) if r["last_close"] < 1000 else round(r["last_close"], 1),
            "d": None if r["dist_to_zone_pct"] is None else round(r["dist_to_zone_pct"], 2),
            "p": round(r["strength"], 2),
            "h": None if r["hit_rate_1y"] is None else round(r["hit_rate_1y"], 2),
            "e": earn_label,  # MM-DD or MM-DD BMO/AMC
            "f": bool(r.get("earnings_flag")),
        })
    meta = {k: data[k] for k in ("scan_date", "universe_size", "n_now", "n_upcoming", "n_low", "n_high", "runtime_sec") if k in data}
    meta["scanned_at"] = (data.get("scanned_at") or "")[:19]
    meta["n_earnings_flag"] = data.get("n_earnings_flag") or sum(1 for r in data["rows"] if r.get("earnings_flag"))
    rows_js = json.dumps(slim, separators=(",", ":"))
    meta_js = json.dumps(meta, separators=(",", ":"))
    body = _TEMPLATE.replace("__ROWS__", rows_js).replace("__META__", meta_js)
    out = OUT / "canvas_contents.tsx"
    out.write_text(body)
    (OUT / "canvas_meta.json").write_text(json.dumps(meta, indent=2))
    print(out)
    return 0

_TEMPLATE = r'''import { Page, Section, Text, Table, Metrics, Segmented, Callout, useState, useMemo } from "grok/canvas";

type Kind = "all" | "low" | "high";
type Status = "all" | "now" | "upcoming";
type SortKey = "strength" | "ticker" | "dist" | "hit";
type R = { t: string; k: string; s: string; a: string; b: string; z: string; c: number; d: number | null; p: number; h: number | null; e: string | null; f: boolean };

const ROWS: R[] = __ROWS__;
const META = __META__ as { scan_date: string; universe_size: number; n_now: number; n_upcoming: number; n_low: number; n_high: number; runtime_sec?: number; scanned_at?: string; n_earnings_flag?: number };

const url = (t: string) => "https://fib-time-price.onrender.com/?t=" + t + "&tf=1d&tp=1";
function pct(x: number | null): string { if (x == null || Number.isNaN(x)) return "—"; return (x * 100).toFixed(0) + "%"; }
function dist(x: number | null): string { if (x == null || Number.isNaN(x)) return "—"; return (x >= 0 ? "+" : "") + x.toFixed(2) + "%"; }
function kind(k: string): string { return k === "l" || k === "low" ? "LOW" : "HIGH"; }
function statusOf(s: string): string { return s === "n" || s === "now" ? "now" : "upcoming"; }

/** Red ticker link when earnings_flag; TableCell ReactNode. */
function tickerLink(t: string, flagged: boolean) {
  return (
    <a
      href={url(t)}
      target="_blank"
      rel="noopener noreferrer"
      style={flagged ? { color: "#c5221f", fontWeight: 700 } : undefined}
    >
      {t}
    </a>
  );
}

function cell(text: string, flagged: boolean) {
  return flagged ? { text, tone: "danger" as const } : text;
}

export default function App() {
  const [status, setStatus] = useState<Status>("all");
  const [kindF, setKindF] = useState<Kind>("all");
  const [sort, setSort] = useState<SortKey>("strength");
  const filtered = useMemo(() => {
    let r = ROWS.slice();
    if (status !== "all") r = r.filter((x) => statusOf(x.s) === status);
    if (kindF !== "all") r = r.filter((x) => kind(x.k).toLowerCase() === kindF);
    r.sort((a, b) => {
      if (sort === "ticker") return a.t.localeCompare(b.t);
      if (sort === "dist") return Math.abs(a.d ?? 99) - Math.abs(b.d ?? 99);
      if (sort === "hit") return (b.h ?? -1) - (a.h ?? -1);
      return (b.p ?? 0) - (a.p ?? 0);
    });
    return r;
  }, [status, kindF, sort]);
  const nowRows = filtered.filter((x) => statusOf(x.s) === "now");
  const upRows = filtered.filter((x) => statusOf(x.s) === "upcoming");
  const cols = ["Ticker", "Turn", "Window", "Zone", "Close", "Dist %", "Strength", "1Y hit", "Earnings"];
  const cells = (x: R) => {
    const f = !!x.f;
    return [
      tickerLink(x.t, f),
      cell(kind(x.k), f),
      cell(x.a + " → " + x.b, f),
      cell(x.z, f),
      cell(String(x.c), f),
      cell(dist(x.d), f),
      cell(Math.round((x.p ?? 0) * 100) + "%", f),
      cell(pct(x.h), f),
      cell(x.e ?? "—", f),
    ];
  };
  return (
    <Page title="Time + Price Scanner" width="wide" summary={`Daily Boroden-style royal setups (DTP ≥90% into a Fib zone). Scan ${META.scan_date} · ${META.universe_size} tickers. RED rows have earnings on a window day or the next trading day.`}>
      <Callout tone="warning" lead="Earnings in red">A pick is shown in red when FMP lists earnings on any calendar day of its time window, or on the trading day after the window ends. Earnings column shows the date (and BMO/AMC when FMP provides timing).</Callout>
      <Metrics metrics={[{ value: String(META.n_now), label: "In window now" }, { value: String(META.n_upcoming), label: "Upcoming (≤3d)" }, { value: String(META.n_low), label: "Possible LOWs" }, { value: String(META.n_earnings_flag ?? 0), label: "Earnings flagged" }]} />
      <Section heading="Filters">
        <Text>{`Scan ${META.scanned_at ?? META.scan_date}${META.runtime_sec != null ? ` · ${META.runtime_sec}s` : ""}. Showing ${filtered.length}/${ROWS.length}.`}</Text>
        <Segmented<Status> value={status} onChange={setStatus} options={[{ value: "all", label: "All", count: ROWS.length }, { value: "now", label: "In window now", count: META.n_now }, { value: "upcoming", label: "Upcoming", count: META.n_upcoming }]} />
        <Segmented<Kind> value={kindF} onChange={setKindF} options={[{ value: "all", label: "LOW + HIGH" }, { value: "low", label: "LOW only", count: META.n_low }, { value: "high", label: "HIGH only", count: META.n_high }]} />
        <Segmented<SortKey> value={sort} onChange={setSort} options={[{ value: "strength", label: "Sort: strength" }, { value: "ticker", label: "Sort: ticker" }, { value: "dist", label: "Sort: |dist|" }, { value: "hit", label: "Sort: 1Y hit" }]} />
      </Section>
      {nowRows.length > 0 ? (
        <Section heading="In window now" caption="Top-decile timing cluster (±Band) with Fib zone confluence. Red = earnings risk.">
          <Table columns={cols} rows={nowRows.map(cells)} align={["start", "start", "start", "start", "end", "end", "end", "end", "start"]} />
        </Section>
      ) : null}
      {upRows.length > 0 ? (
        <Section heading="Upcoming (within 3 trading days)" caption="Strong DTP peak ahead; watch the listed zone. Red = earnings risk.">
          <Table columns={cols} rows={upRows.map(cells)} align={["start", "start", "start", "start", "end", "end", "end", "end", "start"]} />
        </Section>
      ) : null}
      {filtered.length === 0 ? (
        <Section heading="No matches"><Text>No tickers matched the current filters for this scan date.</Text></Section>
      ) : null}
      <Section heading="Refresh">
        <Text>{`cd /workspace/fib-time-price && .venv/bin/python scanner/scan.py && .venv/bin/python scanner/render_canvas.py then ask Grok Bot to update this Page (same canvas id). Charts: https://fib-time-price.onrender.com/?t=TICKER&tf=1d&tp=1`}</Text>
      </Section>
    </Page>
  );
}
'''

if __name__ == "__main__":
    raise SystemExit(main())
