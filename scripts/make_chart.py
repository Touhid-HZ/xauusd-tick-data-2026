#!/usr/bin/env python3
"""
Render the README overview chart: XAUUSD daily close (mid price) for 2026.

Reads data/daily/XAUUSD_2026_daily_ohlcv.csv and writes
charts/XAUUSD_2026_daily_close.png

Usage:  python make_chart.py   (requires matplotlib, pandas)
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DAILY = os.path.join(REPO, "data", "daily", "XAUUSD_2026_daily_ohlcv.csv")
OUT = os.path.join(REPO, "charts", "XAUUSD_2026_daily_close.png")


def main():
    df = pd.read_csv(DAILY, parse_dates=["date"])
    fig, ax = plt.subplots(figsize=(11, 5.2), dpi=150, constrained_layout=True)
    ax.plot(df["date"], df["close"], color="#C9A227", linewidth=1.6)
    ax.fill_between(df["date"], df["close"], df["close"].min() * 0.0 + df["close"].min(),
                    color="#C9A227", alpha=0.08)
    lo, hi = df["low"].min(), df["high"].max()
    ax.set_title("XAUUSD — Spot Gold 2026, Daily Close (UTC, mid price)",
                 fontsize=13, fontweight="bold")
    ax.set_ylabel("USD per troy ounce")
    ax.set_xlabel(f"Data: Dukascopy tick-by-tick, {len(df):,} trading days — "
                  f"range ${lo:,.0f} to ${hi:,.0f}")
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.grid(True, alpha=0.25)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fig.savefig(OUT)
    print("chart saved:", OUT)


if __name__ == "__main__":
    main()
