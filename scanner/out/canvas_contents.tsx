import { Page, Section, Text, Table, Metrics, Segmented, Callout, useState, useMemo } from "grok/canvas";

type Kind = "all" | "low" | "high";
type Status = "all" | "now" | "upcoming";
type SortKey = "strength" | "ticker" | "dist" | "hit";
type R = { t: string; k: string; s: string; a: string; b: string; z: string; c: number; d: number | null; p: number; h: number | null };

const ROWS: R[] = [{"t":"AES","k":"h","s":"n","a":"10-26","b":"10-27","z":"15.04-15.07","c":15.03,"d":-0.18,"p":1.0,"h":0.43},{"t":"DLR","k":"h","s":"n","a":"10-23","b":"10-23","z":"178.21-178.25","c":179.01,"d":0.44,"p":1.0,"h":1.0},{"t":"DOC","k":"h","s":"n","a":"10-27","b":"10-27","z":"19.62","c":19.02,"d":-3.03,"p":1.0,"h":0.5},{"t":"FRT","k":"h","s":"n","a":"10-23","b":"10-23","z":"109.90-110.14","c":109.67,"d":-0.32,"p":1.0,"h":0.0},{"t":"GS","k":"h","s":"n","a":"10-23","b":"10-26","z":"913.39-915.60","c":911.77,"d":-0.3,"p":1.0,"h":0.0},{"t":"GWW","k":"h","s":"n","a":"10-27","b":"10-27","z":"1372-1373","c":1342.7,"d":-2.17,"p":1.0,"h":0.6},{"t":"HBAN","k":"h","s":"n","a":"10-23","b":"10-23","z":"15.90-15.92","c":15.71,"d":-1.28,"p":1.0,"h":0.0},{"t":"ITW","k":"h","s":"n","a":"10-27","b":"10-27","z":"280.78-280.94","c":275.93,"d":-1.76,"p":1.0,"h":0.43},{"t":"MAA","k":"h","s":"n","a":"10-23","b":"10-23","z":"122.08-122.27","c":118.75,"d":-2.81,"p":1.0,"h":0.6},{"t":"NUE","k":"h","s":"n","a":"10-23","b":"10-23","z":"275.39-275.88","c":270.79,"d":-1.76,"p":1.0,"h":0.33},{"t":"PNC","k":"h","s":"n","a":"10-23","b":"10-23","z":"227.73-228.03","c":227.54,"d":-0.15,"p":1.0,"h":0.17},{"t":"QCOM","k":"h","s":"n","a":"10-23","b":"10-26","z":"184.03-184.33","c":184.17,"d":-0.0,"p":1.0,"h":0.0},{"t":"RL","k":"h","s":"n","a":"10-27","b":"10-27","z":"393.49-394.01","c":391.25,"d":-0.64,"p":1.0,"h":0.0},{"t":"SW","k":"h","s":"n","a":"10-27","b":"10-27","z":"42.78-42.87","c":42.54,"d":-0.68,"p":1.0,"h":0.0},{"t":"TFC","k":"h","s":"n","a":"10-23","b":"10-26","z":"49.28-49.30","c":48.54,"d":-1.52,"p":1.0,"h":0.0},{"t":"TRGP","k":"h","s":"n","a":"10-26","b":"10-26","z":"306.66-306.90","c":302.61,"d":-1.36,"p":1.0,"h":0.0},{"t":"URI","k":"h","s":"n","a":"10-22","b":"10-23","z":"1150","c":1162.0,"d":1.01,"p":1.0,"h":0.33},{"t":"BA","k":"l","s":"n","a":"10-26","b":"10-26","z":"180.50-180.69","c":168.18,"d":-6.87,"p":1.0,"h":0.25},{"t":"BF-B","k":"l","s":"n","a":"10-27","b":"10-27","z":"28.39-28.42","c":28.51,"d":0.36,"p":1.0,"h":0.5},{"t":"SPX","k":"l","s":"n","a":"10-27","b":"10-27","z":"7603-7609","c":7722.6,"d":1.54,"p":1.0,"h":0.55},{"t":"SPY","k":"l","s":"n","a":"10-27","b":"10-27","z":"756.45-758.09","c":769.66,"d":1.64,"p":1.0,"h":0.44},{"t":"AMP","k":"h","s":"u","a":"10-28","b":"10-28","z":"504.46-504.70","c":492.85,"d":-2.33,"p":1.0,"h":1.0},{"t":"BKR","k":"h","s":"u","a":"10-30","b":"10-30","z":"59.75-59.87","c":59.0,"d":-1.35,"p":1.0,"h":0.33},{"t":"CSX","k":"h","s":"u","a":"10-28","b":"10-29","z":"55.97-56.08","c":52.27,"d":-6.71,"p":1.0,"h":0.0},{"t":"DOC","k":"h","s":"u","a":"10-28","b":"10-29","z":"19.62","c":19.02,"d":-3.03,"p":1.0,"h":0.5},{"t":"DVA","k":"h","s":"u","a":"10-30","b":"10-30","z":"193.82-194.26","c":181.69,"d":-6.36,"p":1.0,"h":0.33},{"t":"EXE","k":"h","s":"u","a":"10-29","b":"10-30","z":"96.90-96.96","c":94.62,"d":-2.38,"p":1.0,"h":1.0},{"t":"FERG","k":"h","s":"u","a":"10-28","b":"10-29","z":"238.83-238.96","c":229.56,"d":-3.91,"p":1.0,"h":1.0},{"t":"GEHC","k":"h","s":"u","a":"10-28","b":"10-28","z":"72.80-72.94","c":71.11,"d":-2.42,"p":1.0,"h":0.5},{"t":"LULU","k":"h","s":"u","a":"10-28","b":"10-29","z":"106.40-106.47","c":104.59,"d":-1.74,"p":1.0,"h":1.0},{"t":"LVS","k":"h","s":"u","a":"10-28","b":"10-29","z":"40.78-40.79","c":36.12,"d":-11.44,"p":1.0,"h":1.0},{"t":"MCO","k":"h","s":"u","a":"10-30","b":"11-02","z":"504.48-505.06","c":474.0,"d":-6.09,"p":1.0,"h":0.5},{"t":"MTB","k":"h","s":"u","a":"10-28","b":"10-29","z":"226.19-226.50","c":221.31,"d":-2.23,"p":1.0,"h":0.4},{"t":"NEE","k":"h","s":"u","a":"10-28","b":"10-28","z":"84.66-84.78","c":82.42,"d":-2.71,"p":1.0,"h":0.0},{"t":"PFG","k":"h","s":"u","a":"10-28","b":"10-28","z":"114.10-114.31","c":111.98,"d":-1.95,"p":1.0,"h":0.4},{"t":"REG","k":"h","s":"u","a":"10-28","b":"10-28","z":"75.22-75.36","c":74.28,"d":-1.34,"p":1.0,"h":0.83},{"t":"RL","k":"h","s":"u","a":"10-28","b":"10-29","z":"393.49-394.01","c":391.25,"d":-0.64,"p":1.0,"h":0.0},{"t":"ROL","k":"h","s":"u","a":"10-28","b":"10-28","z":"35.84-35.92","c":34.01,"d":-5.22,"p":1.0,"h":1.0},{"t":"SNA","k":"h","s":"u","a":"10-28","b":"10-28","z":"372.65-373.21","c":357.51,"d":-4.14,"p":1.0,"h":0.67},{"t":"SW","k":"h","s":"u","a":"10-28","b":"10-29","z":"42.78-42.87","c":42.54,"d":-0.68,"p":1.0,"h":0.0},{"t":"WFC","k":"h","s":"u","a":"10-28","b":"10-28","z":"86.55-86.68","c":82.66,"d":-4.57,"p":1.0,"h":0.67},{"t":"AFL","k":"l","s":"u","a":"10-30","b":"10-30","z":"119.25-119.37","c":121.99,"d":2.25,"p":1.0,"h":0.5},{"t":"AMZN","k":"l","s":"u","a":"10-28","b":"10-28","z":"243.86-244.05","c":253.1,"d":3.75,"p":1.0,"h":1.0},{"t":"ARKK","k":"l","s":"u","a":"10-28","b":"10-29","z":"78.41-78.56","c":84.78,"d":8.02,"p":1.0,"h":0.5},{"t":"BAX","k":"l","s":"u","a":"10-30","b":"11-02","z":"23.29-23.34","c":24.92,"d":6.88,"p":1.0,"h":1.0},{"t":"CHRW","k":"l","s":"u","a":"10-28","b":"10-29","z":"135.12-135.20","c":143.59,"d":6.24,"p":1.0,"h":null},{"t":"CRM","k":"l","s":"u","a":"10-30","b":"11-02","z":"236.08-236.35","c":240.89,"d":1.98,"p":1.0,"h":0.5},{"t":"DTE","k":"l","s":"u","a":"10-29","b":"10-29","z":"130.44-130.60","c":132.67,"d":1.65,"p":1.0,"h":0.67},{"t":"HUM","k":"l","s":"u","a":"10-29","b":"10-29","z":"405.66-406.66","c":414.85,"d":2.14,"p":1.0,"h":null},{"t":"JBHT","k":"l","s":"u","a":"10-29","b":"10-30","z":"219.54-219.72","c":231.95,"d":5.61,"p":1.0,"h":0.5},{"t":"PLTR","k":"l","s":"u","a":"10-28","b":"10-29","z":"183.03-183.17","c":198.73,"d":8.54,"p":1.0,"h":1.0},{"t":"PPL","k":"l","s":"u","a":"10-30","b":"10-30","z":"33.85-33.91","c":35.18,"d":3.83,"p":1.0,"h":0.75},{"t":"QQQ","k":"l","s":"u","a":"10-28","b":"10-28","z":"694.43-694.45","c":721.25,"d":3.86,"p":1.0,"h":0.8},{"t":"SMCI","k":"l","s":"u","a":"10-30","b":"11-02","z":"26.87-26.88","c":35.09,"d":30.55,"p":1.0,"h":0.0},{"t":"SOLV","k":"l","s":"u","a":"10-29","b":"10-29","z":"81.09-81.27","c":82.98,"d":2.21,"p":1.0,"h":0.0},{"t":"SPX","k":"l","s":"u","a":"10-28","b":"10-28","z":"7580-7596","c":7722.6,"d":1.78,"p":1.0,"h":0.55},{"t":"SPY","k":"l","s":"u","a":"10-28","b":"10-28","z":"756.45-758.09","c":769.66,"d":1.64,"p":1.0,"h":0.44},{"t":"STLD","k":"l","s":"u","a":"10-30","b":"10-30","z":"230.26-230.51","c":246.8,"d":7.13,"p":1.0,"h":0.6},{"t":"VRSN","k":"l","s":"u","a":"10-28","b":"10-28","z":"288.65-289.13","c":304.04,"d":5.25,"p":1.0,"h":1.0}];
const META = {"scan_date":"2026-10-27","universe_size":540,"n_now":21,"n_upcoming":38,"n_low":22,"n_high":37,"runtime_sec":13.6,"scanned_at":"2026-10-27T17:21:47"} as { scan_date: string; universe_size: number; n_now: number; n_upcoming: number; n_low: number; n_high: number; runtime_sec?: number; scanned_at?: string };

