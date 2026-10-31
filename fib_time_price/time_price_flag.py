"""Carolyn Boroden–style TIME + PRICE ('royal') confluence flags.

A flag fires when a strong walk-forward DTP timing cluster (normalized
strength >= ``min_strength``, default 0.9 / top-decile) coincides with
price trading into an active Fib confluence zone:

* LOW timing  + support zone  (bar low/high overlaps zone; zone below mid)
* HIGH timing + resistance zone (same; zone above mid)

Past flags use walk-forward DTP (no lookahead on pivots: a swing-N pivot
at bar i is known only once bar i+N has closed). Zones for a past window
use only levels whose anchor pivot index <= window start (no future
anchors). Outcome: whether a confirmed pivot of matching kind formed
within ±band bars of the time window.

Future / upcoming flags: live DTP peaks (xi >= n-1) with strength >=
threshold that sit over an active zone the market has not yet traded
through — watch boxes for the scanner.

This module is scanner-ready. A future daily scanner can call
``flags_active_now`` over a universe and link each hit with ``chart_url``.

Chart deep-link (Time+Price on)::

    https://fib-time-price.onrender.com/?t=AAPL&tf=1d&tp=1&bars=40
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Literal, Sequence

Kind = Literal["low", "high"]

SITE_BASE = "https://fib-time-price.onrender.com"

RET_R = (0.382, 0.5, 0.618, 0.786)
EX_R = (1.272, 1.618, 2.618)
APP_R = (1.0,)
DTP_TR = (0.382, 0.618, 1.0, 1.618, 2.618)
DTP_ATP = (0.382, 0.5, 0.618, 0.786, 1.0, 1.272, 1.618)
DTP_CC = (0.618, 1.0, 1.618)
DTP_CC_W = 0.5


@dataclass
class FlagParams:
    swing: int = 3
    depth: int = 5
    zone_tol_pct: float = 0.25  # Zone % of last close
    band: float = 2.0  # DTP triangular half-width (bars / cal days treated as bar index here)
    dtp_start: float = 6.5
    min_strength: float = 0.9  # top-decile / normalized peak threshold
    max_levels: int = 24
    app_all: bool = False
    # For scanner deep-links
    site_base: str = SITE_BASE


@dataclass
class TimePriceFlag:
    ticker: str
    kind: Kind  # "low" or "high"
    i0: int  # first bar of strong time cluster
    i1: int  # last bar of strong time cluster
    peak_i: int  # strongest bar in cluster
    peak_strength: float  # 0..1
    date0: str
    date1: str
    peak_date: str
    zone_lo: float
    zone_hi: float
    zone_n: int
    zone_label: str
    future: bool  # True = upcoming / watch (price may not be in zone yet)
    # Past only:
    outcome_pivot: bool | None = None  # True if matching pivot within ±band of window
    outcome_pivot_i: int | None = None
    outcome_pivot_date: str | None = None
    # Distance of last close (or peak bar mid) to zone mid, in price units
    dist_to_zone: float | None = None
    in_zone_now: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def chart_url(
    ticker: str,
    *,
    tf: str = "1d",
    asof: str | None = None,
    tp: bool = True,
    bars: int | None = 40,
    base: str = SITE_BASE,
) -> str:
    """Deep-link that opens the site chart with Time+Price toggle on (``tp=1``).

    ``bars`` zooms the chart to the last N candles (``?bars=40``). Pass
    ``bars=None`` to leave the default zoom. Scanner rows should use
    ``target=_blank`` on this URL.
    """
    t = ticker.upper().lstrip("$")
    parts = [f"t={t}", f"tf={tf}"]
    if tp:
        parts.append("tp=1")
    if bars is not None and bars > 0:
        parts.append(f"bars={int(bars)}")
    if asof:
        parts.append(f"asof={asof}")
    return f"{base.rstrip('/')}/?{'&'.join(parts)}"


# ---- OHLC helpers -----------------------------------------------------------


def _arr(xs: Sequence[float]) -> list[float]:
    return [float(x) for x in xs]


@dataclass
class Bars:
    ticker: str
    dates: list[str]
    o: list[float]
    h: list[float]
    l: list[float]
    c: list[float]

    @property
    def n(self) -> int:
        return len(self.dates)

    @classmethod
    def from_dict(cls, d: dict[str, Any], ticker: str | None = None) -> "Bars":
        dates = [str(x)[:10] if len(str(x)) >= 10 else str(x) for x in d["dates"]]
        n = len(dates)
        opens = d.get("opens") or d.get("o") or d["closes"]
        return cls(
            ticker=(ticker or d.get("ticker") or "").upper(),
            dates=dates,
            o=_arr(opens)[:n],
            h=_arr(d.get("highs") or d["h"])[:n],
            l=_arr(d.get("lows") or d["l"])[:n],
            c=_arr(d.get("closes") or d["c"])[:n],
        )


# ---- pivots (mirrors index.html detectPivots) --------------------------------


@dataclass
class Pivot:
    i: int
    kind: Kind
    price: float
    date: str = ""
    tent: bool = False
    chg: float | None = None
    tb: int | None = None


def detect_pivots(bars: Bars, swing: int = 3) -> list[Pivot]:
    N = max(1, int(swing))
    h, l, n = bars.h, bars.l, bars.n
    raw: list[Pivot] = []
    for i in range(N, n - N):
        is_h = is_l = True
        for k in range(i - N, i + N + 1):
            if h[k] > h[i]:
                is_h = False
            if l[k] < l[i]:
                is_l = False
            if not is_h and not is_l:
                break
        if is_h:
            raw.append(Pivot(i=i, kind="high", price=h[i]))
        if is_l:
            raw.append(Pivot(i=i, kind="low", price=l[i]))
    out: list[Pivot] = []
    j = 0
    while j < len(raw):
        p = raw[j]
        if j + 1 < len(raw) and raw[j + 1].i == p.i and out and out[-1].kind == p.kind:
            raw[j + 1], p = p, raw[j + 1]
        prev = out[-1] if out else None
        if prev and prev.kind == p.kind:
            if (p.kind == "high" and p.price > prev.price) or (
                p.kind == "low" and p.price < prev.price
            ):
                out[-1] = p
            j += 1
            continue
        if prev and prev.i == p.i and prev.kind != p.kind:
            out.append(p)
            j += 1
            continue
        out.append(p)
        j += 1
    # zigzag refine
    for j in range(len(out)):
        a = out[j - 1].i + 1 if j > 0 else 0
        b = out[j + 1].i - 1 if j + 1 < len(out) else out[j].i
        best = out[j]
        for k in range(a, b + 1):
            if best.kind == "low":
                if l[k] < best.price:
                    best = Pivot(i=k, kind="low", price=l[k])
            else:
                if h[k] > best.price:
                    best = Pivot(i=k, kind="high", price=h[k])
        out[j] = best
    # tentative tail
    if out:
        last = Pivot(**{**out[-1].__dict__})
        cand = None
        extended = False
        for k in range(last.i + 1, n):
            if last.kind == "high":
                if h[k] > last.price:
                    last = Pivot(i=k, kind="high", price=h[k], tent=True)
                    cand = None
                    extended = True
                    continue
                if cand is None or l[k] < cand.price:
                    cand = Pivot(i=k, kind="low", price=l[k], tent=True)
            else:
                if l[k] < last.price:
                    last = Pivot(i=k, kind="low", price=l[k], tent=True)
                    cand = None
                    extended = True
                    continue
                if cand is None or h[k] > cand.price:
                    cand = Pivot(i=k, kind="high", price=h[k], tent=True)
        out[-1] = last
        if cand and not extended:
            out.append(cand)
    for j, p in enumerate(out):
        q = out[j - 1] if j else None
        p.date = bars.dates[p.i]
        p.chg = (p.price - q.price) if q else None
        p.tb = (p.i - q.i) if q else None
    return out


# ---- levels & zones ---------------------------------------------------------


@dataclass
class Level:
    price: float
    type: str
    r: float
    anchor_i: int
    start: int
    hit: bool = False
    held: bool = False


def _level_hit(bars: Bars, anchor_i: int, anchor_price: float, lvl: float) -> bool:
    c = bars.c[anchor_i]
    if lvl >= min(c, anchor_price) and lvl <= max(c, anchor_price) and lvl != anchor_price:
        return True
    for j in range(anchor_i + 1, bars.n):
        if bars.l[j] <= lvl <= bars.h[j]:
            return True
        if j > 0 and (
            (bars.h[j - 1] < lvl and bars.l[j] > lvl)
            or (bars.l[j - 1] > lvl and bars.h[j] < lvl)
        ):
            return True
    return False


def compute_levels(
    bars: Bars, pivots: list[Pivot], params: FlagParams
) -> list[Level]:
    out: list[Level] = []
    last = len(pivots) - 1
    if last < 1:
        return out
    depth = params.depth
    min_start = pivots[max(0, last - 1)].i
    app_rs = (0.618, 1.0, 1.618) if params.app_all else APP_R

    def add(price: float, typ: str, r: float, anchor: Pivot) -> None:
        if price <= 0:
            return
        hit = _level_hit(bars, anchor.i, anchor.price, price)
        out.append(
            Level(
                price=price,
                type=typ,
                r=r,
                anchor_i=anchor.i,
                start=max(anchor.i, min(min_start, anchor.i)),
                hit=hit,
            )
        )

    for e in range(last, max(0, last - depth) - 1, -1):
        if e < 1:
            break
        E = pivots[e]
        used = 0
        s = e - 1
        while s >= 0 and s >= e - 7 and used < 3:
            S = pivots[s]
            ok, break_out = True, False
            for k in range(s, e + 1):
                q = pivots[k]
                if q.kind == E.kind and (
                    (E.kind == "high" and q.price > E.price)
                    or (E.kind == "low" and q.price < E.price)
                ):
                    ok = False
                    break_out = True
                    break
                if q.kind == S.kind and (
                    (S.kind == "low" and q.price < S.price)
                    or (S.kind == "high" and q.price > S.price)
                ):
                    ok = False
            if break_out:
                break
            if ok:
                used += 1
                rng = S.price - E.price
                for r in RET_R:
                    add(E.price + r * rng, "Ret", r, E)
                for r in EX_R:
                    add(E.price + r * rng, "EX", r, E)
            s -= 2

    for c in range(last, max(1, last - depth) - 1, -1):
        if c < 2:
            break
        C = pivots[c]
        for a, b in ((c - 2, c - 1), (c - 4, c - 3)):
            if a < 0:
                continue
            A, B = pivots[a], pivots[b]
            length = B.price - A.price
            for r in app_rs:
                add(C.price + r * length, "App", r, C)

    out.sort(key=lambda v: v.price)
    # nearest max_levels to last close among unhit
    active = [v for v in out if not v.hit]
    if len(active) > params.max_levels:
        ref = bars.c[-1]
        active = sorted(active, key=lambda v: abs(v.price - ref))[: params.max_levels]
        active.sort(key=lambda v: v.price)
    return active


@dataclass
class Zone:
    lo: float
    hi: float
    n: int
    start: int
    label: str


def zone_label(lo: float, hi: float) -> str:
    d = 0 if abs(hi) >= 1000 else 2
    a, b = f"{lo:.{d}f}", f"{hi:.{d}f}"
    if a == b:
        return a
    return f"{a}-{b}"


def compute_zones(levels: list[Level], ref_price: float, tol_pct: float) -> list[Zone]:
    span = (tol_pct / 100.0) * ref_price
    s = sorted(levels, key=lambda v: v.price)
    zones: list[Zone] = []
    cur: list[Level] = []
    for v in s:
        if cur and v.price - cur[0].price > span:
            if len(cur) >= 2:
                zones.append(
                    Zone(
                        lo=cur[0].price,
                        hi=cur[-1].price,
                        n=len(cur),
                        start=min(x.start for x in cur),
                        label=zone_label(cur[0].price, cur[-1].price),
                    )
                )
            cur = []
        cur.append(v)
    if len(cur) >= 2:
        zones.append(
            Zone(
                lo=cur[0].price,
                hi=cur[-1].price,
                n=len(cur),
                start=min(x.start for x in cur),
                label=zone_label(cur[0].price, cur[-1].price),
            )
        )
    return zones


# ---- DTP walk-forward (bar-index units; matches hist top-decile) -------------


def _opp(k: Kind) -> Kind:
    return "high" if k == "low" else "low"


def _dtp_projections(
    kind: Kind, pivots: list[Pivot], dtp_start: float
) -> tuple[Pivot, list[tuple[float, float]]] | None:
    """Return (anchor, [(x_bar_index, weight), ...]) for confirmed pivots only."""
    conf = [p for p in pivots if not p.tent]
    same = [p for p in conf if p.kind == kind]
    if len(same) < 2:
        return None
    H = same[-1]
    proj: list[tuple[float, float]] = []
    # time retracements / extensions of prior opposite→H swings
    for S in conf:
        if S.i >= H.i or S.kind == kind:
            continue
        dur = H.i - S.i
        if dur < dtp_start:
            continue
        for r in DTP_TR:
            proj.append((H.i + r * dur, 1.0))
    # ATP: A→B duration from H
    for j in range(len(conf) - 1):
        A, B = conf[j], conf[j + 1]
        if B.i >= H.i:
            break
        dur = B.i - A.i
        if dur >= 2:
            for r in DTP_ATP:
                x = H.i + r * dur
                if x - H.i >= dtp_start:
                    proj.append((x, 1.0))
    # crest-crest / trough-trough
    for j in range(1, len(same)):
        dur = same[j].i - same[j - 1].i
        if dur < 1:
            continue
        for r in DTP_CC:
            x = H.i + r * dur
            if x - H.i >= dtp_start:
                proj.append((x, DTP_CC_W))
    return H, proj


def walk_forward_dtp(
    bars: Bars,
    pivots: list[Pivot],
    params: FlagParams,
    kinds: Sequence[Kind] | None = None,
) -> dict[Kind, list[float]]:
    """Per-bar normalized DTP strength in [0,1], walk-forward, no lookahead.

    A swing-N pivot at bar i is known only once bar i+N has closed.
    """
    N = max(1, params.swing)
    bwid = max(0.3, params.band)
    n = bars.n
    if kinds is None:
        last = pivots[-1] if pivots else None
        if last is None:
            kinds = ("low",)
        else:
            tgt: Kind = last.kind if last.tent else _opp(last.kind)  # type: ignore[assignment]
            kinds = (tgt,)

    cands = sorted(
        [
            {**p.__dict__, "confAt": p.i + N}
            for p in pivots
            if not p.tent and p.i + N < n
        ],
        key=lambda x: (x["confAt"], x["i"]),
    )

    raw: dict[Kind, list[float]] = {K: [0.0] * n for K in kinds}
    conf: list[Pivot] = []
    ei = 0
    active_proj: dict[Kind, list[tuple[float, float]] | None] = {K: None for K in kinds}
    active_anchor: dict[Kind, int] = {K: -1 for K in kinds}
    # epoch normalization: collect weights then normalize by epoch max
    epoch_vals: dict[Kind, dict[int, float]] = {K: {} for K in kinds}
    epoch_max: dict[Kind, float] = {K: 0.0 for K in kinds}
    epoch_anchor: dict[Kind, int] = {K: -1 for K in kinds}

    def flush(K: Kind) -> None:
        mx = epoch_max[K]
        if mx > 0:
            for t, v in epoch_vals[K].items():
                if v >= 0.01 * mx:
                    raw[K][t] = max(raw[K][t], v / mx)
        epoch_vals[K] = {}
        epoch_max[K] = 0.0

    for t in range(n):
        changed = False
        while ei < len(cands) and cands[ei]["confAt"] <= t:
            conf.append(
                Pivot(
                    i=cands[ei]["i"],
                    kind=cands[ei]["kind"],
                    price=cands[ei]["price"],
                    date=cands[ei]["date"],
                    tent=False,
                )
            )
            ei += 1
            changed = True
        if changed:
            for K in kinds:
                r = _dtp_projections(K, conf, params.dtp_start)
                new_h = r[0].i if r else -1
                if new_h != active_anchor[K]:
                    flush(K)
                    active_anchor[K] = new_h
                    active_proj[K] = r[1] if r else None
                    epoch_anchor[K] = new_h
        for K in kinds:
            proj = active_proj[K]
            if not proj or active_anchor[K] < 0 or t < active_anchor[K]:
                continue
            v = 0.0
            for x, w in proj:
                a = abs(t - x)
                if a < bwid:
                    v += w * (1 - a / bwid)
            if v > 0:
                epoch_vals[K][t] = v
                if v > epoch_max[K]:
                    epoch_max[K] = v
    for K in kinds:
        flush(K)
    return raw


def _live_dtp_future(
    bars: Bars,
    pivots: list[Pivot],
    params: FlagParams,
    kinds: Sequence[Kind],
    fut: int = 40,
) -> dict[Kind, list[tuple[int, float, str]]]:
    """Upcoming DTP peaks beyond last bar (and including last). Returns (xi, strength, date_hint)."""
    conf = [p for p in pivots if not p.tent]
    bwid = max(0.3, params.band)
    out: dict[Kind, list[tuple[int, float, str]]] = {K: [] for K in kinds}
    for K in kinds:
        r = _dtp_projections(K, conf, params.dtp_start)
        if not r:
            continue
        H, proj = r
        # evaluate on bars from H to n-1+fut
        weights = []
        for xi in range(H.i, bars.n + fut):
            v = 0.0
            for x, w in proj:
                a = abs(xi - x)
                if a < bwid:
                    v += w * (1 - a / bwid)
            weights.append((xi, v))
        max_w = max((v for _, v in weights), default=0.0)
        if max_w <= 0:
            continue
        for xi, v in weights:
            h = v / max_w
            if h >= params.min_strength:
                # synthetic future date label
                if xi < bars.n:
                    d = bars.dates[xi]
                else:
                    d = f"+{xi - bars.n + 1}b"
                out[K].append((xi, h, d))
    return out


# ---- flag detection ---------------------------------------------------------
def _bars_slice(bars: Bars, n: int) -> Bars:
    """First n bars only (as-of end of bar n-1)."""
    n = max(0, min(n, bars.n))
    return Bars(
        ticker=bars.ticker,
        dates=bars.dates[:n],
        o=bars.o[:n],
        h=bars.h[:n],
        l=bars.l[:n],
        c=bars.c[:n],
    )


def zones_asof(bars: Bars, params: FlagParams, asof_i: int) -> list[Zone]:
    """Zones knowable at bar asof_i (pivots confirmed, levels hit-tested only through asof_i)."""
    if asof_i < 10:
        return []
    sub = _bars_slice(bars, asof_i + 1)
    piv = detect_pivots(sub, params.swing)
    # drop tentative for zone building stability
    piv = [p for p in piv if not p.tent] or piv
    if len(piv) < 2:
        return []
    # temporarily raise max_levels so historical clusters aren't truncated to "near last close"
    p2 = FlagParams(**{**params.__dict__, "max_levels": max(params.max_levels, 48)})
    levels = compute_levels(sub, piv, p2)
    return compute_zones(levels, sub.c[-1], params.zone_tol_pct)





def _bar_overlaps_zone(bars: Bars, i: int, z: Zone) -> bool:
    return bars.l[i] <= z.hi and bars.h[i] >= z.lo


def _zone_role(z: Zone, mid: float, kind: Kind) -> bool:
    """Support for lows (zone at/below mid), resistance for highs (at/above mid)."""
    zmid = 0.5 * (z.lo + z.hi)
    if kind == "low":
        return zmid <= mid * 1.002  # allow slight above mid for tight clusters
    return zmid >= mid * 0.998


def _cluster_runs(
    strength: list[float], min_s: float, start_i: int = 0
) -> list[tuple[int, int, int, float]]:
    """Contiguous runs where strength >= min_s → (i0, i1, peak_i, peak_s)."""
    runs = []
    i = start_i
    n = len(strength)
    while i < n:
        if strength[i] < min_s:
            i += 1
            continue
        i0 = i
        peak_i, peak_s = i, strength[i]
        i += 1
        while i < n and strength[i] >= min_s:
            if strength[i] > peak_s:
                peak_i, peak_s = i, strength[i]
            i += 1
        runs.append((i0, i - 1, peak_i, peak_s))
    return runs


def find_time_price_flags(
    bars: Bars,
    params: FlagParams | None = None,
    *,
    include_future: bool = True,
    lookback_bars: int | None = None,
) -> list[TimePriceFlag]:
    """Detect past (walk-forward) and optional upcoming TIME+PRICE flags."""
    params = params or FlagParams()
    pivots = detect_pivots(bars, params.swing)
    if len(pivots) < 2:
        return []

    last_p = pivots[-1]
    target: Kind = last_p.kind if last_p.tent else _opp(last_p.kind)  # type: ignore[assignment]
    kinds: tuple[Kind, ...] = (target,) if target in ("low", "high") else ("low", "high")

    levels = compute_levels(bars, pivots, params)
    zones_now = compute_zones(levels, bars.c[-1], params.zone_tol_pct)
    hist = walk_forward_dtp(bars, pivots, params, kinds)

    start_i = 0
    if lookback_bars is not None and lookback_bars > 0:
        start_i = max(0, bars.n - lookback_bars)

    tol = max(1, int(round(params.band)))
    flags: list[TimePriceFlag] = []

    # confirmed pivots for outcome scoring
    conf_pivs = [p for p in pivots if not p.tent]

    for K in kinds:
        strength = hist[K]
        for i0, i1, peak_i, peak_s in _cluster_runs(strength, params.min_strength, start_i):
            if peak_i >= bars.n:
                continue
            # mid price over window for support/resistance role
            mid = 0.5 * (
                sum(bars.h[i] for i in range(i0, i1 + 1)) / (i1 - i0 + 1)
                + sum(bars.l[i] for i in range(i0, i1 + 1)) / (i1 - i0 + 1)
            )
            # zones as-of window end (no lookahead past i1)
            z_asof = zones_asof(bars, params, i1)
            cand_zones = [z for z in z_asof if z.start <= i0 and _zone_role(z, mid, K)]
            # Price check over timing window expanded by ±Band bars (definition)
            j0, j1 = max(0, i0 - tol), min(bars.n - 1, i1 + tol)
            hit_z = None
            for z in sorted(cand_zones, key=lambda z: -z.n):
                if any(_bar_overlaps_zone(bars, i, z) for i in range(j0, j1 + 1)):
                    hit_z = z
                    break
            # Near-miss: within 0.15% of zone edge (wick didn't quite tag)
            if hit_z is None and cand_zones:
                pad = abs(mid) * 0.0015
                for z in sorted(cand_zones, key=lambda z: -z.n):
                    for i in range(j0, j1 + 1):
                        if bars.l[i] <= z.hi + pad and bars.h[i] >= z.lo - pad:
                            hit_z = z
                            break
                    if hit_z:
                        break
            if hit_z is None:
                continue
            # outcome: matching pivot within ±band of window
            out_ok = False
            out_i = out_d = None
            for p in conf_pivs:
                if p.kind != K:
                    continue
                if p.i >= i0 - tol and p.i <= i1 + tol:
                    out_ok = True
                    out_i = p.i
                    out_d = p.date
                    break
            zmid = 0.5 * (hit_z.lo + hit_z.hi)
            last_c = bars.c[min(peak_i, bars.n - 1)]
            flags.append(
                TimePriceFlag(
                    ticker=bars.ticker,
                    kind=K,
                    i0=i0,
                    i1=i1,
                    peak_i=peak_i,
                    peak_strength=peak_s,
                    date0=bars.dates[i0],
                    date1=bars.dates[i1],
                    peak_date=bars.dates[peak_i],
                    zone_lo=hit_z.lo,
                    zone_hi=hit_z.hi,
                    zone_n=hit_z.n,
                    zone_label=hit_z.label,
                    future=False,
                    outcome_pivot=out_ok,
                    outcome_pivot_i=out_i,
                    outcome_pivot_date=out_d,
                    dist_to_zone=last_c - zmid,
                    in_zone_now=_bar_overlaps_zone(bars, bars.n - 1, hit_z)
                    if peak_i >= bars.n - 5
                    else _bar_overlaps_zone(bars, peak_i, hit_z),
                )
            )

    if include_future:
        fut = _live_dtp_future(bars, pivots, params, kinds)
        for K in kinds:
            # cluster future points
            pts = fut.get(K) or []
            if not pts:
                continue
            # group contiguous xi
            runs: list[list[tuple[int, float, str]]] = []
            for pt in pts:
                if not runs or pt[0] > runs[-1][-1][0] + 1:
                    runs.append([pt])
                else:
                    runs[-1].append(pt)
            mid = bars.c[-1]
            for run in runs:
                # only care about windows that touch 'now' or the future
                if run[-1][0] < bars.n - 1:
                    continue
                peak = max(run, key=lambda x: x[1])
                i0, i1 = run[0][0], run[-1][0]
                # prefer zones price is in or approaching for this kind
                cand = [z for z in zones_now if _zone_role(z, mid, K)]
                if not cand:
                    continue
                # pick nearest zone to last close
                z = min(cand, key=lambda z: abs(mid - 0.5 * (z.lo + z.hi)))
                in_zone = _bar_overlaps_zone(bars, bars.n - 1, z)
                # for future-only windows (fully ahead), still flag as watch if zone exists
                zmid = 0.5 * (z.lo + z.hi)
                d0 = bars.dates[i0] if i0 < bars.n else run[0][2]
                d1 = bars.dates[i1] if i1 < bars.n else run[-1][2]
                pd = bars.dates[peak[0]] if peak[0] < bars.n else peak[2]
                flags.append(
                    TimePriceFlag(
                        ticker=bars.ticker,
                        kind=K,
                        i0=i0,
                        i1=i1,
                        peak_i=peak[0],
                        peak_strength=peak[1],
                        date0=d0,
                        date1=d1,
                        peak_date=pd,
                        zone_lo=z.lo,
                        zone_hi=z.hi,
                        zone_n=z.n,
                        zone_label=z.label,
                        future=True,
                        outcome_pivot=None,
                        dist_to_zone=mid - zmid,
                        in_zone_now=in_zone,
                    )
                )

    # de-dupe overlapping past flags (same kind, overlapping windows, same zone)
    flags.sort(key=lambda f: (f.future, f.i0, -f.peak_strength))
    pruned: list[TimePriceFlag] = []
    for f in flags:
        if any(
            (not f.future and not g.future and f.kind == g.kind
             and not (f.i1 < g.i0 or f.i0 > g.i1)
             and abs(f.zone_lo - g.zone_lo) < 1e-6)
            for g in pruned
        ):
            continue
        pruned.append(f)
    return pruned


def flags_active_now(
    bars: Bars,
    params: FlagParams | None = None,
) -> list[TimePriceFlag]:
    """Scanner entry point: flags where the confluence window is active now
    (past cluster covering the last bar, or upcoming watch with price in/near zone).
    """
    params = params or FlagParams()
    all_f = find_time_price_flags(bars, params, include_future=True)
    n1 = bars.n - 1
    active = []
    for f in all_f:
        if f.future:
            # upcoming: include if window starts within ~band of now, or price already in zone
            if f.i0 <= n1 + max(1, int(round(params.band))) + 5 and (
                f.in_zone_now or abs(f.dist_to_zone or 0) <= (f.zone_hi - f.zone_lo) * 2
            ):
                active.append(f)
        else:
            if f.i0 <= n1 <= f.i1 + max(1, int(round(params.band))):
                active.append(f)
    return active


def summarize_past_year(
    bars: Bars, params: FlagParams | None = None
) -> dict[str, Any]:
    """Honest past-flag stats over ~1Y of bars (no fabrication)."""
    params = params or FlagParams()
    # ~252 trading days
    flags = find_time_price_flags(
        bars, params, include_future=False, lookback_bars=260
    )
    past = [f for f in flags if not f.future]
    hits = sum(1 for f in past if f.outcome_pivot)
    return {
        "ticker": bars.ticker,
        "n_flags": len(past),
        "n_with_pivot": hits,
        "n_without_pivot": len(past) - hits,
        "hit_rate": (hits / len(past)) if past else None,
        "flags": [f.to_dict() for f in past],
    }
