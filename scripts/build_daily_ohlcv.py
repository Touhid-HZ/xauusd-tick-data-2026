#!/usr/bin/env python3
"""
Build the daily OHLCV file and DATA_STATUS.json from the weekly meta sidecars.

Reads every data/tick/XAUUSD_2026_wNN.meta.json, merges the per-day
aggregates, and writes:

  data/daily/XAUUSD_2026_daily_ohlcv.csv   — one row per day with ticks
  DATA_STATUS.json                          — machine-readable dataset summary

Usage:  python build_daily_ohlcv.py
"""

import datetime as dt
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
TICK_DIR = os.path.join(REPO, "data", "tick")
DAILY_DIR = os.path.join(REPO, "data", "daily")
STATUS_PATH = os.path.join(REPO, "DATA_STATUS.json")

SCHEMA = {
    "timestamp": "string, UTC, 'YYYY-MM-DD HH:MM:SS.mmm' (millisecond precision)",
    "ask": "float, USD per troy ounce, 3 decimals",
    "bid": "float, USD per troy ounce, 3 decimals",
    "ask_volume": "float, millions of units (Dukascopy convention)",
    "bid_volume": "float, millions of units (Dukascopy convention)",
}


def load_metas():
    out = []
    for p in sorted(glob.glob(os.path.join(TICK_DIR, "*.meta.json"))):
        with open(p) as f:
            out.append(json.load(f))
    return out


def build_daily(metas):
    days = {}
    for m in metas:
        for d in m["days"]:
            days[d["date"]] = d          # later weeks overwrite nothing (unique dates)
    os.makedirs(DAILY_DIR, exist_ok=True)
    out_path = os.path.join(DAILY_DIR, "XAUUSD_2026_daily_ohlcv.csv")
    with open(out_path, "w") as f:
        f.write("date,open,high,low,close,ticks,ask_volume_m,bid_volume_m,avg_spread\n")
        for date in sorted(days):
            d = days[date]
            f.write(f"{d['date']},{d['open']},{d['high']},{d['low']},{d['close']},"
                    f"{d['ticks']},{d['ask_volume_m']},{d['bid_volume_m']},"
                    f"{d['avg_spread']}\n")
    return out_path, days


def build_status(metas, days):
    total_rows = sum(m["rows"] for m in metas)
    total_bytes = sum(m["compressed_bytes"] for m in metas)
    weekdays = sum(1 for d in days if dt.date.fromisoformat(d).weekday() < 5)
    sundays = sum(1 for d in days if dt.date.fromisoformat(d).weekday() == 6)
    price_low = min(m["price_low"] for m in metas)
    price_high = max(m["price_high"] for m in metas)
    status = {
        "dataset": "XAUUSD tick-by-tick historical data (2026) — spot gold vs US dollar",
        "instrument": "XAUUSD (Spot Gold / US Dollar, OTC)",
        "source": "Dukascopy Bank SA public data feed (https://datafeed.dukascopy.com), decoded via dukascopy-node + custom decoder, cross-validated row-by-row",
        "timezone": "UTC (GMT)",
        "schema": SCHEMA,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "coverage": {
            "from": metas[0]["date_from"],
            "to_exclusive": metas[-1]["date_to_exclusive"],
            "first_tick_utc": metas[0]["first_tick_utc"],
            "last_tick_utc": metas[-1]["last_tick_utc"],
        },
        "totals": {
            "ticks": total_rows,
            "days_with_ticks": len(days),
            "weekdays_with_ticks": weekdays,
            "sundays_with_ticks": sundays,
            "weekly_files": len(metas),
            "compressed_bytes": total_bytes,
            "compressed_mb": round(total_bytes / 1e6, 1),
        },
        "price_range_usd_per_oz": {"low": price_low, "high": price_high},
        "files": [
            {
                "file": m["file"],
                "week": m["week_index"],
                "date_from": m["date_from"],
                "date_to_exclusive": m["date_to_exclusive"],
                "rows": m["rows"],
                "compressed_bytes": m["compressed_bytes"],
                "first_tick_utc": m["first_tick_utc"],
                "last_tick_utc": m["last_tick_utc"],
            }
            for m in metas
        ],
        "daily_ohlcv": "data/daily/XAUUSD_2026_daily_ohlcv.csv",
        "update_policy": "GitHub Action refreshes the dataset every Monday ~03:00 UTC (re-downloads trailing weeks, appends new ones)",
        "license": "MIT (code and packaging); data belongs to its original source and is provided as-is for research/education",
    }
    with open(STATUS_PATH, "w") as f:
        json.dump(status, f, indent=1)
    return status


def main():
    metas = load_metas()
    if not metas:
        raise SystemExit("no meta files found — run the downloader first")
    out_path, days = build_daily(metas)
    status = build_status(metas, days)
    print(f"daily ohlcv : {out_path} ({len(days)} days)")
    print(f"status file : {STATUS_PATH}")
    print(f"ticks total : {status['totals']['ticks']:,}")
    print(f"size        : {status['totals']['compressed_mb']} MB gz")
    print(f"price range : {price['low']} – {price['high']} USD/oz"
          if (price := status["price_range_usd_per_oz"]) else "")


if __name__ == "__main__":
    main()
