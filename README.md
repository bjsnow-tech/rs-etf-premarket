# RS ETF Premarket & Finviz Screeners

Two companion tools for a daily relative-strength / screener workflow:

- **`rs-premarket`** — builds a relative-strength "premarket overview" dashboard CSV across a
  broad universe of ETFs and stocks, measured against a benchmark (default: SPY)
- **`finviz_screeners`** — runs a set of saved Finviz Elite screener exports on a schedule and
  filters the resulting tickers by trailing weekly performance

They're independent (neither imports the other) but pair naturally: run the Finviz screeners
to source candidate lists, then use `rs-premarket` to rank relative strength across your own
universe, or vice versa.

![RS Premarket dashboard demo](docs/dashboard_demo.gif)

`visualize.py`'s HTML dashboard output — real ETF/sector data, heatmapped % columns and inline
RS trend sparklines. Static screenshot: [`docs/dashboard_screenshot.png`](docs/dashboard_screenshot.png).

## Project layout

```text
rs-etf-premarket/
├── README.md
├── LICENSE
├── .env.example                                ← shared: POLYGON_API_KEY, FINVIZ_AUTH_TOKEN
├── pyproject.toml                              ← rs-premarket package
├── rs_premarket_csv.py                         ← thin shim to the rs-premarket entry point
├── visualize.py                                ← CSV → HTML dashboard renderer
├── rs_custom_universe_template.csv             ← minimal custom-universe example
├── premarket_overview_universe_template.csv    ← full default-style universe template
├── src/
│   └── rs_etf_premarket/
│       ├── __init__.py
│       └── cli.py       ← entry point, Polygon fetch, RS computation
└── finviz_screeners/
    ├── requirements.txt
    ├── screeners.yaml                    ← named Finviz Elite export URLs
    ├── run_screeners.py                  ← fetches each screener, saves dated CSVs + tickers.txt
    ├── weekly_range_filter.py            ← filters a day's tickers by trailing weekly performance
    └── trend_confirmation_filter.py      ← further filters those by 50/200 SMA trend + ATR distance
```

## Configuration

Copy `.env.example` to `.env` and fill in your keys — both tools read from the same root
`.env`:

```bash
cp .env.example .env
```

| Variable | Used by | Description |
|---|---|---|
| `POLYGON_API_KEY` | `rs-premarket` | Polygon.io API key for OHLCV and snapshot data (or pass `--polygon-key`) |
| `FINVIZ_AUTH_TOKEN` | `finviz_screeners` | Finviz Elite auth token (Account → API) |

---

## RS ETF Premarket

Builds a relative-strength "premarket overview" dashboard CSV across a broad universe of
ETFs and stocks — indices, size/style segments, equal-weight and SPDR sector ETFs, industry
groups, and a handful of individual names — all measured against a benchmark (default: SPY).

