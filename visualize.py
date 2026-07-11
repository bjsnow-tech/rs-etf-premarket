#!/usr/bin/env python3
"""
Render an rs_premarket CSV as a styled HTML dashboard.
Usage:  python visualize.py <csv_file> [--output dashboard.html]
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd

BLOCK_MAP = {"▁": 0, "▂": 1, "▃": 2, "▄": 3, "▅": 4, "▆": 5, "▇": 6, "█": 7}

SECTION_COLORS = {
    "Index":               "#0d1b4b",
    "Segment":             "#2d1b4b",
    "Equal Weight Sector": "#0a4d6b",
    "SPDR Sector":         "#074f47",
    "Group":               "#1b4f1e",
}

SECTION_NAMES = {
    "Index":               "Major Market Indices",
    "Segment":             "Segment",
    "Equal Weight Sector": "Equal Weight Sector ETFs",
    "SPDR Sector":         "SPDR Sector ETFs",
    "Group":               "Industry Groups",
}

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: 'Segoe UI', Consolas, Arial, sans-serif;
    font-size: 12px;
    background: #111827;
    color: #d1d5db;
    padding: 16px;
}
h1 { color: #93c5fd; margin-bottom: 10px; font-size: 15px; font-weight: 600; }
table { border-collapse: collapse; width: 100%; }
thead th {
    background: #0d1117;
    color: #6b9fce;
    padding: 5px 10px;
    border-bottom: 2px solid #2d3748;
    white-space: nowrap;
    font-size: 11px;
    text-align: right;
}
thead th.left { text-align: left; }
td {
    padding: 3px 10px;
    border-bottom: 1px solid #1e2736;
    white-space: nowrap;
    text-align: right;
    vertical-align: middle;
    font-size: 11.5px;
}
td.ticker { text-align: left; font-weight: 700; color: #e2e8f0; min-width: 52px; }
td.name   { text-align: left; color: #94a3b8; max-width: 190px; overflow: hidden; text-overflow: ellipsis; }
td.spark  { text-align: left; padding-left: 6px; }
td.setup  { color: #6ee7b7; font-weight: 700; text-align: center; }
td.rank   { color: #67e8f9; }
td.high   { color: #4ade80; text-align: center; }
tr.section-hdr td {
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.6px;
    color: #f1f5f9;
    padding: 6px 10px 5px;
    border-top: 2px solid #2d3748;
    text-align: left;
}
tr:not(.section-hdr):hover td { background: rgba(255,255,255,0.03); }
.px { color: #cbd5e1; }
.missing { color: #6b7280; font-style: italic; }
"""


def decode_histogram(hist: str) -> list[float]:
    return [BLOCK_MAP[ch] / 7.0 for ch in hist if ch in BLOCK_MAP]


def sparkline_svg(values: list[float], width: int = 90, height: int = 26) -> str:
    if len(values) < 2:
        return ""
    n = len(values)
    xs = [i / (n - 1) * (width - 4) + 2 for i in range(n)]
    lo, hi = min(values), max(values)
    rng = hi - lo if hi != lo else 1.0
    margin = 2
    ys = [height - margin - ((v - lo) / rng) * (height - margin * 2) for v in values]

    path = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))

    # Last point dot
    lx, ly = xs[-1], ys[-1]
    last_val = values[-1]
    is_near_high = last_val >= hi - rng * 0.05
    dot_color = "#4ade80" if is_near_high else "#60a5fa"

    # Line color: green if last > first, red if lower
    line_color = "#4ade80" if values[-1] >= values[0] else "#f87171"

    return (
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">'
        f'<path d="{path}" fill="none" stroke="{line_color}" stroke-width="1.4" stroke-linejoin="round"/>'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.2" fill="{dot_color}"/>'
        f'</svg>'
    )


def cell_style(val: float | None) -> str:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return ""
    if val > 0:
        alpha = min(0.15 + abs(val) * 4, 0.75)
        return f"background:rgba(74,222,128,{alpha:.2f});color:#bbf7d0;"
    elif val < 0:
        alpha = min(0.15 + abs(val) * 4, 0.75)
        return f"background:rgba(248,113,113,{alpha:.2f});color:#fecaca;"
    return ""


