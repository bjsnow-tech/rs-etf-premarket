#!/usr/bin/env python3
# Thin shim — entry point moved to src/rs_etf_premarket/cli.py
# Install the package (`pip install -e .`) and use the `rs-premarket` command instead.
from rs_etf_premarket.cli import main
import sys

if __name__ == "__main__":
    raise SystemExit(main())
