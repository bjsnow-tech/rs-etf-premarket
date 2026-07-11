#!/usr/bin/env python3
"""
Finviz Screener Runner
======================
Reads screener definitions from screeners.yaml, fetches each one via the
Finviz Elite export URL, and saves the results as date-stamped CSVs.

Usage:
    python run_screeners.py                    # run all screeners
    python run_screeners.py --screener name    # run a single screener by name
    python run_screeners.py --output-dir path  # override output directory

Output:
    results/<YYYY-MM-DD>/<screener_name>.csv

Install:
    pip install -r requirements.txt
"""

import argparse
import io
import os
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests
import yaml

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("  [!] python-dotenv not installed — .env file will not be loaded.")
    print("      Run: pip install python-dotenv")

FINVIZ_AUTH_TOKEN: str = os.environ.get("FINVIZ_AUTH_TOKEN", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; finviz-screener-runner/1.0)",
}


def load_screeners(config_path: Path) -> list[dict]:
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return config["screeners"]


def fetch_screener(name: str, url: str, token: str) -> pd.DataFrame:
    resolved_url = url.replace("{token}", token)
    response = requests.get(resolved_url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    df = pd.read_csv(io.StringIO(response.text))
    print(f"  [{name}] {len(df)} rows fetched")
    return df


def save_csv(df: pd.DataFrame, output_dir: Path, name: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{name}.csv"
    df.to_csv(out_path, index=False)
    print(f"  [{name}] saved → {out_path}")
    return out_path


def run(screeners: list[dict], token: str, output_dir: Path) -> None:
    errors = []
    ticker_lists: list[tuple[str, list[str]]] = []
    for s in screeners:
        name = s["name"]
        url = s["url"]
        try:
            df = fetch_screener(name, url, token)
            save_csv(df, output_dir, name)
            ticker_col = next((c for c in df.columns if c.strip().lower() == "ticker"), None)
            tickers = df[ticker_col].dropna().str.strip().tolist() if ticker_col else []
            ticker_lists.append((name, tickers))
        except Exception as e:
            print(f"  [{name}] ERROR: {e}", file=sys.stderr)
            errors.append((name, e))
        time.sleep(3)

    print()
    if errors:
        print(f"Completed with {len(errors)} error(s):")
        for name, e in errors:
            print(f"  - {name}: {e}")

    if ticker_lists:
        lines = []
        for name, tickers in ticker_lists:
            lines.append(f"[{name}]")
            lines.append(", ".join(tickers) if tickers else "(none)")
            lines.append("")
        txt_path = output_dir / "tickers.txt"
        txt_path.write_text("\n".join(lines).strip() + "\n")
        print(f"Tickers saved → {txt_path}\n")
        print("=== Tickers by Screener ===")
        for name, tickers in ticker_lists:
            print(f"\n[{name}]")
            print(", ".join(tickers) if tickers else "(none)")

    if errors:
        sys.exit(1)
    else:
        print(f"\nAll {len(screeners)} screener(s) saved to {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Finviz screeners and save to CSV")
    parser.add_argument(
        "--screener",
        metavar="NAME",
        help="Run only this screener (by name in screeners.yaml)",
    )
    parser.add_argument(
        "--output-dir",
        metavar="PATH",
        help="Output directory (default: results/YYYY-MM-DD)",
    )
    parser.add_argument(
        "--config",
        default="screeners.yaml",
        metavar="PATH",
        help="Path to screeners config file (default: screeners.yaml)",
    )
    args = parser.parse_args()

    if not FINVIZ_AUTH_TOKEN:
        print("ERROR: FINVIZ_AUTH_TOKEN is not set. Add it to your .env file.", file=sys.stderr)
        sys.exit(1)

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    screeners = load_screeners(config_path)

    if args.screener:
        screeners = [s for s in screeners if s["name"] == args.screener]
        if not screeners:
            print(f"ERROR: No screener named '{args.screener}' in {config_path}", file=sys.stderr)
            sys.exit(1)

    today = date.today().strftime("%Y-%m-%d")
    output_dir = Path(args.output_dir) if args.output_dir else Path("results") / today

    print(f"=== Finviz Screener Runner — {today} ===")
    print(f"Running {len(screeners)} screener(s) → {output_dir}\n")

    run(screeners, FINVIZ_AUTH_TOKEN, output_dir)


if __name__ == "__main__":
    main()
