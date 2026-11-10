#!/usr/bin/env python3
"""
Quick-start examples for the XAUUSD 2026 tick dataset (pandas).

Covers:
  1. loading one weekly tick file
  2. computing the instantaneous spread
  3. resampling ticks into 1-minute OHLCV candles (mid price)
  4. loading the whole year lazily (chunked) to count ticks or filter dates

Run from the repo root:   python scripts/examples/load_and_resample.py
"""

import glob
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
TICK_DIR = os.path.join(REPO, "data", "tick")


def load_week(week="w01"):
    """Load a single weekly tick file (gzip is handled transparently)."""
    path = os.path.join(TICK_DIR, f"XAUUSD_2026_{week}.csv.gz")
    df = pd.read_csv(
        path,
        parse_dates=["timestamp"],
        date_format="%Y-%m-%d %H:%M:%S.%f",   # millisecond precision
    )
    return df


def main():
    # ---- 1. load one week -----------------------------------------------
    df = load_week("w05")          # one of the busiest weeks of the year
    print(f"week w05: {len(df):,} ticks "
          f"({df.timestamp.iloc[0]} -> {df.timestamp.iloc[-1]})")
    print(df.head(3).to_string(index=False))

    # ---- 2. spread -------------------------------------------------------
    df["spread"] = df["ask"] - df["bid"]
    print(f"\nspread: mean={df.spread.mean():.3f} USD, "
          f"median={df.spread.median():.3f}, max={df.spread.max():.2f}")

    # ---- 3. 1-minute OHLCV from ticks (mid price) ------------------------
    df = df.set_index("timestamp")
    df["mid"] = (df["ask"] + df["bid"]) / 2
    ohlc = df["mid"].resample("1min").ohlc()
    ohlc["volume_m"] = (df["ask_volume"] + df["bid_volume"]).resample("1min").sum()
    ohlc = ohlc.dropna()
    print("\n1-minute candles (first 3):")
    print(ohlc.head(3).to_string())

    # other granularities work the same way:
    #   df["mid"].resample("5min").ohlc()
    #   df["mid"].resample("1h").ohlc()
    #   df["mid"].resample("1D").ohlc()

    # ---- 4. whole-year streaming (never loads 79M rows at once) ----------
    total = 0
    for path in sorted(glob.glob(os.path.join(TICK_DIR, "XAUUSD_2026_w*.csv.gz"))):
        for chunk in pd.read_csv(path, chunksize=2_000_000,
                                 usecols=["timestamp", "ask", "bid"]):
            # example filter: keep only Jan 2026, then aggregate what you need
            total += len(chunk)
    print(f"\nstreamed the whole year: {total:,} ticks")


if __name__ == "__main__":
    main()
