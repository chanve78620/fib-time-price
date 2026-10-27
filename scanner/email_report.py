#!/usr/bin/env python3
"""Build Time + Price Scanner email bodies from scanner/out/latest.json.

Usage:
  .venv/bin/python scanner/email_report.py            # write out/email.{html,txt,meta.json}
  .venv/bin/python scanner/email_report.py --print-html
  .venv/bin/python scanner/email_report.py --print-subject

Daily routine: scan.py → render_canvas.py → email_report.py → send via Gmail.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"
PAGE_URL = (
    "https://cursor.com/canvas/store-14b6a13c-f794-4d04-bcfe-d0893df95e28/"
    "bf0e6b89-7903-4f36-a2b0-a4f0c4e52937"
)
CHART = "https://fib-time-price.onrender.com/?t={t}&tf=1d&tp=1"


def _fmt_date(s: str) -> str:
    """YYYY-MM-DD → Mon D, YYYY for subject; keep ISO for tables if short."""
    if len(s) >= 10 and s[4] == "-":
        y, m, d = s[:10].split("-")
        months = (
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        )
        return f"{months[int(m) - 1]} {int(d)}, {y}"
    return s


def _window(r: dict) -> str:
    a, b = r.get("window_start") or "", r.get("window_end") or ""
    if a == b:
        return a
    return f"{a} → {b}"


def _dist(r: dict) -> str:
    d = r.get("dist_to_zone_pct")
    if d is None:
        return "—"
    return f"{d:+.2f}%"


def _close(r: dict) -> str:
    c = r.get("last_close")
    if c is None:
        return "—"
    if abs(c) >= 1000:
        return f"{c:,.1f}"
    return f"{c:,.2f}"


def _kind(r: dict) -> str:
    k = (r.get("kind") or "").lower()
    return "LOW" if k == "low" else "HIGH"


def _chart(t: str) -> str:
    return CHART.format(t=t)


def build(data: dict) -> tuple[str, str, str, dict]:
    scan_date = data["scan_date"]
    nice = _fmt_date(scan_date)
    subject = f"Time + Price Scanner – {nice}"
    now = [r for r in data["rows"] if r.get("status") == "now"]
    up = [r for r in data["rows"] if r.get("status") == "upcoming"]
    # strength desc, then ticker
    now.sort(key=lambda r: (-(r.get("strength") or 0), r.get("ticker") or ""))
    up.sort(key=lambda r: (-(r.get("strength") or 0), r.get("ticker") or ""))

    meta = {
        "subject": subject,
        "scan_date": scan_date,
        "universe_size": data.get("universe_size"),
        "n_now": data.get("n_now", len(now)),
        "n_upcoming": data.get("n_upcoming", len(up)),
        "n_low": data.get("n_low"),
        "n_high": data.get("n_high"),
        "page_url": PAGE_URL,
        "to": "billy.brandenberger@rbc.com",
    }

    def rows_html(rows: list[dict]) -> str:
        if not rows:
            return '<p style="color:#666;margin:8px 0;">None today.</p>'
        parts = [
            '<table cellpadding="0" cellspacing="0" border="0" width="100%" '
            'style="border-collapse:collapse;font-size:13px;font-family:'
            "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;\">"
            "<thead><tr>"
            '<th align="left" style="padding:8px 10px;border-bottom:2px solid #ddd;background:#f6f7f9;">Ticker</th>'
            '<th align="left" style="padding:8px 10px;border-bottom:2px solid #ddd;background:#f6f7f9;">Turn</th>'
            '<th align="left" style="padding:8px 10px;border-bottom:2px solid #ddd;background:#f6f7f9;">Window</th>'
            '<th align="left" style="padding:8px 10px;border-bottom:2px solid #ddd;background:#f6f7f9;">Zone</th>'
            '<th align="right" style="padding:8px 10px;border-bottom:2px solid #ddd;background:#f6f7f9;">Close</th>'
            '<th align="right" style="padding:8px 10px;border-bottom:2px solid #ddd;background:#f6f7f9;">Dist %</th>'
            "</tr></thead><tbody>"
        ]
        for i, r in enumerate(rows):
            bg = "#ffffff" if i % 2 == 0 else "#fafbfc"
            t = r["ticker"]
            href = html.escape(_chart(t), quote=True)
            parts.append(
                f'<tr style="background:{bg};">'
                f'<td style="padding:7px 10px;border-bottom:1px solid #eee;">'
                f'<a href="{href}" style="color:#0b57d0;font-weight:600;text-decoration:none;">'
                f"{html.escape(t)}</a></td>"
                f'<td style="padding:7px 10px;border-bottom:1px solid #eee;">{html.escape(_kind(r))}</td>'
                f'<td style="padding:7px 10px;border-bottom:1px solid #eee;white-space:nowrap;">'
                f"{html.escape(_window(r))}</td>"
                f'<td style="padding:7px 10px;border-bottom:1px solid #eee;">{html.escape(str(r.get("zone_label") or "—"))}</td>'
                f'<td align="right" style="padding:7px 10px;border-bottom:1px solid #eee;font-variant-numeric:tabular-nums;">'
                f"{html.escape(_close(r))}</td>"
                f'<td align="right" style="padding:7px 10px;border-bottom:1px solid #eee;font-variant-numeric:tabular-nums;">'
                f"{html.escape(_dist(r))}</td>"
                f"</tr>"
            )
        parts.append("</tbody></table>")
        return "".join(parts)

    def rows_text(rows: list[dict]) -> str:
        if not rows:
            return "  (none)\n"
        lines = []
        for r in rows:
            t = r["ticker"]
            lines.append(
                f"  {t:6}  {_kind(r):4}  {_window(r):23}  "
                f"zone {r.get('zone_label') or '—'}  "
                f"close {_close(r)}  dist {_dist(r)}\n"
                f"         {_chart(t)}\n"
            )
        return "".join(lines)

    html_body = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
<body style="margin:0;padding:0;background:#f0f2f5;">
  <div style="max-width:820px;margin:0 auto;padding:24px 16px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;color:#1a1a1a;">
    <h1 style="margin:0 0 4px;font-size:22px;font-weight:700;">Time + Price Scanner</h1>
    <p style="margin:0 0 16px;color:#555;font-size:14px;">
      Scan date <strong>{html.escape(nice)}</strong>
      · universe <strong>{meta['universe_size']}</strong> tickers
    </p>
    <table cellpadding="0" cellspacing="0" border="0" style="margin:0 0 20px;font-size:13px;">
      <tr>
        <td style="padding:10px 14px;background:#e8f0fe;border-radius:8px;margin-right:8px;">
          <div style="font-size:20px;font-weight:700;color:#0b57d0;">{meta['n_now']}</div>
          <div style="color:#555;">In window now</div>
        </td>
        <td style="width:10px;"></td>
        <td style="padding:10px 14px;background:#fef7e0;border-radius:8px;">
          <div style="font-size:20px;font-weight:700;color:#a05a00;">{meta['n_upcoming']}</div>
          <div style="color:#555;">Upcoming (≤3d)</div>
        </td>
        <td style="width:10px;"></td>
        <td style="padding:10px 14px;background:#e6f4ea;border-radius:8px;">
          <div style="font-size:20px;font-weight:700;color:#137333;">{meta['n_low']}</div>
          <div style="color:#555;">Possible LOWs</div>
        </td>
        <td style="width:10px;"></td>
        <td style="padding:10px 14px;background:#fce8e6;border-radius:8px;">
          <div style="font-size:20px;font-weight:700;color:#c5221f;">{meta['n_high']}</div>
          <div style="color:#555;">Possible HIGHs</div>
        </td>
      </tr>
    </table>

    <h2 style="margin:24px 0 10px;font-size:16px;border-bottom:2px solid #0b57d0;padding-bottom:6px;">In window now</h2>
    {rows_html(now)}

    <h2 style="margin:28px 0 10px;font-size:16px;border-bottom:2px solid #a05a00;padding-bottom:6px;">Upcoming</h2>
    {rows_html(up)}

    <p style="margin:28px 0 8px;font-size:14px;">
      <a href="{html.escape(PAGE_URL, quote=True)}" style="color:#0b57d0;font-weight:600;">
        Open the Time + Price Scanner Page
      </a>
      — sortable filters, strength &amp; 1Y hit rates.
    </p>
    <p style="margin:0;font-size:12px;color:#888;">
      Tickers open the live chart with Time+Price on (?tp=1). Deploy main on Render if ?tp=1 is not live yet.
    </p>
  </div>
</body></html>
"""

    text_body = (
        f"Time + Price Scanner – {nice}\n"
        f"Universe: {meta['universe_size']} tickers\n"
        f"In window now: {meta['n_now']}  |  Upcoming: {meta['n_upcoming']}  |  "
        f"LOW: {meta['n_low']}  |  HIGH: {meta['n_high']}\n"
        f"\nPage: {PAGE_URL}\n"
        f"\n=== In window now ===\n"
        f"{rows_text(now)}"
        f"\n=== Upcoming ===\n"
        f"{rows_text(up)}"
    )
    return subject, text_body, html_body, meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, default=OUT / "latest.json")
    ap.add_argument("--print-html", action="store_true")
    ap.add_argument("--print-text", action="store_true")
    ap.add_argument("--print-subject", action="store_true")
    args = ap.parse_args()
    data = json.loads(args.json.read_text())
    subject, text_body, html_body, meta = build(data)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "email.html").write_text(html_body)
    (OUT / "email.txt").write_text(text_body)
    (OUT / "email.meta.json").write_text(json.dumps(meta, indent=2))
    if args.print_subject:
        print(subject)
    elif args.print_html:
        print(html_body)
    elif args.print_text:
        print(text_body)
    else:
        print(json.dumps({"subject": subject, "html": str(OUT / "email.html"), "text": str(OUT / "email.txt"), **{k: meta[k] for k in ("n_now", "n_upcoming", "universe_size")}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
