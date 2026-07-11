#!/usr/bin/env python3
"""
Weekly Range Filter
====================
Reads a date's tickers.txt (produced by run_screeners.py), fetches each
unique ticker's 1-week performance from Finviz, and reports the tickers
whose weekly move falls within a given range (default -5% to +5%),
grouped by their original screener section.

Usage:
    python weekly_range_filter.py                      # today, -5% to +5%
    python weekly_range_filter.py --date 2026-07-08
    python weekly_range_filter.py --min -3 --max 3
    python weekly_range_filter.py --no-save             # print only, skip daily_insights write

Input:
    results/<YYYY-MM-DD>/tickers.txt

Output:
    Printed report + daily_insights/<YYYY-MM-DD>/<YYYY-MM-DD>_weekly_range_filter.md
"""

import argparse
import os
import sys
import time
from datetime import date
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("  [!] python-dotenv not installed — .env file will not be loaded.")

FINVIZ_AUTH_TOKEN: str = os.environ.get("FINVIZ_AUTH_TOKEN", "")
PERFORMANCE_VIEW = 141  # Finviz "Performance" export view (includes Perf Week)
BATCH_SIZE = 150

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; finviz-screener-runner/1.0)",
}


def parse_sections(tickers_path: Path) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in tickers_path.read_text().splitlines():
        content = line.split("\t", 1)[-1].strip()
        if content.startswith("[") and content.endswith("]"):
            current = content[1:-1]
            sections[current] = []
        elif content and current:
            sections[current].extend(t.strip() for t in content.split(",") if t.strip())
    return sections


def fetch_weekly_perf(tickers: list[str], token: str) -> dict[str, float]:
    perf: dict[str, float] = {}
    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i : i + BATCH_SIZE]
        url = (
            f"https://elite.finviz.com/export.ashx?v={PERFORMANCE_VIEW}"
            f"&t={','.join(batch)}&auth={token}"
        )
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        df = pd.read_csv(StringIO(response.text))
        for _, row in df.iterrows():
            try:
                perf[row["Ticker"]] = float(str(row["Performance (Week)"]).rstrip("%"))
            except (ValueError, KeyError):
                continue
        print(f"  fetched weekly performance for {len(batch)} tickers ({i + len(batch)}/{len(tickers)})")
        if i + BATCH_SIZE < len(tickers):
            time.sleep(1)
    return perf


def build_report(
    sections: dict[str, list[str]], perf: dict[str, float], lo: float, hi: float, day: str
) -> str:
    lines = [f"# Weekly Range Filter ({lo:+.0f}% to {hi:+.0f}%) — {day}", ""]
    total_matches = 0
    for name, tickers in sections.items():
        matches = [(t, perf[t]) for t in tickers if t in perf and lo <= perf[t] <= hi]
        matches.sort(key=lambda x: x[1])
        if not matches:
            continue
        total_matches += len(matches)
        lines.append(f"## {name} ({len(matches)}/{len(tickers)})")
        lines.append("")
        lines.append(", ".join(t for t, v in matches))
        lines.append("")
    if total_matches == 0:
        lines.append("No tickers fell within range today.")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter finviz screener tickers by weekly performance range")
    parser.add_argument("--date", metavar="YYYY-MM-DD", help="Date to process (default: today)")
    parser.add_argument("--min", type=float, default=-5.0, help="Minimum weekly %% change (default: -5)")
    parser.add_argument("--max", type=float, default=5.0, help="Maximum weekly %% change (default: 5)")
    parser.add_argument("--results-dir", default="results", metavar="PATH", help="Base results directory")
    parser.add_argument(
        "--insights-dir",
        default="daily_insights",
        metavar="PATH",
        help="Base daily_insights directory (default: daily_insights)",
    )
    parser.add_argument("--no-save", action="store_true", help="Print report only, don't write to daily_insights")
    args = parser.parse_args()

    if not FINVIZ_AUTH_TOKEN:
        print("ERROR: FINVIZ_AUTH_TOKEN is not set. Add it to your .env file.", file=sys.stderr)
        sys.exit(1)

    day = args.date or date.today().strftime("%Y-%m-%d")
    tickers_path = Path(args.results_dir) / day / "tickers.txt"
    if not tickers_path.exists():
        print(f"ERROR: {tickers_path} not found.", file=sys.stderr)
        sys.exit(1)

    sections = parse_sections(tickers_path)
    unique_tickers = sorted({t for ts in sections.values() for t in ts})
    print(f"=== Weekly Range Filter — {day} ({args.min:+.0f}% to {args.max:+.0f}%) ===")
    print(f"{len(unique_tickers)} unique tickers across {len(sections)} sections\n")

    perf = fetch_weekly_perf(unique_tickers, FINVIZ_AUTH_TOKEN)
    missing = [t for t in unique_tickers if t not in perf]
    if missing:
        print(f"  [!] no performance data for: {', '.join(missing)}")

    report = build_report(sections, perf, args.min, args.max, day)
    print()
    print(report)

    if not args.no_save:
        out_dir = Path(args.insights_dir) / day
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{day}_weekly_range_filter.md"
        out_path.write_text(report)
        print(f"\nSaved → {out_path}")


if __name__ == "__main__":
    main()