const url = (t: string) => "https://fib-time-price.onrender.com/?t=" + t + "&tf=1d&tp=1";
function pct(x: number | null): string { if (x == null || Number.isNaN(x)) return "—"; return (x * 100).toFixed(0) + "%"; }
function dist(x: number | null): string { if (x == null || Number.isNaN(x)) return "—"; return (x >= 0 ? "+" : "") + x.toFixed(2) + "%"; }
function kind(k: string): string { return k === "l" || k === "low" ? "LOW" : "HIGH"; }
function statusOf(s: string): string { return s === "n" || s === "now" ? "now" : "upcoming"; }

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
  const cols = ["Ticker chart", "Turn", "Window", "Zone", "Close", "Dist %", "Strength", "1Y hit"];
  const cells = (x: R) => [x.t + "  " + url(x.t), kind(x.k), x.a + " → " + x.b, x.z, String(x.c), dist(x.d), Math.round((x.p ?? 0) * 100) + "%", pct(x.h)];
  return (
    <Page title="Time + Price Scanner" width="wide" summary={`Daily Boroden-style royal setups (DTP ≥90% into a Fib zone). Scan ${META.scan_date} · ${META.universe_size} tickers. Click a chart URL — opens with Time+Price on (?tp=1).`}>
      <Callout tone="info" lead="How to read this">In window now = time and price lined up on the latest bar (±Band). Upcoming = strong time cluster within the next 3 trading days. Each ticker cell links the live chart in a new tab.</Callout>
      <Metrics metrics={[{ value: String(META.n_now), label: "In window now" }, { value: String(META.n_upcoming), label: "Upcoming (≤3d)" }, { value: String(META.n_low), label: "Possible LOWs" }, { value: String(META.n_high), label: "Possible HIGHs" }]} />
      <Section heading="Filters">
        <Text>{`Scan ${META.scanned_at ?? META.scan_date}${META.runtime_sec != null ? ` · ${META.runtime_sec}s` : ""}. Showing ${filtered.length}/${ROWS.length}.`}</Text>
        <Segmented<Status> value={status} onChange={setStatus} options={[{ value: "all", label: "All", count: ROWS.length }, { value: "now", label: "In window now", count: META.n_now }, { value: "upcoming", label: "Upcoming", count: META.n_upcoming }]} />
        <Segmented<Kind> value={kindF} onChange={setKindF} options={[{ value: "all", label: "LOW + HIGH" }, { value: "low", label: "LOW only", count: META.n_low }, { value: "high", label: "HIGH only", count: META.n_high }]} />
        <Segmented<SortKey> value={sort} onChange={setSort} options={[{ value: "strength", label: "Sort: strength" }, { value: "ticker", label: "Sort: ticker" }, { value: "dist", label: "Sort: |dist|" }, { value: "hit", label: "Sort: 1Y hit" }]} />
      </Section>
      {nowRows.length > 0 ? (
        <Section heading="In window now" caption="Top-decile timing cluster (±Band) with Fib zone confluence.">
          <Table columns={cols} rows={nowRows.map(cells)} align={["start", "start", "start", "start", "end", "end", "end", "end"]} />
        </Section>
      ) : null}
      {upRows.length > 0 ? (
        <Section heading="Upcoming (within 3 trading days)" caption="Strong DTP peak ahead; watch the listed zone.">
          <Table columns={cols} rows={upRows.map(cells)} align={["start", "start", "start", "start", "end", "end", "end", "end"]} />
        </Section>
      ) : null}
      {filtered.length === 0 ? (
        <Section heading="No matches"><Text>No tickers matched the current filters for this scan date.</Text></Section>
      ) : null}
      <Section heading="Refresh">
        <Text>`cd /workspace/fib-time-price && .venv/bin/python scanner/scan.py && .venv/bin/python scanner/render_canvas.py` then ask Grok Bot to update this Page (same canvas id). Charts: https://fib-time-price.onrender.com/?t=TICKER&tf=1d&tp=1</Text>
      </Section>
    </Page>
  );
}
