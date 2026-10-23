# TD Propulsion: rules used by the tool

## Levels (Perl, *DeMark Indicators*, 2008, ch. 6)
Up: R = Y − X, A = Z + r1·R (trigger), B = Z + r2·R (target), Full = Z + 1.0·R (optional).
Down mirrors it. r1/r2 = 0.236/0.472 (DeMark) or 0.25/0.50 (Bloomberg default per Perl).
Price basis: High/Low (default; X = low of the bottom bar, Y = high of the top bar, Z = low of
the pullback) or Close (the closes of those bars). The basis also decides whether the cancel, break,
target and full tests use intrabar extremes or closes.

## Breakout qualifiers for A (TD Line qualifiers; Perl p.123 applies them to Propulsion)
Upside (mirror for downside). A break qualifies if any of Q1 to Q3 holds:
- Q1: the prior bar is a down close, C[i−1] < C[i−2].
- Q2: the open is above the level and above the prior close, then trades at least 1 tick above the open.
- Q3: C[i−1] + (C[i−1] − trueLow[i−1]) < level, where trueLow = min(L[i−1], C[i−2]).
- Q4 (DeMark 1999 only, "new and optional"; reported, not counted): open > C[i−1] and open > C[i−2],
  level > H[i−1], and H[i] > open.

After the break the tool reports these cancellations as cautions only: the next open is back below
the level; the next open is below the break close and the next close is back below the level; the
next bar fails to exceed the break high.

Sources:
- T. & T.J. DeMark, "High-quality entries", *Futures*, Oct 1997.
- DeMark & DeMark, *DeMark on Day Trading Options* (1999), ch. 7.
- Perl (2008), p.122–123.
- Aspen Graphics DeMark help.

## Bloomberg calibration (GDXJ 30m, 10 days, Oct 2026)
Bloomberg's values: trigger 110.7613, exhaustion 113.2125, full propulsion 117.305, green dotted 109.6137.