Pulls daily OHLCV data from [Polygon.io](https://polygon.io) for every ticker concurrently,
computes relative-strength deltas and thrust, and flags tickers with an improving RS trend as
"Setups." An included `visualize.py` script renders the CSV as a dark-themed HTML dashboard.

### Features

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

### Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv sync
```

### Usage

**Default universe:**

```bash
rs-premarket
```

Fetches ~1 year of daily bars for the full default universe (see `cli.py`'s `DEFAULT_UNIVERSE`),
computes RS metrics vs. each row's benchmark (SPY by default), and writes a timestamped CSV.

**Live / intraday proxy** — overlay the latest Polygon snapshot price instead of the last
completed daily bar:

```bash
rs-premarket --mode live
```

**Custom universe** — provide your own `Section,Ticker,Name,Benchmark` CSV (see
`rs_custom_universe_template.csv` for the minimal format, or
`premarket_overview_universe_template.csv` for the full default-style layout):

```bash
rs-premarket --tickers my_universe.csv
```

**Other options:**

```bash
rs-premarket --benchmark QQQ          # default benchmark for rows that omit one
rs-premarket --period 90d             # RS lookback window (default: 45d)
rs-premarket --output my_report.csv   # custom output path
rs-premarket --workers 30             # concurrent fetch threads (default: 20)
rs-premarket --polygon-key <key>      # override env/`.env` key discovery
```

Run `rs-premarket --help` for the full option list.

**Visualizing results:**

```bash
python visualize.py rs_premarket_overview_last_close_20260710_1605.csv
```

Renders a dark-themed HTML dashboard grouped by section (writes to `html/<name>.html` next to
the CSV by default, or pass `--output` for a custom path). See the demo GIF and screenshot at
the top of this README for what the output looks like.

### Output columns

Each row includes: `Section`, `Ticker`, `Name`, `Benchmark`, `% Daily`, `% Monthly`,
`1M RS Δ` (1-month relative-strength change), `1M RS %` (percentile rank within its section),
`RS Thrust Rate` / `1W RS Thrust` (short-term RS acceleration), `% Off 52W High`,
`1-Month RS Histogram` (compact trailing-trend sparkline), `RS High In Window`, and
`Setup` / `Status` flags.

RS metrics are computed directly from Polygon daily bars, not sourced from a third-party rating
service — treat the "Setup" flag as a starting point for further research, not a standalone
signal.

---

## Finviz Screeners

Runs a set of named Finviz Elite screener exports (defined in `screeners.yaml`) and saves each
one as a dated CSV, plus a combined `tickers.txt` grouped by screener. A second script,
`weekly_range_filter.py`, reads that `tickers.txt` and reports which tickers' trailing weekly
performance falls within a target range — useful for finding names that have consolidated
rather than run away.

### Install

```bash
pip install -r finviz_screeners/requirements.txt
```

### Usage

**Run all screeners** (requires a Finviz **Elite** subscription and auth token):

```bash
cd finviz_screeners
python run_screeners.py
```

Saves each screener to `results/<YYYY-MM-DD>/<screener_name>.csv`, plus
`results/<YYYY-MM-DD>/tickers.txt` (all tickers, grouped by screener section).

```bash
python run_screeners.py --screener qullamaggie_1_month   # run a single screener
python run_screeners.py --output-dir custom_dir          # override output directory
python run_screeners.py --config my_screeners.yaml        # use a different screener config
```

Add or edit screeners directly in `screeners.yaml` — each entry is a `name` and a Finviz Elite
`export.ashx` `url` with `{token}` as a placeholder for `FINVIZ_AUTH_TOKEN`.

**Filter by trailing weekly performance:**

```bash
python weekly_range_filter.py                    # today, -5% to +5%
python weekly_range_filter.py --date 2026-07-08
python weekly_range_filter.py --min -3 --max 3
python weekly_range_filter.py --no-save          # print only, skip the markdown write
```

Reads `results/<date>/tickers.txt`, fetches each unique ticker's weekly performance from
Finviz, and prints (and optionally saves to `daily_insights/<date>/<date>_weekly_range_filter.md`)
a report grouped by originating screener section. Sample output:
[`docs/weekly_range_filter_demo.md`](docs/weekly_range_filter_demo.md).

**Trend confirmation (second-stage filter):**

```bash
python trend_confirmation_filter.py                    # today, same weekly band as above
python trend_confirmation_filter.py --date 2026-07-08
python trend_confirmation_filter.py --atr-mult 5        # looser trend-distance cap
python trend_confirmation_filter.py --no-save
```

Re-applies the weekly compression filter, then — for Polygon.io daily bars — keeps only
tickers that are above both their 50-day and 200-day SMA and within `--atr-mult` (default 3)
ATR(14)s of the 50-day SMA. This confirms an established uptrend that hasn't already run too
far from its trend line. Requires `POLYGON_API_KEY` in `.env` in addition to
`FINVIZ_AUTH_TOKEN`. Saves to
`daily_insights/<date>/<date>_trend_confirmation_filter.md` (or `..._atr{N}.md` when
`--atr-mult` isn't the default) in the same comma-delimited, per-section table format as
`weekly_range_filter.py`. Sample output:
[`docs/trend_confirmation_filter_demo.md`](docs/trend_confirmation_filter_demo.md).

### Notes

Finviz Elite enforces rate limits on export requests — `run_screeners.py` sleeps 3 seconds
between screeners, and `weekly_range_filter.py` batches ticker lookups (150 per request) with a
1-second pause between batches.

---

## License

MIT — see [LICENSE](LICENSE).
