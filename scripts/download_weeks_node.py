#!/usr/bin/env python3
"""
Bulk weekly downloader for XAUUSD tick data — powered by dukascopy-node.

This is the *recommended* bulk path: dukascopy-node
(https://github.com/LeoEichler/dukascopy-node) handles Dukascopy's AWS WAF
and rate limiting robustly. We run it once per 7-day week, then convert its
epoch-millisecond CSV into this repository's weekly schema:

    timestamp,ask,bid,ask_volume,bid_volume   (UTC, ISO "YYYY-MM-DD HH:MM:SS.mmm")

Outputs (per week), identical to scripts/download_ticks.py:
    data/tick/XAUUSD_2026_wNN.csv.gz
    data/tick/XAUUSD_2026_wNN.meta.json

Resumable: completed weeks (gz + meta present) are skipped.

Usage:
    python download_weeks_node.py --from 2026-01-01 --to 2026-11-10 \
        --work-dir ./work          # intermediate CSVs + bi5 cache (safe to delete)

Requires: Node.js >= 16 (npx) and: pip install requests
"""

import argparse
import datetime as dt
import gzip
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from download_ticks import day_stats  # noqa: E402  (shared aggregation logic)


def weeks_between(start, end_exclusive):
    i = 0
    cur = start
    while cur < end_exclusive:
        i += 1
        nxt = cur + dt.timedelta(days=7)
        yield i, cur, min(nxt, end_exclusive)
        cur = nxt


def ms_to_iso(ts_ms):
    sec, msec = divmod(ts_ms, 1000)
    t = dt.datetime.fromtimestamp(sec, tz=dt.timezone.utc)
    return f"{t:%Y-%m-%d %H:%M:%S}.{msec:03d}"


