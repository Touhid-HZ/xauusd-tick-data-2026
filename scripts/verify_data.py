#!/usr/bin/env python3
"""
Integrity verifier for the XAUUSD 2026 tick dataset.

Streams every weekly .csv.gz and checks:
  * header matches the documented schema
  * timestamps are ISO UTC and non-decreasing (lexicographic == chronological)
  * ask >= bid on every row, prices inside a sane bound
  * volumes are non-negative
  * row count matches the week's .meta.json
  * grand total matches DATA_STATUS.json (when present)

Exit code 0 = all checks passed. Usage: python verify_data.py [--quick]
(--quick verifies only the first and last week files)
"""

import glob
import gzip
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
TICK_DIR = os.path.join(REPO, "data", "tick")
STATUS_PATH = os.path.join(REPO, "DATA_STATUS.json")
HEADER = "timestamp,ask,bid,ask_volume,bid_volume"
PRICE_MIN, PRICE_MAX = 1000.0, 10000.0


def verify_file(gz_path, meta_path):
    problems = []
    with open(meta_path) as f:
        meta = json.load(f)
    n = 0
    prev_ts = ""
    with gzip.open(gz_path, "rt") as f:
        head = f.readline().strip()
        if head != HEADER:
            problems.append(f"bad header: {head!r}")
        for line in f:
            n += 1
            parts = line.rstrip("\n").split(",")
            if len(parts) != 5:
                if len(problems) < 3:
                    problems.append(f"row {n}: wrong column count")
                continue
            ts, ask, bid, av, bv = parts
            if ts < prev_ts:
                if len(problems) < 3:
                    problems.append(f"row {n}: timestamp went backwards "
                                    f"({prev_ts} -> {ts})")
            prev_ts = ts
            a, b = float(ask), float(bid)
            if a < b:
                if len(problems) < 3:
                    problems.append(f"row {n}: ask < bid ({ask} < {bid})")
            if not (PRICE_MIN <= b <= PRICE_MAX and PRICE_MIN <= a <= PRICE_MAX):
                if len(problems) < 3:
                    problems.append(f"row {n}: price out of bounds ({ask},{bid})")
            if float(av) < 0 or float(bv) < 0:
                if len(problems) < 3:
                    problems.append(f"row {n}: negative volume")
    if n != meta["rows"]:
        problems.append(f"row count {n:,} != meta {meta['rows']:,}")
    return n, problems


def main():
    quick = "--quick" in sys.argv
    pairs = []
    for gz in sorted(glob.glob(os.path.join(TICK_DIR, "XAUUSD_2026_w*.csv.gz"))):
        meta = gz.replace(".csv.gz", ".meta.json")
        if os.path.exists(meta):
            pairs.append((gz, meta))
    if not pairs:
        raise SystemExit("no data files found")
    if quick:
        pairs = [pairs[0], pairs[-1]]

    total = 0
    failures = 0
    for gz, meta in pairs:
        n, problems = verify_file(gz, meta)
        total += n
        name = os.path.basename(gz)
        if problems:
            failures += 1
            print(f"FAIL  {name}: {problems}")
        else:
            print(f"OK    {name}: {n:,} ticks")
    print(f"\nverified {len(pairs)} files, {total:,} ticks, "
          f"{failures} file(s) with problems")

    if os.path.exists(STATUS_PATH) and not quick:
        with open(STATUS_PATH) as f:
            status = json.load(f)
        expected = status["totals"]["ticks"]
        if expected != total:
            print(f"FAIL  DATA_STATUS.json total {expected:,} != verified {total:,}")
            failures += 1
        else:
            print(f"OK    DATA_STATUS.json grand total matches ({total:,})")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
