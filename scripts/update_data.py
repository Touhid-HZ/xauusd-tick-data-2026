#!/usr/bin/env python3
"""
Weekly refresh pipeline used by the GitHub Action (and handy locally).

What it does:
  1. Deletes the two most recent weekly files (to catch late-arriving ticks)
     and re-downloads them plus any brand-new weeks, up to yesterday UTC.
     Week numbering stays anchored to the dataset's original start date,
     so existing files are never misnumbered.
  2. Rebuilds data/daily/XAUUSD_2026_daily_ohlcv.csv
  3. Rebuilds DATA_STATUS.json
  4. Re-renders charts/XAUUSD_2026_daily_close.png

Usage:  python scripts/update_data.py
Requires: requests, pandas, matplotlib  (+ Node.js/npx for the download step)
"""

import datetime as dt
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
TICK_DIR = os.path.join(REPO, "data", "tick")


def main():
    metas = sorted(glob.glob(os.path.join(TICK_DIR, "*.meta.json")))
    if not metas:
        raise SystemExit("no existing data — run the downloader first")

    first = json.load(open(metas[0]))
    dataset_start = first["date_from"]          # e.g. 2026-01-01 (anchor)

    # drop the trailing two weeks so they get re-downloaded fresh
    for meta_path in metas[-2:]:
        gz = meta_path.replace(".meta.json", ".csv.gz")
        print(f"refreshing week file: {os.path.basename(meta_path)}")
        for p in (meta_path, gz):
            if os.path.exists(p):
                os.remove(p)

    target_to = dt.datetime.now(dt.timezone.utc).date().isoformat()  # exclusive
    print(f"updating {dataset_start} -> {target_to} (exclusive)")
    rc = subprocess.run(
        [sys.executable, os.path.join(HERE, "download_weeks_node.py"),
         "--from", dataset_start, "--to", target_to,
         "--work-dir", os.path.join(REPO, "work")]).returncode
    if rc != 0:
        print("WARNING: downloader reported failures — data may be partial")

    for step in ("build_daily_ohlcv.py", "make_chart.py"):
        r = subprocess.run([sys.executable, os.path.join(HERE, step)])
        if r.returncode != 0:
            raise SystemExit(f"{step} failed")

    # keep the work dir small in CI
    for p in glob.glob(os.path.join(REPO, "work", "csv", "*.csv")):
        os.remove(p)

    print("update pipeline finished")


if __name__ == "__main__":
    main()
