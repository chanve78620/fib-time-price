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
- Bloomberg's values: trigger 110.7613, target/exhaustion 113.2125, full propulsion 117.305.
- With X = 103.675, Y = 112.40 and Z = 108.58, A = Z + 0.25R = 110.76125 and Full = Z + R = 117.305
  both match exactly. FMP prints 103.68 and 108.59, half a cent to a cent away from those anchors.
- Bloomberg's 113.2125 is not Z + 0.5R (that gives 112.9425). It equals 108.85 + 0.5R; 108.85 may be
  Bloomberg's close of the Z bar (FMP: 108.86). This is unconfirmed.
- Auto XYZ uses the anchors Bloomberg appears to use: X = the later of the window's absolute
  low/high, Y = the opposite extreme after it, Z = the deepest pullback after Y.
