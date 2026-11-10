# Importing the dataset into MetaTrader 5

You can turn this repository's tick CSVs into a **custom symbol** inside
MetaTrader 5 and then run the Strategy Tester in
*"Every tick based on real ticks"* mode with genuine 2026 gold quotes.

## Steps

1. **Merge + decompress the weekly files** into one plain CSV
   (MT5 cannot read gzip). From the repo root:

   ```bash
   python scripts/metatrader/prepare_csv.py                 # full year (~3.5 GB)
   python scripts/metatrader/prepare_csv.py --weeks w01 w02 # just a subset
   ```

   This writes `XAUUSD_2026_ALL.csv` (same schema:
   `timestamp,ask,bid,ask_volume,bid_volume`).

2. **Copy the CSV** into your MT5 data folder:
   `File → Open Data Folder → MQL5 → Files`

3. **Compile and run the importer script**
   `ImportXAUUSDTicks.mq5` (from `scripts/metatrader/`) in MetaEditor,
   then drag it onto any chart. Inputs:

   | Input        | Default              | Meaning                          |
   |--------------|----------------------|----------------------------------|
   | `InpCsvFile` | `XAUUSD_2026_ALL.csv`| CSV inside `MQL5\Files`          |
   | `InpSymbol`  | `XAUUSD_T2026`       | custom symbol name to create     |
   | `InpRecreate`| `true`               | delete existing symbol first     |
   | `InpBatch`   | `200000`             | ticks per import batch           |

4. The script creates the symbol (`SYMBOL_DIGITS = 3`,
   `SYMBOL_POINT = 0.001`), streams all ticks via `CustomTicksAdd`, and
   prints a summary. Importing ~79M ticks takes a few minutes.

5. Open **XAUUSD_T2026** in Market Watch / a new chart, or select it in the
   Strategy Tester with modeling mode **"Every tick based on real ticks"**.

## Notes

- Timestamps are UTC; MT5 displays them in your local terminal timezone.
- `MqlTick.volume` is filled from the CSV volumes
  (`(ask_volume + bid_volume) × 1,000,000` units).
- The importer requires MT5 build 3800+ (custom symbols support).
