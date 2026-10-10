import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df["close"].shift()
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c = df["close"]
    df["ema20"] = ema(c, 20)
    df["ema50"] = ema(c, 50)
    df["ema200"] = ema(c, 200)
    df["rsi"] = rsi(c)
    macd = ema(c, 12) - ema(c, 26)
    df["macd_hist"] = macd - ema(macd, 9)
    df["atr"] = atr(df)
    vol_mean = df["volume"].rolling(20).mean()
    vol_std = df["volume"].rolling(20).std()
    df["vol_z"] = (df["volume"] - vol_mean) / vol_std.replace(0, np.nan)
    # Ausbruch über das Hoch / unter das Tief der letzten 20 Kerzen (ohne aktuelle)
    df["hh20"] = df["high"].shift(1).rolling(20).max()
    df["ll20"] = df["low"].shift(1).rolling(20).min()
    return df


def trend_direction(df: pd.DataFrame) -> str:
    """Trend auf höherer Zeitebene: up / down / flat."""
    if len(df) < 60:
        return "flat"
    d = add_indicators(df).iloc[-1]
    if d["close"] > d["ema50"] > d["ema200"] or (d["close"] > d["ema50"] and d["ema20"] > d["ema50"]):
        return "up"
    if d["close"] < d["ema50"] < d["ema200"] or (d["close"] < d["ema50"] and d["ema20"] < d["ema50"]):
        return "down"
    return "flat"
