#!/usr/bin/env python3
"""
XAUUSD (Gold/USD) tick data downloader — Dukascopy public data feed -> weekly CSV.gz

Downloads hourly .bi5 tick archives from Dukascopy Bank SA's public data feed
(https://datafeed.dukascopy.com), decodes them, and writes weekly
gzip-compressed CSV files with the schema:

    timestamp,ask,bid,ask_volume,bid_volume

- timestamp : UTC (GMT), millisecond precision, "YYYY-MM-DD HH:MM:SS.mmm"
- ask, bid  : USD per troy ounce, 3 decimal places
- volumes   : Dukascopy convention — millions of units (0.00012 = 120 units)

Each output week spans 7 days starting at --from:
    XAUUSD_2026_w01.csv.gz -> 2026-01-01 .. 2026-01-07
    XAUUSD_2026_w02.csv.gz -> 2026-01-08 .. 2026-01-14   (and so on)
A sidecar .meta.json is written next to every completed week with per-day
and per-week statistics (rows, OHLC, volumes, spread).

Resumable: a week is skipped when both its .csv.gz and .meta.json exist.
Weeks with failed hours are re-downloaded on the next run.

Usage:
    python download_ticks.py --from 2026-01-01 --to 2026-11-10 \
        --out-dir ../data/tick --workers 10

Requires: pip install requests
"""

import argparse
import datetime as dt
import gzip
import json
import lzma
import os
import struct
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

BASE_URL = ("https://datafeed.dukascopy.com/datafeed/{instrument}/{year}/"
            "{month:02d}/{day:02d}/{hour:02d}h_ticks.bi5")
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
RECORD = struct.Struct(">IIIff")   # ms-offset, ask, bid, askVol, bidVol
POINT = 0.001                      # XAUUSD price scale (1/1000)
MAX_ATTEMPTS = 8

_tls = threading.local()

# ---- global request throttle: at most MIN_INTERVAL_S between request starts
_throttle_lock = threading.Lock()
_throttle_next = 0.0
MIN_INTERVAL_S = 0.085          # ~12 requests/sec ceiling


def throttle():
    global _throttle_next
    while True:
        with _throttle_lock:
            now = time.monotonic()
            wait = _throttle_next - now
            if wait <= 0:
                _throttle_next = now + MIN_INTERVAL_S
                return
        time.sleep(wait)


def get_session():
    """One requests.Session per worker thread (connection reuse)."""
    if not hasattr(_tls, "session"):
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT})
        _tls.session = s
    return _tls.session


def hours_to_probe(day):
    """Gold trades ~Sun 22:00 UTC -> Fri 22:00 UTC. Trim impossible hours."""
    wd = day.weekday()
    if wd == 5:                    # Saturday — market closed
        return []
    if wd == 6:                    # Sunday — only late GMT hours can exist
        return range(18, 24)
    return range(0, 24)            # Monday..Friday


def fmt_price(raw):
    """Integer x1000 -> exact decimal string (no float rounding artifacts)."""
    return f"{raw // 1000}.{raw % 1000:03d}"


def fetch_hour(instrument, day, hour):
    """Download + decode one hourly bi5 archive.

    Returns list of row tuples [(ts, ask, bid, av, bv), ...] as strings,
    [] when the hour legitimately has no data, or None on failure.
    """
    url = BASE_URL.format(instrument=instrument, year=day.year,
                          month=day.month - 1, day=day.day, hour=hour)  # month is 0-based!
    base_ms = int(dt.datetime(day.year, day.month, day.day, hour,
                              tzinfo=dt.timezone.utc).timestamp() * 1000)
    day_prefix = f"{day:%Y-%m-%d} "

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            throttle()
            r = get_session().get(url, timeout=30)
            if r.status_code == 404:
                return []                       # no data for this hour
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(5 * attempt)             # rate limited / server busy
                continue
            r.raise_for_status()
            raw = r.content
            if not raw:
                return []
            data = lzma.decompress(raw)
            if len(data) % RECORD.size != 0:
                raise ValueError(f"bi5 size {len(data)} not multiple of 20")
            n = len(data) // RECORD.size
            rows = []
            for i in range(n):
                ms, ask, bid, av, bv = RECORD.unpack_from(data, i * RECORD.size)
                stamp = (f"{day_prefix}{hour:02d}:{ms // 60000:02d}:"
                         f"{(ms % 60000) // 1000:02d}.{ms % 1000:03d}")
                rows.append((stamp, fmt_price(ask), fmt_price(bid),
                             f"{av:.6f}", f"{bv:.6f}"))
            rows.sort(key=lambda x: x[0])
            return rows
        except Exception as e:
            if attempt == MAX_ATTEMPTS:
                print(f"    FAILED {day} {hour:02d}h after {MAX_ATTEMPTS} "
                      f"attempts: {type(e).__name__}: {e}", flush=True)
                return None
            time.sleep(min(attempt * 2, 15))
    return None


def download_day(pool, instrument, day):
    """Fetch every probe-able hour of one day. Returns (rows, failed_hours)."""
    rows, failed = [], []
    futures = {pool.submit(fetch_hour, instrument, day, h): h
               for h in hours_to_probe(day)}
    for fut in as_completed(futures):
        h = futures[fut]
        result = fut.result()
        if result is None:
            failed.append(h)
        else:
            rows.extend(result)
    rows.sort(key=lambda x: x[0])
    return rows, failed


