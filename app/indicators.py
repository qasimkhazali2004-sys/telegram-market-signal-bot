from __future__ import annotations
import numpy as np
import pandas as pd

def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    gain = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def macd(s: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    fast = ema(s, 12)
    slow = ema(s, 26)
    line = fast - slow
    signal = ema(line, 9)
    return line, signal, line - signal

def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev).abs(),
        (df["low"] - prev).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()

def vwap(df: pd.DataFrame) -> pd.Series:
    vol = df["volume"].replace(0, np.nan)
    typical = (df["high"] + df["low"] + df["close"]) / 3
    return (typical * vol).cumsum() / vol.cumsum()

def enrich(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    x["ema20"] = ema(x["close"], 20)
    x["ema50"] = ema(x["close"], 50)
    x["ema200"] = ema(x["close"], 200)
    x["rsi"] = rsi(x["close"])
    _, _, x["macd_hist"] = macd(x["close"])
    x["atr"] = atr(x)
    x["vwap"] = vwap(x)
    x["volume_ma20"] = x["volume"].rolling(20).mean()
    return x

def pivots(df: pd.DataFrame, left: int = 2, right: int = 2):
    highs = []
    lows = []
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    for i in range(left, len(df)-right):
        if h[i] == max(h[i-left:i+right+1]):
            highs.append((i, h[i]))
        if l[i] == min(l[i-left:i+right+1]):
            lows.append((i, l[i]))
    return highs, lows

def structure(df: pd.DataFrame) -> dict:
    highs, lows = pivots(df)
    last_highs = [x[1] for x in highs[-4:]]
    last_lows = [x[1] for x in lows[-4:]]
    hh = len(last_highs) >= 2 and last_highs[-1] > last_highs[-2]
    hl = len(last_lows) >= 2 and last_lows[-1] > last_lows[-2]
    lh = len(last_highs) >= 2 and last_highs[-1] < last_highs[-2]
    ll = len(last_lows) >= 2 and last_lows[-1] < last_lows[-2]

    last = float(df["close"].iloc[-1])
    resistance = max(last_highs[-3:]) if last_highs else float(df["high"].tail(20).max())
    support = min(last_lows[-3:]) if last_lows else float(df["low"].tail(20).min())

    if hh and hl:
        bias = "BULLISH"
    elif lh and ll:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    return {
        "bias": bias,
        "hh": hh, "hl": hl, "lh": lh, "ll": ll,
        "support": support, "resistance": resistance,
        "breakout_up": last > resistance,
        "breakout_down": last < support,
    }
