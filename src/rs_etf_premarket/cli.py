"""
RS Premarket Overview CSV Builder

Pulls daily OHLCV data from Polygon.io for all tickers concurrently,
then computes relative strength metrics vs a benchmark (default: SPY).

API key is read from the POLYGON_API_KEY env var or a local .env file.

Install:
    uv pip install -e .

Basic use:
    rs-premarket

With live/intraday proxy (Polygon snapshot):
    rs-premarket --mode live

Custom output:
    rs-premarket --output my_rs_report.csv

Custom tickers CSV:
    rs-premarket --tickers my_tickers.csv

Custom tickers CSV format:
    Section,Ticker,Name,Benchmark
    Index,SPY,SPDR S&P 500 ETF Trust,SPY
    Equal Weight Sector,RSPT,S&P 500 Equal Weight Technology,SPY
    SPDR Sector,XLK,Technology Select Sector SPDR,SPY
    Group,XSD,Semiconductor,SPY
    Liquid Stocks,NVDA,NVIDIA,SPY
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


DEFAULT_UNIVERSE = [
    # Index
    ("Index", "SPY", "SPDR S&P 500 ETF Trust", "SPY"),
    ("Index", "RSP", "Invesco S&P 500 Equal Weight ETF", "SPY"),
    ("Index", "QQQE", "Direxion NASDAQ-100 Equal Weighted Index Shares", "SPY"),
    ("Index", "IWM", "iShares Russell 2000 ETF", "SPY"),
    ("Index", "TLT", "iShares 20+ Year Treasury Bond ETF", "SPY"),
    ("Index", "RPV", "S&P 500 Large-Cap Value", "SPY"),
    ("Index", "RPG", "S&P 500 Large-Cap Growth", "SPY"),

    # Size & Style
    ("Segment", "IVV", "S&P 500 Core", "SPY"),
    ("Segment", "IVE", "S&P 500 Value", "SPY"),
    ("Segment", "IVW", "S&P 500 Growth", "SPY"),
    ("Segment", "IJH", "S&P Mid-Cap 400 Core", "SPY"),
    ("Segment", "IJJ", "S&P Mid-Cap 400 Value", "SPY"),
    ("Segment", "IJK", "S&P Mid-Cap 400 Growth", "SPY"),
    ("Segment", "IJR", "S&P Small-Cap 600 Core", "SPY"),
    ("Segment", "IJS", "S&P Small-Cap 600 Value", "SPY"),
    ("Segment", "IJT", "S&P Small-Cap 600 Growth", "SPY"),

    # Equal Weight Sector
    ("Equal Weight Sector", "RSPT", "S&P 500 Equal Weight Technology", "SPY"),
    ("Equal Weight Sector", "RSPD", "S&P 500 Equal Weight Consumer Discretionary", "SPY"),
    ("Equal Weight Sector", "RSPC", "S&P 500 Equal Weight Communication Services", "SPY"),
    ("Equal Weight Sector", "RSPR", "S&P 500 Equal Weight Real Estate", "SPY"),
    ("Equal Weight Sector", "RSPH", "S&P 500 Equal Weight Health Care", "SPY"),
    ("Equal Weight Sector", "RSPN", "S&P 500 Equal Weight Industrials", "SPY"),
    ("Equal Weight Sector", "RSPF", "S&P 500 Equal Weight Financials", "SPY"),
    ("Equal Weight Sector", "RSPG", "S&P 500 Equal Weight Energy", "SPY"),
    ("Equal Weight Sector", "RSPM", "S&P 500 Equal Weight Materials", "SPY"),
    ("Equal Weight Sector", "RSPU", "S&P 500 Equal Weight Utilities", "SPY"),
    ("Equal Weight Sector", "RSPS", "S&P 500 Equal Weight Consumer Staples", "SPY"),

    # SPDR Sector
    ("SPDR Sector", "XLK", "Technology Select Sector SPDR", "SPY"),
    ("SPDR Sector", "XLY", "Consumer Discretionary Select Sector SPDR", "SPY"),
    ("SPDR Sector", "XLC", "Communication Services Select Sector SPDR", "SPY"),
    ("SPDR Sector", "XLRE", "Real Estate Select Sector SPDR", "SPY"),
    ("SPDR Sector", "XLV", "Health Care Select Sector SPDR", "SPY"),
    ("SPDR Sector", "XLI", "Industrial Select Sector SPDR", "SPY"),
    ("SPDR Sector", "XLF", "Financial Select Sector SPDR", "SPY"),
    ("SPDR Sector", "XLE", "Energy Select Sector SPDR", "SPY"),
    ("SPDR Sector", "XLB", "Materials Select Sector SPDR", "SPY"),
    ("SPDR Sector", "XLU", "Utilities Select Sector SPDR", "SPY"),
    ("SPDR Sector", "XLP", "Consumer Staples Select Sector SPDR", "SPY"),

    # Group
    ("Group", "FXI", "China Large Cap", "SPY"),
    ("Group", "GXC", "China", "SPY"),
    ("Group", "FFTY", "IBD 50", "SPY"),
    ("Group", "XHB", "Homebuilders", "SPY"),
    ("Group", "CIBR", "Cyber Security", "SPY"),
    ("Group", "PBJ", "Food & Beverage", "SPY"),
    ("Group", "XRT", "Retail", "SPY"),
    ("Group", "IBUY", "Online Retail", "SPY"),
    ("Group", "DRIV", "Automation & EV", "SPY"),
    ("Group", "WCLD", "Cloud Computing", "SPY"),
    ("Group", "PEJ", "Leisure and Entertainment", "SPY"),
    ("Group", "XTL", "Telecom", "SPY"),
    ("Group", "XSW", "Software & Services", "SPY"),
    ("Group", "KIE", "Insurance", "SPY"),
    ("Group", "IPAY", "Mobile Payment", "SPY"),
    ("Group", "USO", "United States Oil", "SPY"),
    ("Group", "KCE", "Capital Markets", "SPY"),
    ("Group", "ROBO", "Robotics & Automation", "SPY"),
    ("Group", "GNR", "Natural Resources", "SPY"),
    ("Group", "BOAT", "Global Shipping", "SPY"),
    ("Group", "XOP", "Oil & Gas Exploration & Production", "SPY"),
    ("Group", "FCG", "Natural Gas", "SPY"),
    ("Group", "BUZZ", "Social Sentiment", "SPY"),
    ("Group", "XHS", "Health Care Services", "SPY"),
    ("Group", "PAVE", "Global Infrastructure", "SPY"),
    ("Group", "MOO", "Agribusiness", "SPY"),
    ("Group", "KBE", "US Banks", "SPY"),
    ("Group", "GBTC", "Bitcoin Trust", "SPY"),
    ("Group", "XTN", "Transportation", "SPY"),
    ("Group", "XBI", "Biotech", "SPY"),
    ("Group", "BLOK", "Crypto Related Companies", "SPY"),
    ("Group", "XSD", "Semiconductor", "SPY"),
    ("Group", "XHE", "Healthcare Equipment", "SPY"),
    ("Group", "XPH", "Pharmaceuticals", "SPY"),
    ("Group", "KRE", "Regional Banks", "SPY"),
    ("Group", "XAR", "Aerospace & Defence", "SPY"),
    ("Group", "XES", "Oil & Gas Equipment & Services", "SPY"),
    ("Group", "COPX", "Copper Miners", "SPY"),
    ("Group", "PBW", "Clean Energy", "SPY"),
    ("Group", "XME", "Metal & Mining", "SPY"),
    ("Group", "SLX", "Steel", "SPY"),
    ("Group", "JETS", "Airliners", "SPY"),
    ("Group", "ITB", "US Home Construction", "SPY"),
    ("Group", "IYT", "US Transportation", "SPY"),
    ("Group", "BETZ", "Sports Betting & iGaming", "SPY"),
    ("Group", "IHF", "US Healthcare Providers", "SPY"),
    ("Group", "PHO", "Water Resources", "SPY"),
    ("Group", "CNBS", "Cannabis", "SPY"),
    ("Group", "PBE", "Dynamic Biotechnology & Genome", "SPY"),
    ("Group", "IHI", "US Medical Devices", "SPY"),
    ("Group", "PPH", "Pharmaceuticals", "SPY"),
    ("Group", "DRAM", "Roundhill Memory ETF", "SPY"),

    # Individual Stock
    ("Individual Stock", "MU", "Micron Technology", "SPY"),
    ("Individual Stock", "SNDK", "SanDisk", "SPY"),
    ("Individual Stock", "WDC", "Western Digital", "SPY"),
    ("Individual Stock", "STX", "Seagate Technology", "SPY"),
]


@dataclass(frozen=True)
class RowDef:
    section: str
    ticker: str
    name: str
    benchmark: str = "SPY"


def load_universe(path: str | None) -> list[RowDef]:
    if not path:
        return [RowDef(*row) for row in DEFAULT_UNIVERSE]

    df = pd.read_csv(path)
    required = {"Section", "Ticker", "Name"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Ticker CSV missing columns: {sorted(missing)}")

    if "Benchmark" not in df.columns:
        df["Benchmark"] = "SPY"

    rows = []
    for _, r in df.iterrows():
        rows.append(
            RowDef(
                section=str(r["Section"]).strip(),
                ticker=str(r["Ticker"]).strip().upper(),
                name=str(r["Name"]).strip(),
                benchmark=str(r["Benchmark"]).strip().upper() or "SPY",
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Polygon API key discovery
# ---------------------------------------------------------------------------

def _find_polygon_api_key() -> str | None:
    """Return POLYGON_API_KEY from env or a local .env file."""
    key = os.environ.get("POLYGON_API_KEY")
    if key:
        return key

    try:
        from dotenv import dotenv_values
    except ImportError:
        return None

    here = Path(__file__).resolve().parent
    # cli.py -> rs_etf_premarket/ -> src/ -> project root
    env_path = here.parent.parent.parent / ".env"
    if env_path.exists():
        vals = dotenv_values(env_path)
        if vals.get("POLYGON_API_KEY"):
            logger.debug("Loaded POLYGON_API_KEY from %s", env_path)
            return vals["POLYGON_API_KEY"]
    return None


# ---------------------------------------------------------------------------
# Polygon data fetching
# ---------------------------------------------------------------------------

def _fetch_one_polygon(ticker: str, client, start: str, end: str) -> dict:
    """Fetch 1 year of daily OHLCV for a single ticker from Polygon."""
    try:
        aggs = client.get_aggs(
            ticker, 1, "day", start, end,
            adjusted=True, sort="asc", limit=50000,
        )
        if not aggs:
            return {"ticker": ticker, "df": None}

        rows = []
        for a in aggs:
            if None not in (a.open, a.high, a.low, a.close, a.volume, a.timestamp):
                rows.append({
                    "ts":     pd.Timestamp(a.timestamp, unit="ms", tz="UTC").tz_convert(None).normalize(),
                    "close":  float(a.close),
                    "volume": float(a.volume),
                    "high":   float(a.high),
                })

        if not rows:
            return {"ticker": ticker, "df": None}

        df = pd.DataFrame(rows).set_index("ts")
        df.index.name = None
        return {"ticker": ticker, "df": df}

    except Exception as exc:
        logger.warning("Polygon fetch failed for %s: %s", ticker, exc)
        return {"ticker": ticker, "df": None}


def download_prices_polygon(
    tickers: Iterable[str],
    api_key: str,
    period_days: int = 55,
    workers: int = 20,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    """
    Fetch daily close/volume for the RS window and 52W highs for all tickers.

    Makes one Polygon aggs call per ticker (1-year window), concurrently
    across `workers` threads.  Returns:
      close    — DataFrame(date × ticker), trimmed to `period_days`
      volume   — DataFrame(date × ticker), trimmed to `period_days`
      highs_52w — dict[ticker, float] — rolling 52W high
    """
    from polygon import RESTClient  # type: ignore

    tickers = sorted(set(tickers))
    end_date = date.today()
    start_52w = (end_date - timedelta(days=375)).isoformat()
    end_str   = end_date.isoformat()
    cutoff    = pd.Timestamp(end_date - timedelta(days=period_days))

    client = RESTClient(api_key=api_key, num_pools=workers + 5)

    raw: dict[str, pd.DataFrame | None] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {
            ex.submit(_fetch_one_polygon, t, client, start_52w, end_str): t
            for t in tickers
        }
        for fut in as_completed(futures):
            r = fut.result()
            raw[r["ticker"]] = r["df"]

    close_cols: dict[str, pd.Series] = {}
    volume_cols: dict[str, pd.Series] = {}
    highs_52w:   dict[str, float]     = {}

    for t, df in raw.items():
        if df is None or df.empty:
            continue
        highs_52w[t] = float(df["high"].max())
        trimmed = df[df.index >= cutoff]
        if not trimmed.empty:
            close_cols[t]  = trimmed["close"]
            volume_cols[t] = trimmed["volume"]

    close  = pd.DataFrame(close_cols).sort_index()
    volume = pd.DataFrame(volume_cols).sort_index()
    return close, volume, highs_52w


def get_live_prices_polygon(tickers: list[str], api_key: str) -> dict[str, float]:
    """Fetch latest trade price for all tickers via Polygon snapshot (single call)."""
    from polygon import RESTClient  # type: ignore

    client = RESTClient(api_key=api_key)
    live: dict[str, float] = {}
    try:
        snapshots = client.get_snapshot_all("stocks", tickers)
        for snap in snapshots:
            t = getattr(snap, "ticker", None)
            if not t:
                continue
            # Prefer last trade, fall back to day close
            lt = getattr(snap, "last_trade", None)
            price = getattr(lt, "price", None) if lt else None
            if not price:
                day = getattr(snap, "day", None)
                price = getattr(day, "close", None) if day else None
            if price:
                live[t] = float(price)
    except Exception as exc:
        logger.warning("Polygon snapshot failed: %s", exc)
    return live


# ---------------------------------------------------------------------------
# Report building (unchanged logic, provider-agnostic)
# ---------------------------------------------------------------------------

def text_histogram(values: pd.Series, width: int = 20) -> str:
    vals = values.dropna().astype(float)
    if vals.empty:
        return ""

    vals = vals.tail(width)
    lo, hi = vals.min(), vals.max()
    blocks = "▁▂▃▄▅▆▇█"

    if math.isclose(float(lo), float(hi)):
        chars = ["▁"] * len(vals)
    else:
        scaled = ((vals - lo) / (hi - lo) * (len(blocks) - 1)).round().astype(int)
        chars = [blocks[i] for i in scaled]

    high_idx = vals.idxmax()
    out = []
    for idx, ch in zip(vals.index, chars):
        out.append(f"[{ch}]" if idx == high_idx else ch)
    return "".join(out)


def pct(x: float | int | np.float64 | None) -> float | None:
    if x is None or pd.isna(x) or np.isinf(x):
        return None
    return float(x)


def build_report(
    rows: list[RowDef],
    close: pd.DataFrame,
    volume: pd.DataFrame,
    live_last: dict[str, float] | None = None,
    highs_52w: dict[str, float] | None = None,
) -> pd.DataFrame:
    if close.empty:
        raise RuntimeError("No price data returned. Check API key and ticker symbols.")

    live_last = live_last or {}
    out = []

    for r in rows:
        t = r.ticker
        b = r.benchmark

        if t not in close.columns or b not in close.columns:
            out.append({
                "Section": r.section, "Ticker": t, "Name": r.name,
                "Benchmark": b, "Status": "missing price data",
            })
            continue

        px = close[t].dropna()
        bm = close[b].dropna()
        common = pd.concat([px, bm], axis=1, join="inner").dropna()
        common.columns = ["px", "bm"]

        if len(common) < 2:
            out.append({
                "Section": r.section, "Ticker": t, "Name": r.name,
                "Benchmark": b, "Status": "not enough history",
            })
            continue

        latest_close    = float(common["px"].iloc[-1])
        latest_bm_close = float(common["bm"].iloc[-1])
        latest_px       = live_last.get(t, latest_close)
        latest_bm       = live_last.get(b, latest_bm_close)

        prev_close  = float(common["px"].iloc[-2])
        first_close = float(common["px"].iloc[0])
        first_bm    = float(common["bm"].iloc[0])

        daily_return   = latest_px / prev_close - 1
        monthly_return = latest_px / first_close - 1

        rs_series   = common["px"] / common["bm"]
        latest_rs   = latest_px / latest_bm if latest_bm else np.nan
        starting_rs = first_close / first_bm if first_bm else np.nan
        rs_1m_delta = latest_rs / starting_rs - 1 if starting_rs else np.nan

        vol20 = None
        if t in volume.columns:
            vol_vals = volume[t].dropna().tail(20)
            if not vol_vals.empty:
                vol20 = float(vol_vals.mean())

        high_52w   = highs_52w.get(t) if highs_52w else None
        pct_off_52w = (latest_px / high_52w - 1) if high_52w else None

        rs_thrust = None
        rs_tail   = rs_series.tail(20)
        n_rs      = len(rs_tail)
        if n_rs >= 3:
            baseline = float(rs_tail.iloc[0])
            if baseline != 0 and not np.isnan(baseline):
                ys    = rs_tail.values.astype(float) / baseline
                xs    = np.arange(n_rs, dtype=float)
                slope = float(np.polyfit(xs, ys, 1)[0])
                rs_thrust = slope * 20

        rs_thrust_1w = None
        rs_tail_1w   = rs_series.tail(5)
        n_rs_1w      = len(rs_tail_1w)
        if n_rs_1w >= 3:
            baseline_1w = float(rs_tail_1w.iloc[0])
            if baseline_1w != 0 and not np.isnan(baseline_1w):
                ys_1w    = rs_tail_1w.values.astype(float) / baseline_1w
                xs_1w    = np.arange(n_rs_1w, dtype=float)
                slope_1w = float(np.polyfit(xs_1w, ys_1w, 1)[0])
                rs_thrust_1w = slope_1w * 5

        out.append({
            "Section":              r.section,
            "Ticker":               t,
            "Name":                 r.name,
            "Benchmark":            b,
            "Latest Date":          common.index[-1].strftime("%Y-%m-%d"),
            "Latest Px":            round(latest_px, 4),
            "% Daily":              pct(daily_return),
            "% Monthly":            pct(monthly_return),
            "Latest RS":            round(float(latest_rs), 6) if pd.notna(latest_rs) else None,
            "1M RS Δ":              pct(rs_1m_delta),
            "RS Thrust Rate":       pct(rs_thrust),
            "1W RS Thrust":         pct(rs_thrust_1w),
            "% Off 52W High":       pct(pct_off_52w),
            "20D Avg $Vol":         round(vol20 * latest_px, 0) if vol20 else None,
            "1-Month RS Histogram": text_histogram(rs_series, width=20),
            "RS High In Window":    bool(pd.notna(latest_rs) and latest_rs >= rs_series.max()),
            "Setup":                "Setup" if pd.notna(rs_1m_delta) and rs_1m_delta > 0 and daily_return > -0.01 else "",
            "Status":               "ok",
        })

    report = pd.DataFrame(out)

    if "1M RS Δ" in report.columns:
        report["RS Rank In Section"] = (
            report.groupby("Section")["1M RS Δ"]
            .rank(ascending=False, method="min")
        )
        report["1M RS %"] = (
            report["1M RS Δ"].rank(pct=True, ascending=True, na_option="keep") * 100
        ).round(1)

    section_order = {
        "Index": 0, "Segment": 1, "Equal Weight Sector": 2,
        "SPDR Sector": 3, "Group": 4, "Individual Stock": 5,
    }
    report["_section_order"] = report["Section"].map(section_order).fillna(99)
    report = report.sort_values(["_section_order", "RS Rank In Section", "Ticker"], na_position="last")
    report = report.drop(columns=["_section_order"])

    for col in ["% Daily", "% Monthly", "1M RS Δ", "% Off 52W High", "RS Thrust Rate", "1W RS Thrust"]:
        if col in report.columns:
            report[col + " Text"] = report[col].map(lambda x: "" if pd.isna(x) else f"{x:.2%}")

    preferred = [
        "Section", "Ticker", "Name", "Benchmark", "Latest Date", "Latest Px",
        "% Daily Text", "% Monthly Text", "1M RS Δ Text", "1M RS %",
        "1W RS Thrust Text", "RS Thrust Rate Text",
        "% Off 52W High Text",
        "Latest RS", "RS Rank In Section", "20D Avg $Vol",
        "1-Month RS Histogram", "RS High In Window", "Setup", "Status",
        "% Daily", "% Monthly", "1M RS Δ", "1W RS Thrust", "RS Thrust Rate", "% Off 52W High",
    ]
    cols = [c for c in preferred if c in report.columns] + [c for c in report.columns if c not in preferred]
    return report[cols]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _period_to_days(period: str) -> int:
    """Convert period string (e.g. '45d', '2mo') to calendar days with buffer."""
    if period.endswith("d"):
        return int(period[:-1]) + 10
    if period.endswith("mo"):
        return int(period[:-2]) * 35
    if period.endswith("y"):
        return int(period[:-1]) * 375
    return 55


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Build a relative-strength dashboard CSV using Polygon.io.")
    parser.add_argument("--tickers",     default=None,       help="Custom universe CSV with Section,Ticker,Name,Benchmark columns.")
    parser.add_argument("--benchmark",   default="SPY",      help="Default benchmark if custom CSV omits Benchmark. Default: SPY")
    parser.add_argument("--period",      default="45d",      help="Lookback period for RS calculation. Default: 45d")
    parser.add_argument("--mode",        choices=["last_close", "live"], default="last_close",
                        help="last_close = completed daily bars. live = Polygon snapshot latest price.")
    parser.add_argument("--output",      default=None,       help="Output CSV path.")
    parser.add_argument("--polygon-key", default=None,       help="Polygon API key (overrides env/auto-discovery).")
    parser.add_argument("--workers",     default=20, type=int, help="Concurrent fetch threads. Default: 20")
    args = parser.parse_args()

    api_key = args.polygon_key or _find_polygon_api_key()
    if not api_key:
        print(
            "ERROR: No Polygon API key found.\n"
            "Set POLYGON_API_KEY env var, add it to a .env file, or pass --polygon-key.",
            file=sys.stderr,
        )
        return 1

    rows = load_universe(args.tickers)
    if args.benchmark and args.tickers:
        rows = [RowDef(r.section, r.ticker, r.name, r.benchmark or args.benchmark) for r in rows]

    tickers = sorted(set([r.ticker for r in rows] + [r.benchmark for r in rows]))
    period_days = _period_to_days(args.period)

    print(f"Fetching {len(tickers)} tickers from Polygon ({args.workers} workers)…", flush=True)
    close, volume, highs_52w = download_prices_polygon(
        tickers, api_key,
        period_days=period_days,
        workers=args.workers,
    )

    live_last: dict[str, float] = {}
    if args.mode == "live":
        print("Fetching live snapshots…", flush=True)
        live_last = get_live_prices_polygon(tickers, api_key)

    report = build_report(rows, close, volume, live_last=live_last, highs_52w=highs_52w)

    stamp  = datetime.now().strftime("%Y%m%d_%H%M")
    output = args.output or f"rs_premarket_overview_{args.mode}_{stamp}.csv"
    report.to_csv(output, index=False)

    print(f"Wrote {output}")
    print()
    print(report[["Section", "Ticker", "Name", "% Daily Text", "% Monthly Text", "1M RS Δ Text", "1-Month RS Histogram", "Setup", "Status"]].head(25).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
