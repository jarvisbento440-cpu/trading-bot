from __future__ import annotations

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


def trend_series(higher: pd.DataFrame, tf_ms: int, ts: pd.Series) -> pd.Series:
    """Trend der höheren Zeitebene für jeden Zeitpunkt in ts, ohne Blick in die Zukunft.

    Eine Tageskerze zählt erst ab ihrem Ende (ts + tf_ms).
    """
    if len(higher) < 60:
        return pd.Series(["flat"] * len(ts), index=ts.index)
    h = add_indicators(higher)
    up = (h["close"] > h["ema50"]) & ((h["ema50"] > h["ema200"]) | (h["ema20"] > h["ema50"]))
    down = (h["close"] < h["ema50"]) & ((h["ema50"] < h["ema200"]) | (h["ema20"] < h["ema50"]))
    trend = pd.DataFrame({
        "avail": h["ts"] + tf_ms,
        "trend": np.where(up, "up", np.where(down, "down", "flat")),
    })
    left = pd.DataFrame({"ts": ts.values, "order": range(len(ts))})
    m = pd.merge_asof(left.sort_values("ts"), trend.sort_values("avail"),
                      left_on="ts", right_on="avail", direction="backward")
    m = m.sort_values("order")
    return pd.Series(m["trend"].fillna("flat").values, index=ts.index)


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> tuple[pd.Series, pd.Series]:
    mid = close.rolling(n).mean()
    sd = close.rolling(n).std()
    return mid + k * sd, mid - k * sd


FIB_LEVELS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]


def fibonacci(df: pd.DataFrame, lookback: int = 150) -> dict | None:
    """Fibonacci-Retracement zwischen Hoch und Tief der letzten `lookback` Kerzen.

    Kam das Hoch nach dem Tief, ist es ein Aufwärtsimpuls (Retracement nach unten gemessen).
    """
    w = df.tail(lookback)
    if len(w) < 20:
        return None
    hi_i, lo_i = w["high"].idxmax(), w["low"].idxmin()
    hi, lo = float(w.loc[hi_i, "high"]), float(w.loc[lo_i, "low"])
    up = hi_i > lo_i
    levels = [
        {"ratio": r, "price": hi - r * (hi - lo) if up else lo + r * (hi - lo)}
        for r in FIB_LEVELS
    ]
    return {
        "direction": "up" if up else "down",
        "from": {"ts": int(w.loc[lo_i if up else hi_i, "ts"]), "price": lo if up else hi},
        "to": {"ts": int(w.loc[hi_i if up else lo_i, "ts"]), "price": hi if up else lo},
        "levels": levels,
    }


def support_resistance(df: pd.DataFrame, lookback: int = 300, wing: int = 5, max_levels: int = 3) -> list[dict]:
    """Unterstützungen/Widerstände aus Umkehrpunkten (Fraktale), nah beieinander zusammengefasst."""
    w = df.tail(lookback).reset_index(drop=True)
    if len(w) < 2 * wing + 5:
        return []
    a = atr(w).iloc[-1]
    pivots = []
    for i in range(wing, len(w) - wing):
        win = w.iloc[i - wing:i + wing + 1]
        if w.at[i, "high"] == win["high"].max():
            pivots.append(float(w.at[i, "high"]))
        if w.at[i, "low"] == win["low"].min():
            pivots.append(float(w.at[i, "low"]))
    clusters: list[list[float]] = []
    for p in sorted(pivots):
        if clusters and p - clusters[-1][-1] <= 0.5 * a:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    price = float(w["close"].iloc[-1])
    levels = [{"price": sum(c) / len(c), "touches": len(c)} for c in clusters if len(c) >= 2]
    above = sorted([l for l in levels if l["price"] > price], key=lambda l: l["price"])[:max_levels]
    below = sorted([l for l in levels if l["price"] <= price], key=lambda l: -l["price"])[:max_levels]
    return [{**l, "kind": "resistance"} for l in above] + [{**l, "kind": "support"} for l in below]


def supertrend(df: pd.DataFrame, n: int = 10, mult: float = 3.0) -> tuple[pd.Series, pd.Series]:
    """Supertrend-Linie und Richtung (+1 aufwärts, -1 abwärts)."""
    a = atr(df, n).values
    hl2 = ((df["high"] + df["low"]) / 2).values
    close = df["close"].values
    upper, lower = hl2 + mult * a, hl2 - mult * a
    fu, fl = upper.copy(), lower.copy()
    direction = np.ones(len(df))
    line = np.full(len(df), np.nan)
    for i in range(1, len(df)):
        fu[i] = upper[i] if upper[i] < fu[i - 1] or close[i - 1] > fu[i - 1] else fu[i - 1]
        fl[i] = lower[i] if lower[i] > fl[i - 1] or close[i - 1] < fl[i - 1] else fl[i - 1]
        if direction[i - 1] == 1:
            direction[i] = -1 if close[i] < fl[i] else 1
        else:
            direction[i] = 1 if close[i] > fu[i] else -1
        line[i] = fl[i] if direction[i] == 1 else fu[i]
    return pd.Series(line, index=df.index), pd.Series(direction, index=df.index)


def confirmed_swings(df: pd.DataFrame, wing: int = 3) -> pd.DataFrame:
    """Letztes bestätigtes Swing-Hoch/-Tief je Kerze, ohne Blick in die Zukunft.

    Ein Umkehrpunkt gilt erst `wing` Kerzen später als bestätigt.
    """
    h, l = df["high"], df["low"]
    win = 2 * wing + 1
    is_ph = h == h.rolling(win, center=True).max()
    is_pl = l == l.rolling(win, center=True).min()
    pos = pd.Series(np.arange(len(df)), index=df.index, dtype=float)
    out = pd.DataFrame(index=df.index)
    out["sh"] = h.where(is_ph).shift(wing).ffill()
    out["sh_idx"] = pos.where(is_ph).shift(wing).ffill()
    out["sl"] = l.where(is_pl).shift(wing).ffill()
    out["sl_idx"] = pos.where(is_pl).shift(wing).ffill()
    return out


def add_strategy_columns(d: pd.DataFrame) -> pd.DataFrame:
    """Zusätzliche Spalten für die Strategien (d hat schon add_indicators)."""
    d = d.copy()
    c = d["close"]
    macd = ema(c, 12) - ema(c, 26)
    d["macd"], d["macd_sig"] = macd, ema(macd, 9)
    mid = c.rolling(20).mean()
    sd = c.rolling(20).std()
    d["bb_mid"], d["bb_up"], d["bb_lo"] = mid, mid + 2 * sd, mid - 2 * sd
    d["bb_width"] = (d["bb_up"] - d["bb_lo"]) / mid
    d["bb_width_q"] = d["bb_width"].rolling(120).quantile(0.1)
    d["st_line"], d["st_dir"] = supertrend(d)
    return d.join(confirmed_swings(d))
