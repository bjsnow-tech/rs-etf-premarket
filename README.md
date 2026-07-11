# RS ETF Premarket

Builds a relative-strength "premarket overview" dashboard CSV across a broad universe of
ETFs and stocks — indices, size/style segments, equal-weight and SPDR sector ETFs, industry
groups, and a handful of individual names — all measured against a benchmark (default: SPY).

Pulls daily OHLCV data from [Polygon.io](https://polygon.io) for every ticker concurrently,
computes relative-strength deltas and thrust, and flags tickers with an improving RS trend as
"Setups." An included `visualize.py` script renders the CSV as a dark-themed HTML dashboard.

## Features

- **Broad default universe**: indices, size/style segments, equal-weight sector ETFs, SPDR
  sector ETFs, dozens of industry-group ETFs, and select individual stocks
- Computes % daily / % monthly return, 1-month RS delta, RS thrust rate (short-term RS
  acceleration), % off 52-week high, and a compact text histogram of the trailing RS trend
- **Setup flag**: marks tickers where 1-month RS is improving and the stock isn't down hard
  today — an actionable relative-strength signal
- **`last_close` mode**: uses completed daily bars
- **`live` mode**: overlays a Polygon snapshot for the latest pre/post-market or intraday price
- Custom universe support via a `Section,Ticker,Name,Benchmark` CSV
- `visualize.py`: renders any output CSV as a styled, sectioned HTML dashboard

## Project layout

```text
rs-etf-premarket/
├── README.md
├── LICENSE
├── pyproject.toml
├── rs_premarket_csv.py                        ← thin shim to the rs-premarket entry point
├── visualize.py                               ← CSV → HTML dashboard renderer
├── rs_custom_universe_template.csv            ← minimal custom-universe example
├── premarket_overview_universe_template.csv   ← full default-style universe template
├── src/
│   └── rs_etf_premarket/
│       ├── __init__.py
│       └── cli.py       ← entry point, Polygon fetch, RS computation
└── tests/
```

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv sync
```

## Configuration

Copy `.env.example` to `.env` and add your Polygon API key:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `POLYGON_API_KEY` | Yes (or pass `--polygon-key`) | Polygon.io API key for OHLCV and snapshot data |

## Usage

### Default universe

```bash
rs-premarket
```

Fetches ~1 year of daily bars for the full default universe (see `cli.py`'s `DEFAULT_UNIVERSE`),
computes RS metrics vs. each row's benchmark (SPY by default), and writes a timestamped CSV.

### Live / intraday proxy

Overlay the latest Polygon snapshot price instead of the last completed daily bar:

```bash
rs-premarket --mode live
```

### Custom universe

Provide your own `Section,Ticker,Name,Benchmark` CSV (see `rs_custom_universe_template.csv` for
the minimal format, or `premarket_overview_universe_template.csv` for the full default-style
layout):

```bash
rs-premarket --tickers my_universe.csv
```

### Other options

```bash
rs-premarket --benchmark QQQ          # default benchmark for rows that omit one
rs-premarket --period 90d             # RS lookback window (default: 45d)
rs-premarket --output my_report.csv   # custom output path
rs-premarket --workers 30             # concurrent fetch threads (default: 20)
rs-premarket --polygon-key <key>      # override env/`.env` key discovery
```

Run `rs-premarket --help` for the full option list.

### Visualizing results

```bash
python visualize.py rs_premarket_overview_last_close_20260710_1605.csv
```

Renders a dark-themed HTML dashboard grouped by section (writes to `html/<name>.html` next to
the CSV by default, or pass `--output` for a custom path).

## Output columns

Each row includes: `Section`, `Ticker`, `Name`, `Benchmark`, `% Daily`, `% Monthly`,
`1M RS Δ` (1-month relative-strength change), `1M RS %` (percentile rank within its section),
`RS Thrust Rate` / `1W RS Thrust` (short-term RS acceleration), `% Off 52W High`,
`1-Month RS Histogram` (compact trailing-trend sparkline), `RS High In Window`, and
`Setup` / `Status` flags.

## Notes

RS metrics are computed directly from Polygon daily bars, not sourced from a third-party rating
service — treat the "Setup" flag as a starting point for further research, not a standalone
signal.

## License

MIT — see [LICENSE](LICENSE).
