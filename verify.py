#!/usr/bin/env python3
"""Verify Newton-style Fib TIME math against Oct 1, 2026 tweet worksheet values."""

from datetime import date, timedelta
from math import floor

RATIOS = [
    0.272, 0.382, 0.414, 0.500, 0.618, 0.707, 0.786, 0.841,
    1.000, 1.272, 1.382, 1.414, 1.500, 1.618, 1.707, 1.786, 1.841,
    2.000, 2.272, 2.382, 2.414, 2.500, 2.618, 2.707, 2.786, 2.841,
    3.000, 3.272,
]

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def format_date(d: date) -> str:
    return f"{d.day}-{MONTHS[d.month - 1]}-{d.year}"


def compute_row(ratio: float, date1: date, date2: date, base_days: int):
    raw = ratio * base_days
    days_disp = round(raw)
    floor_days = floor(raw)
    return {
        "ratio": ratio,
        "days": days_disp,
        "weeks": days_disp / 7,
        "months": days_disp / 29.5,
        "years": days_disp / 365,
        "add1": date1 + timedelta(days=floor_days),
        "add2": date2 + timedelta(days=floor_days),
        "add1_str": format_date(date1 + timedelta(days=floor_days)),
        "add2_str": format_date(date2 + timedelta(days=floor_days)),
    }


# Expected rows from tweet / Excel screenshot
EXPECTED = [
    # ratio, days, add1, add2
    (0.382, 52, "20-May-2026", "3-Oct-2026"),
    (0.618, 84, "22-Jun-2026", "5-Nov-2026"),
    (1.000, 136, "13-Aug-2026", "27-Dec-2026"),
    (1.500, 204, "20-Oct-2026", "5-Mar-2027"),
    (1.618, 220, "5-Nov-2026", "21-Mar-2027"),
]


def main():
    date1 = date(2026, 3, 30)
    date2 = date(2026, 8, 13)
    base_days = (date2 - date1).days

    print(f"Date1={date1}  Date2={date2}  baseDays={base_days}")
    assert base_days == 136, f"baseDays expected 136, got {base_days}"

    failures = []
    for ratio, exp_days, exp_add1, exp_add2 in EXPECTED:
        row = compute_row(ratio, date1, date2, base_days)
        ok = (
            row["days"] == exp_days
            and row["add1_str"] == exp_add1
            and row["add2_str"] == exp_add2
        )
        status = "PASS" if ok else "FAIL"
        print(
            f"  {status}  r={ratio:.3f}  Days={row['days']} (exp {exp_days})  "
            f"Add1={row['add1_str']} (exp {exp_add1})  "
            f"Add2={row['add2_str']} (exp {exp_add2})"
        )
        if not ok:
            failures.append(ratio)
            raw = ratio * base_days
            print(f"         debug: raw={raw} floor={floor(raw)} round={round(raw)}")

    # Sanity: floor vs round split for 0.382
    raw_382 = 0.382 * 136
    assert abs(raw_382 - 51.952) < 1e-9, raw_382
    assert round(raw_382) == 52
    assert floor(raw_382) == 51

    if failures:
        print("FAIL")
        raise SystemExit(1)

    print("PASS")
    return 0


if __name__ == "__main__":
    main()