def convert_week(csv_path, gz_path, wstart, wend, gzip_level=9):
    """dukascopy-node CSV (epoch ms) -> repo weekly gz + stats.

    Returns (tmp_path, rows_total, day_aggs, all_prices, missing_weekdays).
    """
    rows_total = 0
    day_aggs = []
    all_prices = []
    cur_rows = []
    cur_date = None
    tmp_path = gz_path + ".tmp"

    def flush_day():
        nonlocal cur_rows, all_prices
        if cur_rows:
            st = day_stats(cur_rows)
            if st:
                day_aggs.append(st)
                all_prices += [st["high"], st["low"]]
            cur_rows = []

    with open(csv_path) as fin, \
            gzip.open(tmp_path, "wt", newline="", compresslevel=gzip_level) as fout:
        fout.write("timestamp,ask,bid,ask_volume,bid_volume\n")
        header = fin.readline()          # timestamp,askPrice,bidPrice,askVolume,bidVolume
        if not header.startswith("timestamp"):
            raise ValueError(f"unexpected header: {header!r}")
        for line in fin:
            ts_s, ask, bid, av, bv = line.rstrip("\n").split(",")
            stamp = ms_to_iso(int(ts_s))
            # normalise volumes to fixed 6 decimals for consistency
            fout.write(f"{stamp},{ask},{bid},{float(av):.6f},{float(bv):.6f}\n")
            d = stamp[:10]
            if d != cur_date:
                flush_day()
                cur_date = d
            cur_rows.append((stamp, ask, bid, av, bv))
            rows_total += 1
        flush_day()

    # a weekday (Mon-Fri) inside the week with zero ticks is worth flagging
    present = {a["date"] for a in day_aggs}
    missing = []
    day = wstart
    while day < wend:
        if day.weekday() < 5 and day.isoformat() not in present:
            missing.append(day.isoformat())
        day += dt.timedelta(days=1)

    return tmp_path, rows_total, day_aggs, all_prices, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="date_from", required=True)
    ap.add_argument("--to", dest="date_to", required=True, help="exclusive (UTC)")
    ap.add_argument("--instrument", default="xauusd")
    ap.add_argument("--out-dir", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "tick"))
    ap.add_argument("--work-dir", default="./work",
                    help="intermediate dukascopy-node CSVs + bi5 cache")
    ap.add_argument("--gzip-level", type=int, default=9)
    ap.add_argument("--bs", type=int, default=12, help="dukascopy-node batch size")
    args = ap.parse_args()

    start = dt.date.fromisoformat(args.date_from)
    end = dt.date.fromisoformat(args.date_to)
    year_tag = start.year
    os.makedirs(args.out_dir, exist_ok=True)
    csv_dir = os.path.join(args.work_dir, "csv")
    cache = os.path.join(args.work_dir, "dcache")
    os.makedirs(csv_dir, exist_ok=True)

    failed, done, warned = [], 0, []
    for widx, wstart, wend in weeks_between(start, end):
        gz_name = f"XAUUSD_{year_tag}_w{widx:02d}.csv.gz"
        gz_path = os.path.join(args.out_dir, gz_name)
        meta_path = os.path.join(args.out_dir,
                                 gz_name.replace(".csv.gz", ".meta.json"))
        if os.path.exists(gz_path) and os.path.exists(meta_path):
            done += 1
            continue

        s, e = f"{wstart:%Y-%m-%d}", f"{wend:%Y-%m-%d}"
        print(f"[w{widx:02d}] {s} -> {e}: dukascopy-node ...", flush=True)
        cmd = ["npx", "-y", "dukascopy-node", "-i", args.instrument,
               "-from", s, "-to", e, "-t", "tick", "-f", "csv", "-v",
               "-dir", csv_dir, "-bs", str(args.bs), "--request-interval", "100",
               "-r", "4", "-ch", "-chpath", cache]
        t0 = __import__("time").time()
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              cwd=os.path.dirname(os.path.abspath(__file__)))
        csv_path = os.path.join(csv_dir, f"{args.instrument}-tick-{s}-{e}.csv")
        if proc.returncode != 0 or not os.path.exists(csv_path):
            print(f"[w{widx:02d}] dukascopy-node FAILED (exit {proc.returncode}). "
                  f"stderr tail: {proc.stderr.strip()[-300:]}", flush=True)
            failed.append(widx)
            continue

        tmp_path, rows, day_aggs, all_prices, missing = convert_week(
            csv_path, gz_path, wstart, wend, args.gzip_level)
        if not day_aggs:
            print(f"[w{widx:02d}] WARNING: no data rows at all — skipped",
                  flush=True)
            os.remove(tmp_path)
            failed.append(widx)
            continue
        os.replace(tmp_path, gz_path)
        size = os.path.getsize(gz_path)
        meta = {
            "file": gz_name,
            "instrument": "XAUUSD",
            "week_index": widx,
            "date_from": s,
            "date_to_exclusive": e,
            "rows": rows,
            "compressed_bytes": size,
            "first_tick_utc": day_aggs[0]["first_tick"],
            "last_tick_utc": day_aggs[-1]["last_tick"],
            "trading_days": len(day_aggs),
            "price_high": round(max(all_prices), 3),
            "price_low": round(min(all_prices), 3),
            "days": day_aggs,
            "source": "Dukascopy Bank SA public data feed via dukascopy-node",
            "schema": "timestamp,ask,bid,ask_volume,bid_volume (UTC, ms)",
        }
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=1)
        os.remove(csv_path)
        done += 1
        for d in missing:
            warned.append(f"w{widx:02d}:{d}")
        print(f"[w{widx:02d}] done: {rows:,} ticks, {size / 1e6:.1f} MB gz, "
              f"{__import__('time').time() - t0:.0f}s"
              + (f"  [zero-tick weekdays: {missing}]" if missing else ""),
              flush=True)

    print(f"\nFinished: {done} weeks done this run, {len(failed)} failed "
          f"({failed if failed else 'none'}).", flush=True)
    if warned:
        print(f"Zero-tick weekdays (holidays expected): {warned}", flush=True)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