def day_stats(rows):
    """Aggregate one day's rows for the meta sidecar (mid-price OHLC)."""
    if not rows:
        return None
    mids = [(float(r[1]) + float(r[2])) / 2 for r in rows]
    spreads = [float(r[1]) - float(r[2]) for r in rows]
    return {
        "date": rows[0][0][:10],
        "ticks": len(rows),
        "first_tick": rows[0][0],
        "last_tick": rows[-1][0],
        "open": round(mids[0], 3),
        "high": round(max(mids), 3),
        "low": round(min(mids), 3),
        "close": round(mids[-1], 3),
        "ask_volume_m": round(sum(float(r[3]) for r in rows), 6),
        "bid_volume_m": round(sum(float(r[4]) for r in rows), 6),
        "avg_spread": round(sum(spreads) / len(spreads), 4),
    }


def weeks_between(start, end_exclusive):
    """Yield (index, week_start_date, week_end_exclusive_date)."""
    i = 0
    cur = start
    while cur < end_exclusive:
        i += 1
        nxt = cur + dt.timedelta(days=7)
        yield i, cur, min(nxt, end_exclusive)
        cur = nxt


def main():
    ap = argparse.ArgumentParser(description="Dukascopy tick downloader")
    ap.add_argument("--instrument", default="XAUUSD")
    ap.add_argument("--from", dest="date_from", required=True,
                    help="start date YYYY-MM-DD (inclusive, UTC)")
    ap.add_argument("--to", dest="date_to", required=True,
                    help="end date YYYY-MM-DD (exclusive, UTC)")
    ap.add_argument("--out-dir", default="../data/tick")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--gzip-level", type=int, default=9)
    args = ap.parse_args()

    start = dt.date.fromisoformat(args.date_from)
    end_exclusive_day = dt.date.fromisoformat(args.date_to)
    year_tag = start.year
    os.makedirs(args.out_dir, exist_ok=True)

    total_failed_weeks = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for widx, wstart, wend in weeks_between(start, end_exclusive_day):
            gz_name = f"{args.instrument}_{year_tag}_w{widx:02d}.csv.gz"
            gz_path = os.path.join(args.out_dir, gz_name)
            meta_path = os.path.join(
                args.out_dir, gz_name.replace(".csv.gz", ".meta.json"))
            if os.path.exists(gz_path) and os.path.exists(meta_path):
                print(f"[w{widx:02d}] {wstart} -> {wend}: already done, skip",
                      flush=True)
                continue

            t0 = time.time()
            print(f"[w{widx:02d}] {wstart} -> {wend}: downloading ...",
                  flush=True)
            tmp_path = gz_path + ".tmp"
            week_rows = 0
            failed_hours = []
            day_aggs = []
            all_prices = []
            with gzip.open(tmp_path, "wt", newline="", compresslevel=args.gzip_level) as f:
                f.write("timestamp,ask,bid,ask_volume,bid_volume\n")
                day = wstart
                while day < wend:
                    rows, failed = download_day(pool, args.instrument, day)
                    failed_hours += [f"{day:%Y-%m-%d} {h:02d}h" for h in failed]
                    for r in rows:
                        f.write(",".join(r) + "\n")
                    week_rows += len(rows)
                    st = day_stats(rows)
                    if st:
                        day_aggs.append(st)
                        all_prices += [st["high"], st["low"]]
                    print(f"    {day} : {len(rows):7d} ticks"
                          + (f"  ({len(failed)} failed)" if failed else ""),
                          flush=True)
                    day += dt.timedelta(days=1)

            if failed_hours:
                os.remove(tmp_path)
                print(f"[w{widx:02d}] INCOMPLETE — {len(failed_hours)} failed "
                      f"hours: {failed_hours[:5]} ... week will be retried",
                      flush=True)
                total_failed_weeks += 1
                continue

            os.replace(tmp_path, gz_path)
            size = os.path.getsize(gz_path)
            first_ts = day_aggs[0]["first_tick"] if day_aggs else None
            last_ts = day_aggs[-1]["last_tick"] if day_aggs else None
            meta = {
                "file": gz_name,
                "instrument": args.instrument,
                "week_index": widx,
                "date_from": f"{wstart:%Y-%m-%d}",
                "date_to_exclusive": f"{wend:%Y-%m-%d}",
                "rows": week_rows,
                "compressed_bytes": size,
                "first_tick_utc": first_ts,
                "last_tick_utc": last_ts,
                "trading_days": len(day_aggs),
                "price_high": round(max(all_prices), 3) if all_prices else None,
                "price_low": round(min(all_prices), 3) if all_prices else None,
                "days": day_aggs,
                "source": "Dukascopy Bank SA public data feed (bi5, decoded)",
                "schema": "timestamp,ask,bid,ask_volume,bid_volume (UTC, ms)",
            }
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=1)
            print(f"[w{widx:02d}] done: {week_rows:,} ticks, "
                  f"{size / 1e6:.1f} MB gz, {time.time() - t0:.0f}s",
                  flush=True)

    if total_failed_weeks:
        print(f"\n{total_failed_weeks} week(s) incomplete — re-run this "
              f"script to retry them.", flush=True)
        sys.exit(1)
    print("\nAll weeks complete.", flush=True)


if __name__ == "__main__":
    main()
