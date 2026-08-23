from __future__ import annotations
import argparse
import pandas as pd
from app.indicators import enrich

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True)
    p.add_argument("--symbol", required=True)
    args = p.parse_args()

    df = pd.read_csv(args.csv)
    if "datetime" in df:
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df = df.sort_values("datetime").reset_index(drop=True)
    if len(df) < 300:
        raise SystemExit("بيانات backtest قليلة. استخدم عينة تاريخية أطول.")

    x = enrich(df)
    # No look-ahead: signal on bar i, outcome starts from bar i+1.
    signals = []
    for i in range(200, len(x)-1):
        row = x.iloc[i]
        if row["ema20"] > row["ema50"] > row["ema200"] and row["rsi"] >= 55 and row["macd_hist"] > 0:
            signals.append((i, 1))
        elif row["ema20"] < row["ema50"] < row["ema200"] and row["rsi"] <= 45 and row["macd_hist"] < 0:
            signals.append((i, -1))

    print(f"symbol={args.symbol}")
    print(f"rows={len(x)}")
    print(f"signals={len(signals)}")
    print("هذا harness أولي. أضف نموذج fees/spread/slippage وwalk-forward/OOS قبل أي استنتاج.")
