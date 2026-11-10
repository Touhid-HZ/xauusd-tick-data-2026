# Contributing

Thanks for your interest in improving this dataset.

## Ways to help

- **Found a data issue?** (gap, bad print, timestamp anomaly) — open an issue
  and mention the week file (`XAUUSD_2026_wNN.csv.gz`) and a sample timestamp.
- **Want another instrument or year?** — the downloader scripts are generic;
  open a feature request or fork and go.
- **Bug fixes to scripts** — PRs welcome. Keep scripts dependency-light
  (requests / stdlib for the downloader; pandas + matplotlib only for
  analysis/build steps).

## Rebuilding the data yourself

```bash
pip install requests
python scripts/download_weeks_node.py --from 2026-01-01 --to 2026-11-10 \
    --work-dir ./work          # needs Node.js (npx dukascopy-node)
python scripts/build_daily_ohlcv.py
python scripts/verify_data.py
```

## Data conventions (please keep)

- One gzip CSV per 7-day chunk anchored to the dataset start date.
- UTC timestamps, ISO format, millisecond precision, sorted.
- Never edit raw week files — regenerate them from source instead.
