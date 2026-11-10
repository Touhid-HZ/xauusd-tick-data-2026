#!/usr/bin/env python3
"""
Merge the weekly .csv.gz tick files into ONE plain CSV for MetaTrader 5.

MetaTrader cannot read gzip, so this produces an uncompressed CSV
(MQL5-friendly, same schema) named XAUUSD_2026_ALL.csv by default.
Expected output size: ~3.5 GB for the full year — make sure you have room,
or pass --weeks to merge a subset.

Usage (from repo root):
    python scripts/metatrader/prepare_csv.py                     # all weeks
    python scripts/metatrader/prepare_csv.py --weeks w01 w02 w03 # subset
    python scripts/metatrader/prepare_csv.py --out XAUUSD_2026_ALL.csv
"""

import argparse
import glob
import gzip
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
TICK_DIR = os.path.join(REPO, "data", "tick")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", nargs="*", default=None,
                    help="week ids to merge, e.g. w01 w02 (default: all)")
    ap.add_argument("--out", default="XAUUSD_2026_ALL.csv")
    args = ap.parse_args()

    if args.weeks:
        files = [os.path.join(TICK_DIR, f"XAUUSD_2026_{w}.csv.gz")
                 for w in args.weeks]
    else:
        files = sorted(glob.glob(os.path.join(TICK_DIR, "XAUUSD_2026_w*.csv.gz")))
    files = [f for f in files if os.path.exists(f)]
    if not files:
        raise SystemExit("no tick files found")

    out_path = os.path.join(os.getcwd(), args.out)
    n = 0
    with open(out_path, "w", newline="\n") as fout:
        fout.write("timestamp,ask,bid,ask_volume,bid_volume\n")
        for path in files:
            with gzip.open(path, "rt") as fin:
                for line in fin:
                    fout.write(line)
                    n += 1
            print(f"merged {os.path.basename(path)} (total {n:,} ticks)")
    size_gb = os.path.getsize(out_path) / 1e9
    print(f"\nwrote {out_path}: {n:,} ticks, {size_gb:.2f} GB")
    print("next: copy it to  <MT5 data folder>\\MQL5\\Files\\  and run "
          "ImportXAUUSDTicks.mq5")


if __name__ == "__main__":
    main()
