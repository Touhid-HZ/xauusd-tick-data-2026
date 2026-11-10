#!/usr/bin/env python3
"""
Convert the weekly gzip CSVs into a single Apache Parquet dataset.

Parquet is ~3-5x faster to load than CSV and keeps proper dtypes
(timestamp[ms], float32 prices, float32 volumes).

Usage (from repo root):
    python scripts/examples/convert_to_parquet.py                # -> data/parquet/
    python scripts/examples/convert_to_parquet.py --partitions month

Requires: pip install pandas pyarrow
"""

import argparse
import glob
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
TICK_DIR = os.path.join(REPO, "data", "tick")
OUT_DIR = os.path.join(REPO, "data", "parquet")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--partitions", choices=["none", "month"], default="month",
                    help="partition the parquet dataset by month")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(TICK_DIR, "XAUUSD_2026_w*.csv.gz")))
    if not files:
        raise SystemExit("no weekly tick files found — download the data first")

    os.makedirs(OUT_DIR, exist_ok=True)
    for path in files:
        name = os.path.basename(path).replace(".csv.gz", "")
        df = pd.read_csv(
            path,
            parse_dates=["timestamp"],
            date_format="%Y-%m-%d %H:%M:%S.%f",
        )
        df = df.astype({"ask": "float32", "bid": "float32",
                        "ask_volume": "float32", "bid_volume": "float32"})
        if args.partitions == "month":
            df["month"] = df["timestamp"].dt.strftime("%Y-%m")
            out = os.path.join(OUT_DIR, f"{name}.parquet")
            df.to_parquet(out, index=False, partition_cols=["month"])
        else:
            out = os.path.join(OUT_DIR, f"{name}.parquet")
            df.to_parquet(out, index=False)
        print(f"{name}: {len(df):,} ticks -> {out}")

    print("\nread it back with:")
    print("  import pandas as pd")
    print("  df = pd.read_parquet('data/parquet', "
          "filters=[('month','=','2026-01')])")


if __name__ == "__main__":
    main()
