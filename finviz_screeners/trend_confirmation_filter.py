#!/usr/bin/env python3
"""
Trend Confirmation Filter
==========================
Second-stage filter on top of weekly_range_filter.py. Takes the tickers that
passed the weekly compression filter (trailing weekly % move within a target
band) and keeps only those that are:

  1. Above their 200-day SMA
  2. Above their 50-day SMA
  3. Within `--atr-mult` (default 3) ATR(14)s of their 50-day SMA

i.e. confirmed uptrend, not yet extended far above the 50-day line.

Usage:
    python trend_confirmation_filter.py                      # today
    python trend_confirmation_filter.py --date 2026-07-08
    python trend_confirmation_filter.py --min -3 --max 3     # weekly band override
    python trend_confirmation_filter.py --atr-mult 3
    python trend_confirmation_filter.py --no-save             # print only

Input:
    results/<YYYY-MM-DD>/tickers.txt   (produced by run_screeners.py)

Output:
    Printed report + daily_insights/<YYYY-MM-DD>/<YYYY-MM-DD>_trend_confirmation_filter.md

Polygon API key is read from the POLYGON_API_KEY env var or the repo-root .env file.
"""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from weekly_range_filter import parse_sections, fetch_weekly_perf, FINVIZ_AUTH_TOKEN

SCRIPT_DIR = Path(__file__).resolve().parent

SMA_SHORT = 50
SMA_LONG = 200
ATR_LENGTH = 14
LOOKBACK_DAYS = 380  # calendar days — enough for SMA200 + ATR14 with a buffer
DEFAULT_WORKERS = 10

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; finviz-screener-runner/1.0)",
}


# ---------------------------------------------------------------------------
# Polygon API key discovery
# ---------------------------------------------------------------------------

def _find_polygon_api_key() -> str | None:
    """Return POLYGON_API_KEY from env or the repo-root .env file."""
    key = os.environ.get("POLYGON_API_KEY")
    if key:
        return key

    try:
        from dotenv import dotenv_values
    except ImportError:
        return None

    env_path = SCRIPT_DIR.parent / ".env"
    if env_path.exists():
        vals = dotenv_values(env_path)
        if vals.get("POLYGON_API_KEY"):
            return vals["POLYGON_API_KEY"]
    return None


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------

def _atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(length).mean()


# ---------------------------------------------------------------------------
# Polygon fetching
# ---------------------------------------------------------------------------

def _fetch_one(ticker: str, client, start: str, end: str) -> tuple[str, dict | None]:
    try:
        aggs = client.get_aggs(ticker, 1, "day", start, end, adjusted=True, sort="asc", limit=5000)
        if not aggs:
            return ticker, None

        rows = [
            {"ts": pd.Timestamp(a.timestamp, unit="ms"), "high": a.high, "low": a.low, "close": a.close}
            for a in aggs
            if None not in (a.high, a.low, a.close)
        ]
        if len(rows) < SMA_LONG:
            return ticker, None

        df = pd.DataFrame(rows).set_index("ts").sort_index()
        sma50 = df["close"].rolling(SMA_SHORT).mean().iloc[-1]
        sma200 = df["close"].rolling(SMA_LONG).mean().iloc[-1]
        atr14 = _atr(df["high"], df["low"], df["close"], ATR_LENGTH).iloc[-1]
        close = df["close"].iloc[-1]

        if pd.isna(sma50) or pd.isna(sma200) or pd.isna(atr14) or atr14 == 0:
            return ticker, None

        return ticker, {
            "close": float(close),
            "sma50": float(sma50),
            "sma200": float(sma200),
            "atr14": float(atr14),
        }
    except Exception:
        return ticker, None


def fetch_trend_data(tickers: list[str], api_key: str, workers: int, target_date: date) -> dict[str, dict]:
    from polygon import RESTClient

    end = target_date.isoformat()
    start = (target_date - timedelta(days=LOOKBACK_DAYS)).isoformat()
    client = RESTClient(api_key=api_key, num_pools=workers + 5)

    results: dict[str, dict] = {}
    misses: list[str] = []
    total = len(tickers)

    print(f"  Fetching {total} tickers from Polygon ({workers} workers)...")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_one, t, client, start, end): t for t in tickers}
        for i, future in enumerate(as_completed(futures), 1):
            ticker, data = future.result()
            if data:
                results[ticker] = data
            else:
                misses.append(ticker)
            if i % 25 == 0 or i == total:
                print(f"    {i}/{total} done, {len(results)} with data", end="\r")
    print()
    if misses:
        print(f"  No usable price data for {len(misses)}: {', '.join(sorted(misses))}", file=sys.stderr)

    return results


# ---------------------------------------------------------------------------
# Filtering / report
# ---------------------------------------------------------------------------

def passes_trend_filter(data: dict, atr_mult: float) -> bool:
    close, sma50, sma200, atr14 = data["close"], data["sma50"], data["sma200"], data["atr14"]
    if close <= sma200 or close <= sma50:
        return False
    return (close - sma50) / atr14 <= atr_mult