| Level | Result | Status |
|---|---|---|
| Trigger A = Z + 0.25R | 110.76125 (X 103.675, Y 112.40, Z 108.58) | exact |
| Full = Z + 1.0R | 117.305 | exact |
| Exhaustion B | = **108.85 + 0.5R**; 108.85 is the low of the bar *before* the Z bar (Oct 16 14:00; the running lowest low since Y at that bar, the Z bar's own low is 108.58) | exact to 4 dp; **inferred** from one chart |
| Green dotted 109.6137 | no structural explanation | unresolved |

- A and Full fix Z = 108.58 and R = 8.725 whatever ratios are used (0.75R = Full − A). Across all nice ratio
  triples (a, b, f) no single base Z fits A, B and Full together, so B uses a different base than A/Full.
- Using FMP prices (X 103.68, Z 108.58, Y 112.40) the tool gives A 110.76, B 113.21, Full 117.30; the cent
  differences are Bloomberg's own bar prints (103.675 / 112.405 or 112.40).
- Green 109.6137 = 108.58 + 0.236 × (108.06 − 103.68) fits exactly, but 108.06 is neither a pullback nor a
  swing high (Oct 15 12:00 high / Oct 15 14:30 low) and sits below Z, so I treat it as a numeric coincidence
  among ~4,500 candidate hits of the search. Not used.
- **B anchored on the bar before Z** is a toolbar option ("B from bar before Z"); it switches on with the
  Bloomberg 25/50 setting. It is one data point: untested on any other chart. Switch it off if other
  Bloomberg charts disagree.

## How DeMark selects pivots (documented vs inferred)

### Documented
- **TD Points** (T. DeMark, *The New Science of Technical Analysis*, 1994, ch.1, pp.10–15, 43–47): a TD Supply
  Point is a high not exceeded by the high of the bar immediately before and after; a TD Demand Point is a low not
  undercut by the bar before and after. Level K needs K bars each side with strictly lower highs (higher lows);
  every level-K point is also level 1. Aspen help (aspenres.com, "TD Points, Definition"): strictly greater than
  the K preceding and following bars; the level of a recent bar cannot be fixed until K more bars exist; "chart" or
  "true" highs/lows may be used (true: must also beat the close of the K+1th prior bar).
- **Equal highs/lows** (DeMark & DeMark, "High-quality entries", *Futures*, Oct 1997): if the high equals the prior bar's
  high, test from the bar before the first of the equal bars; the most recent of the equal bars is the TD Point.
- **TD Lines** use the two most recent same-level points, selected right to left. DeMark prefers level 1.
- **Refinement** (New Science p.14–15): a point low must also be below the close two days before ("true" low).
  A pivot is questioned if the next bar's close is beyond the TD Line rate of advance/decline.
- **TD Retracement point selection** (New Science ch.2, p.61): "extend an imaginary horizontal line from the recent low
  toward the left to the last time a lower low had been recorded; the highest price between these two points is the
  critical price." Mirror for a high. Magnet price is the close of that bar.
- **TD Propulsion** (Perl, *DeMark Indicators*, 2008, p.121–124): X = "price low of the move up", Y = "price high for
  the move so far", Z = the set-back low. X and Z are valid if the sell-offs from the *closes of the high bars* leading
  into X and Z are at least 23.6% of X–Y. Bloomberg defaults to 25/50. **Neither Perl, demark.com nor any
  public Bloomberg/Aspen/CQG/Symbolik document says how Bloomberg picks X, Y, Z.** No open-source Propulsion or
  TD Points implementation with DeMark's selection was found (TradingView scripts only draw 3/5-bar fractals).
- demark.com lists Propulsion ("short-term momentum… potential price exhaustion levels") and a separate **Thrust**
  ("projection levels from prior price movements") and **Trend Factor** (5.56% minimum move); Bloomberg's panel
  may combine these. Not testable without the terminal.

### Inferred (tested on the GDXJ 30m chart; not documented as the Propulsion rule)
**Auto (DeMark)**, evaluated as of the last visible bar:
1. Z = the most recent confirmed TD Point of level ≥ L (default L1; a low gives an up structure, a high a down one).
2. Y = highest high between Z and the last bar to the left with a lower low than Z (the TD Retracement critical price).
3. X = lowest low between Y and the last bar to the left of Y with a higher high.

At Oct 16 15:30 this returns X = Oct 14 14:00 (103.68), Y = Oct 16 10:30 (112.40), Z = Oct 16 14:30 (108.58)
at both L1 and L2, i.e. exactly Bloomberg's anchors. Y is a level-6 TD high and X a level-3+ TD low.
The Z bar is level 2 (not level 3: only two bars follow it). Which TD level Bloomberg requires for Z, whether a pullback
must be close-qualified at that moment, and unconfirmed-pivot handling cannot be determined from one chart.
Basis: High/Low by default; Close mode uses closes in every step.

### What the earlier tool got wrong
- Auto XYZ took the visible window's absolute extremes, not the most recent TD Point and the critical-price rule, so it
  needed the window to start at the right place and ignored the "from right to left" principle.
- B used the Z bar's own low; Bloomberg's B matches the low of the bar before it.
- Ratio and qualifier rules were right; pivot selection and B's anchor were the gaps.

## Tool changes
- **Auto XYZ** has two modes: DeMark pivots (above) and window extremes (old behaviour).
- **TD Pts** overlay: level numbers on highs (red) and lows (green), L1+/L2+/L3+, "true" option.
- **Drag handles**: each placed X, Y, Z has a ring; dragging moves only that pivot, snaps to the bar under the
  cursor (X/Z lows for up, Y high; mirrored for down; closes in Close mode), keeps X < Y < Z, recomputes A, B, Full and
  the cancel line live, and persists on release. Panning is unaffected elsewhere.
- Tests: `verify.py` (TD point levels incl. the equal-bar rule, Auto (DeMark) on `fixtures/gdxj_30m_oct2026.json`,
  Bloomberg A/Full/B) and `tests/browser_propulsion_drag.py` (real-browser drag of X, Y, Z, order clamp, persistence,
  Close mode).
