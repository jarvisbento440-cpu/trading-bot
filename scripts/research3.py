"""Dritte Runde (22.10.2026): die Ansätze aus Jengs Liste, die noch fehlten.
Golden Cross (SMA 50/200), Range-Trading, Breakout mit Retest. Gleiche Methode wie research.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import research as R
from research2 import trades_per_year


def golden_cross(df, f=50, s=200):
    c = df["close"]
    return (c.rolling(f).mean() > c.rolling(s).mean()).astype(float)


def adx(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    up, dn = h.diff(), -l.diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(plus, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    mdi = 100 * pd.Series(minus, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def range_trade(df, n=20, adx_max=20, buy_zone=0.2, sell_zone=0.8):
    """Nur bei schwachem Trend (ADX < adx_max): kaufen im unteren Fünftel der n-Tage-Spanne,
    verkaufen im oberen Fünftel; raus, wenn die Spanne nach unten bricht."""
    hi = df["high"].shift(1).rolling(n).max()
    lo = df["low"].shift(1).rolling(n).min()
    c = df["close"].values
    pos_in_range = ((df["close"] - lo) / (hi - lo)).values
    a = adx(df).values
    lov = lo.values
    pos = np.zeros(len(df))
    p = 0.0
    for i in range(len(df)):
        if np.isnan(pos_in_range[i]):
            continue
        if p == 0 and a[i] < adx_max and 0 <= pos_in_range[i] <= buy_zone:
            p = 1.0
        elif p == 1 and (pos_in_range[i] >= sell_zone or c[i] < lov[i]):
            p = 0.0
        pos[i] = p
    return pd.Series(pos, index=df.index)


def breakout_retest(df, n=20, window=10, tol=0.01, stop=0.03, exit_n=10):
    """Schluss über dem n-Tage-Hoch = Ausbruch, Niveau L merken. Innerhalb von `window` Tagen
    kaufen, wenn das Tagestief bis L (+tol) zurückkommt und der Schluss über L bleibt (Retest).
    Raus bei Schluss unter L*(1-stop) oder unter dem exit_n-Tage-Tief."""
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    hi = df["high"].shift(1).rolling(n).max().values
    lo_exit = df["low"].shift(1).rolling(exit_n).min().values
    pos = np.zeros(len(df))
    p, level, since = 0.0, np.nan, 999
    for i in range(len(df)):
        if p == 1:
            if c[i] < level * (1 - stop) or c[i] < lo_exit[i]:
                p = 0.0
        if p == 0:
            if not np.isnan(hi[i]) and c[i] > hi[i]:
                level, since = hi[i], 0
            else:
                since += 1
                if since <= window and l[i] <= level * (1 + tol) and c[i] > level:
                    p = 1.0
        pos[i] = p
    return pd.Series(pos, index=df.index)


if __name__ == "__main__":
    daily = R.load_daily(Path(sys.argv[1]))
    coins = list(daily)
    rules = {
        "Golden Cross SMA 50/200": golden_cross,
        "Golden Cross SMA 20/100": lambda d: golden_cross(d, 20, 100),
        "Range-Trading 20 Tage, ADX<20": range_trade,
        "Range-Trading 30 Tage, ADX<25": lambda d: range_trade(d, 30, 25),
        "Breakout-Retest 20 Tage": breakout_retest,
        "Breakout-Retest 50 Tage": lambda d: breakout_retest(d, 50, 15, 0.02, 0.05, 20),
        "Trendampel (Vergleich)": lambda d: R.vol_target(R.sma_filter(d, 50), d),
        "Kaufen & Halten": lambda d: pd.Series(1.0, index=d.index),
    }
    res = []
    for fee in (0.001, 0.0025):
        R.FEE = fee
        for group, cs in (("alle 10", coins), ("Fokus 5", R.FOCUS)):
            for name, rule in rules.items():
                ins, oos = R.split(R.portfolio(daily, rule, cs))
                tpy = trades_per_year(daily, rule, cs) if fee == 0.001 else None
                res.append({"name": name, "coins": group, "fee": fee, "in": R.metrics(ins), "out": R.metrics(oos), "wechsel_pro_jahr": tpy})
                w = f" | {tpy:.0f} Wechsel/J" if tpy else ""
                print(f"{fee*100:.2f}% {group:8s} {name:32s} | IN {R.fmt(R.metrics(ins))} | OUT {R.fmt(R.metrics(oos))}{w}")
    (Path(__file__).resolve().parent.parent / "results" / "research3_results.json").write_text(json.dumps(res, default=str, indent=1))