def build_report(
    sections: dict[str, list[str]],
    weekly_perf: dict[str, float],
    trend_data: dict[str, dict],
    lo: float,
    hi: float,
    atr_mult: float,
    day: str,
) -> str:
    lines = [
        f"# Trend Confirmation Filter — {day}",
        "",
        f"Weekly compression band: {lo:+.0f}% to {hi:+.0f}% · "
        f"Trend gate: close > 50 SMA > 200 SMA, within {atr_mult:g}x ATR(14) of the 50 SMA",
        "",
    ]
    total_matches = 0
    for name, tickers in sections.items():
        weekly_ok = [t for t in tickers if t in weekly_perf and lo <= weekly_perf[t] <= hi]
        matches = []
        for t in weekly_ok:
            d = trend_data.get(t)
            if d and passes_trend_filter(d, atr_mult):
                dist_atr = (d["close"] - d["sma50"]) / d["atr14"]
                matches.append((t, weekly_perf[t], d["close"], d["sma50"], d["sma200"], dist_atr))
        if not matches:
            continue
        matches.sort(key=lambda x: x[5])
        total_matches += len(matches)
        lines.append(f"## {name} ({len(matches)}/{len(tickers)})")
        lines.append("")
        lines.append("| Ticker | Weekly % | Close | 50 SMA | 200 SMA | Dist/ATR |")
        lines.append("|---|---|---|---|---|---|")
        for t, wk, close, sma50, sma200, dist_atr in matches:
            lines.append(f"| {t} | {wk:+.2f}% | {close:.2f} | {sma50:.2f} | {sma200:.2f} | {dist_atr:+.2f} |")
        lines.append("")
        lines.append(", ".join(t for t, *_ in matches))
        lines.append("")
    if total_matches == 0:
        lines.append("No tickers passed both filters today.")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filter weekly-compression survivors by 50/200 SMA trend + ATR distance"
    )
    parser.add_argument("--date", metavar="YYYY-MM-DD", help="Date to process (default: today)")
    parser.add_argument("--min", type=float, default=-5.0, help="Minimum weekly %% change (default: -5)")
    parser.add_argument("--max", type=float, default=5.0, help="Maximum weekly %% change (default: 5)")
    parser.add_argument("--atr-mult", type=float, default=3.0,
                         help="Max distance above the 50 SMA, in ATR(14) multiples (default: 3)")
    parser.add_argument("--results-dir", default="results", metavar="PATH", help="Base results directory")
    parser.add_argument(
        "--insights-dir", default="daily_insights", metavar="PATH",
        help="Base daily_insights directory (default: daily_insights)",
    )
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Concurrent Polygon fetch threads")
    parser.add_argument("--polygon-key", default=None, help="Polygon API key (overrides env/auto-discovery)")
    parser.add_argument("--no-save", action="store_true", help="Print report only, don't write to daily_insights")
    args = parser.parse_args()

    if not FINVIZ_AUTH_TOKEN:
        print("ERROR: FINVIZ_AUTH_TOKEN is not set. Add it to your .env file.", file=sys.stderr)
        sys.exit(1)

    api_key = args.polygon_key or _find_polygon_api_key()
    if not api_key:
        print(
            "ERROR: No Polygon API key found.\n"
            "Set POLYGON_API_KEY env var, add it to a .env file, or pass --polygon-key.",
            file=sys.stderr,
        )
        sys.exit(1)

    day = args.date or date.today().strftime("%Y-%m-%d")
    target_date = date.fromisoformat(day)
    tickers_path = Path(args.results_dir) / day / "tickers.txt"
    if not tickers_path.exists():
        print(f"ERROR: {tickers_path} not found.", file=sys.stderr)
        sys.exit(1)

    sections = parse_sections(tickers_path)
    unique_tickers = sorted({t for ts in sections.values() for t in ts})
    print(f"=== Trend Confirmation Filter — {day} ===")
    print(f"{len(unique_tickers)} unique tickers across {len(sections)} sections\n")

    print("Stage 1: weekly compression filter")
    weekly_perf = fetch_weekly_perf(unique_tickers, FINVIZ_AUTH_TOKEN)
    weekly_survivors = sorted({
        t for t in unique_tickers if t in weekly_perf and args.min <= weekly_perf[t] <= args.max
    })
    print(f"  {len(weekly_survivors)}/{len(unique_tickers)} within {args.min:+.0f}% to {args.max:+.0f}% weekly\n")

    print("Stage 2: trend confirmation (50/200 SMA + ATR distance)")
    trend_data = fetch_trend_data(weekly_survivors, api_key, args.workers, target_date)

    report = build_report(sections, weekly_perf, trend_data, args.min, args.max, args.atr_mult, day)
    print()
    print(report)

    if not args.no_save:
        out_dir = Path(args.insights_dir) / day
        out_dir.mkdir(parents=True, exist_ok=True)
        suffix = "" if args.atr_mult == 3.0 else f"_atr{args.atr_mult:g}"
        out_path = out_dir / f"{day}_trend_confirmation_filter{suffix}.md"
        out_path.write_text(report)
        print(f"\nSaved → {out_path}")


if __name__ == "__main__":
    main()
