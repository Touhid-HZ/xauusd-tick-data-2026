//+------------------------------------------------------------------+
//|                                         ImportXAUUSDTicks.mq5    |
//|          Import this repo's XAUUSD 2026 tick CSVs into MT5       |
//|                                                                  |
//|  Creates a custom symbol (e.g. XAUUSD_T2026) and feeds it the   |
//|  tick history, so you can chart it or run Strategy Tester in     |
//|  "Every tick based on real ticks" mode.                          |
//|                                                                  |
//|  Setup:                                                          |
//|   1. Run scripts/metatrader/prepare_csv.py to merge the weekly   |
//|      .csv.gz files into ONE plain CSV (e.g. XAUUSD_2026_ALL.csv) |
//|   2. Copy that CSV into  <MT5 data folder>\MQL5\Files\           |
//|   3. Drag this script onto any chart, set inputs, run.           |
//+------------------------------------------------------------------+
#property copyright "xauusd-tick-data-2026 (MIT)"
#property version   "1.00"
#property script_show_inputs
#property description "Imports XAUUSD 2026 tick CSV into a custom symbol"

input string InpCsvFile  = "XAUUSD_2026_ALL.csv"; // CSV file (inside MQL5\Files)
input string InpSymbol   = "XAUUSD_T2026";        // custom symbol to create
input bool   InpRecreate = true;                  // delete existing symbol first
input int    InpBatch    = 200000;                // ticks per import batch

//+------------------------------------------------------------------+
int OnStart()
  {
   //--- recreate the custom symbol
   if(InpRecreate && SymbolSelect(InpSymbol, true))
     {
      if(!CustomSymbolDelete(InpSymbol))
        {
         Print("Could not delete existing symbol (close its charts first). Err=", GetLastError());
         return INIT_FAILED;
        }
     }
   if(!CustomSymbolCreate(InpSymbol, NULL, "XAUUSD"))
      if(!CustomSymbolCreate(InpSymbol, NULL))
        {
         Print("CustomSymbolCreate failed. Err=", GetLastError());
         return INIT_FAILED;
        }
   SymbolSetInteger(InpSymbol, SYMBOL_DIGITS, 3);
   SymbolSetDouble (InpSymbol, SYMBOL_POINT,  0.001);
   SymbolSelect(InpSymbol, true);

   //--- open the CSV
   int h = FileOpen(InpCsvFile, FILE_READ|FILE_TXT|FILE_ANSI);
   if(h == INVALID_HANDLE)
     {
      Print("Cannot open ", InpCsvFile, " (must sit in MQL5\\Files). Err=", GetLastError());
      return INIT_FAILED;
     }
   FileReadString(h); // skip header

   MqlTick ticks[];
   ArrayResize(ticks, InpBatch);
   long   added_total = 0;
   int    in_batch    = 0;
   int    bad_lines   = 0;
   ulong  t0          = GetMicrosecondCount();

   while(!FileIsEnding(h))
     {
      string line = FileReadString(h);
      if(StringLen(line) < 25)
         continue;
      string p[];
      if(StringSplit(line, ',', p) != 5)
        { bad_lines++; continue; }

      // timestamp "2026-01-02 00:00:01.108"
      string dmy = p[0];
      StringReplace(dmy, "-", ".");
      string sec_str = StringSubstr(p[0], 11, 8);   // "00:00:01"
      int    msec    = (int)StringToInteger(StringSubstr(p[0], 20));

      datetime sec = StringToTime(StringSubstr(dmy, 0, 10) + " " + sec_str);

      ticks[in_batch].time     = sec;
      ticks[in_batch].time_msc = (long)sec * 1000 + msec;
      ticks[in_batch].bid      = StringToDouble(p[2]);
      ticks[in_batch].ask      = StringToDouble(p[1]);
      ticks[in_batch].last     = 0.0;
      ticks[in_batch].volume   = (ulong)MathRound(
                                   (StringToDouble(p[3]) + StringToDouble(p[4])) * 1000000.0);
      in_batch++;

      if(in_batch == InpBatch)
        {
         int added = CustomTicksAdd(InpSymbol, ticks);
         if(added < 0)
           {
            Print("CustomTicksAdd failed. Err=", GetLastError());
            FileClose(h);
            return INIT_FAILED;
           }
         added_total += added;
         in_batch = 0;
         if(added_total % 1000000 < InpBatch)
            Print("  ... ", added_total, " ticks imported");
        }
     }
   if(in_batch > 0)
      added_total += CustomTicksAdd(InpSymbol, ticks);

   FileClose(h);
   double secs = (GetMicrosecondCount() - t0) / 1e6;
   PrintFormat("Done: %I64d ticks imported into %s in %.1fs (%d bad lines skipped).",
               added_total, InpSymbol, secs, bad_lines);
   Print("Open the custom symbol in Market Watch and enjoy real 2026 gold ticks.");
   return INIT_SUCCEEDED;
  }
//+------------------------------------------------------------------+