def rs_pct_style(val: float | None) -> str:
    """Heat-map style for a 0-100 percentile: green above 66, red below 33."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return ""
    if val >= 66:
        alpha = min(0.15 + (val - 66) / 34 * 0.6, 0.75)
        return f"background:rgba(74,222,128,{alpha:.2f});color:#bbf7d0;"
    elif val <= 33:
        alpha = min(0.15 + (33 - val) / 33 * 0.6, 0.75)
        return f"background:rgba(248,113,113,{alpha:.2f});color:#fecaca;"
    return ""


def fmt_vol(v) -> str:
    if pd.isna(v):
        return ""
    v = float(v)
    if v >= 1e9:
        return f"${v/1e9:.1f}B"
    if v >= 1e6:
        return f"${v/1e6:.0f}M"
    return f"${v:,.0f}"


def fmt_px(v) -> str:
    if pd.isna(v):
        return ""
    return f"${float(v):.2f}"


def build_html(df: pd.DataFrame, title: str) -> str:
    latest_date = df["Latest Date"].iloc[0] if "Latest Date" in df.columns else ""

    rows_html: list[str] = []
    prev_section = None

    for _, row in df.iterrows():
        section = str(row.get("Section", ""))
        status = str(row.get("Status", "ok"))

        if section != prev_section:
            bg = SECTION_COLORS.get(section, "#1e293b")
            label = SECTION_NAMES.get(section, section)
            rows_html.append(
                f'<tr class="section-hdr" style="background:{bg};">'
                f'<td colspan="13">{label}</td></tr>'
            )
            prev_section = section

        if status != "ok":
            rows_html.append(
                f'<tr><td class="ticker">{row.get("Ticker","")}</td>'
                f'<td class="name">{row.get("Name","")}</td>'
                f'<td colspan="11" class="missing">{status}</td></tr>'
            )
            continue

        daily = row.get("% Daily", None)
        monthly = row.get("% Monthly", None)
        rs_delta = row.get("1M RS Δ", None)
        rs_pct = row.get("1M RS %", None)
        rs_thrust = row.get("RS Thrust Rate", None)
        off_52w = row.get("% Off 52W High", None)

        try:
            daily = float(daily) if daily != "" and not pd.isna(daily) else None
        except (TypeError, ValueError):
            daily = None
        try:
            monthly = float(monthly) if monthly != "" and not pd.isna(monthly) else None
        except (TypeError, ValueError):
            monthly = None
        try:
            rs_delta = float(rs_delta) if rs_delta != "" and not pd.isna(rs_delta) else None
        except (TypeError, ValueError):
            rs_delta = None
        try:
            rs_pct = float(rs_pct) if rs_pct != "" and not pd.isna(rs_pct) else None
        except (TypeError, ValueError):
            rs_pct = None
        try:
            rs_thrust = float(rs_thrust) if rs_thrust != "" and not pd.isna(rs_thrust) else None
        except (TypeError, ValueError):
            rs_thrust = None
        try:
            off_52w = float(off_52w) if off_52w != "" and not pd.isna(off_52w) else None
        except (TypeError, ValueError):
            off_52w = None

        hist = str(row.get("1-Month RS Histogram", ""))
        spark = sparkline_svg(decode_histogram(hist))

        rank_raw = row.get("RS Rank In Section", "")
        rank_str = str(int(rank_raw)) if pd.notna(rank_raw) and rank_raw != "" else ""

        is_high = str(row.get("RS High In Window", "")).lower() == "true"
        is_setup = str(row.get("Setup", "")) == "Setup"

        rs_pct_str = f"{rs_pct:.1f}" if rs_pct is not None else ""
        rows_html.append(
            f'<tr>'
            f'<td class="ticker">{row.get("Ticker","")}</td>'
            f'<td class="name" title="{row.get("Name","")}">{row.get("Name","")}</td>'
            f'<td class="px">{fmt_px(row.get("Latest Px",""))}</td>'
            f'<td style="{cell_style(daily)}">{row.get("% Daily Text","")}</td>'
            f'<td style="{cell_style(monthly)}">{row.get("% Monthly Text","")}</td>'
            f'<td style="{cell_style(rs_delta)}">{row.get("1M RS Δ Text","")}</td>'
            f'<td style="{rs_pct_style(rs_pct)}">{rs_pct_str}</td>'
            f'<td style="{cell_style(rs_thrust)}">{row.get("RS Thrust Rate Text","")}</td>'
            f'<td style="{cell_style(off_52w)}">{row.get("% Off 52W High Text","")}</td>'
            f'<td class="spark">{spark}</td>'
            f'<td class="high">{"★" if is_high else ""}</td>'
            f'<td class="rank">{rank_str}</td>'
            f'<td>{fmt_vol(row.get("20D Avg $Vol",""))}</td>'
            f'</tr>'
        )

    header = (
        '<thead><tr>'
        '<th class="left">Ticker</th>'
        '<th class="left">Name</th>'
        '<th>Px</th>'
        '<th>% Daily</th>'
        '<th>% Monthly</th>'
        '<th>1M RS Δ</th>'
        '<th>1M RS %</th>'
        '<th>RS Thrust</th>'
        '<th>% Off 52W Hi</th>'
        '<th class="left">RS Trend</th>'
        '<th>RS Hi</th>'
        '<th>Rank</th>'
        '<th>20D $Vol</th>'
        '</tr></thead>'
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{CSS}</style>
</head>
<body>
<h1>RS Premarket Overview &mdash; {latest_date}</h1>
<table>
{header}
<tbody>
{''.join(rows_html)}
</tbody>
</table>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Render rs_premarket CSV as HTML dashboard.")
    parser.add_argument("csv", help="CSV file produced by rs-premarket")
    parser.add_argument("--output", default=None, help="Output HTML path (default: <csv>.html)")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if args.output:
        out_path = Path(args.output)
    else:
        html_dir = csv_path.parent / "html"
        html_dir.mkdir(exist_ok=True)
        out_path = html_dir / csv_path.with_suffix(".html").name

    df = pd.read_csv(csv_path)
    df = df[~df["Section"].isin(["Liquid Stocks", "Focus", "Stalk"])]
    html = build_html(df, csv_path.stem)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
