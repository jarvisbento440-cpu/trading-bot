"""Vierte Runde (22.10.2026): Smart-Money-Bausteine als feste Regeln (nur Long).

Fair Value Gap (FVG): Tief von Kerze i liegt über dem Hoch von Kerze i-2 -> Lücke [Hoch i-2, Tief i].
Order Block (OB): Schluss über dem höchsten Hoch der letzten 10 Kerzen (Strukturbruch); die letzte rote
Kerze der 5 Kerzen davor ist der Order Block [Tief, Hoch].
Einstieg: Kurs kommt innerhalb von `window` Kerzen in die Zone zurück und schließt nicht darunter.
Stopp: Schluss unter der Zonen-Unterkante. Ziel: 2 R. Spätestens nach `max_hold` Kerzen raus.
Optional Trendfilter: nur wenn der Schluss über dem 50-Tage-Schnitt liegt.
Getestet auf Tageskerzen und 4h-Kerzen (aus 1h gebaut). Gleiche Trennung wie research.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import research as R


def fvg_zones(df, min_gap=0.0):
    h, l = df["high"].values, df["low"].values
    zones = [None] * len(df)
    for i in range(2, len(df)):
        if l[i] > h[i - 2] * (1 + min_gap):
            zones[i] = (h[i - 2], l[i])
    return zones


def ob_zones(df, bos=10, back=5):
    o, h, l, c = (df[k].values for k in ("open", "high", "low", "close"))
    prev_hi = df["high"].shift(1).rolling(bos).max().values
    zones = [None] * len(df)
    for i in range(bos + back, len(df)):
        if c[i] > prev_hi[i] and not c[i - 1] > prev_hi[i - 1]:
            for j in range(i - 1, i - 1 - back, -1):
                if c[j] < o[j]:
                    zones[i] = (l[j], h[j])
                    break
    return zones


def zone_retest(df, zones, window=20, rr=2.0, max_hold=30, trend=None):
    l, c = df["low"].values, df["close"].values
    tr = trend.values if trend is not None else np.ones(len(df), bool)
    pos = np.zeros(len(df))
    active = []  # [bottom, top, age]
    p, stop, target, held = 0.0, 0.0, 0.0, 0
    for i in range(len(df)):
        if p == 1:
            held += 1
            if c[i] < stop or c[i] >= target or held >= max_hold:
                p = 0.0
        else:
            for z in active:
                bot, top = z[0], z[1]
                if l[i] <= top and c[i] >= bot and tr[i]:
                    risk = max(c[i] - bot, c[i] * 0.005)
                    p, stop, target, held = 1.0, bot, c[i] + rr * risk, 0
                    z[2] = window  # Zone verbraucht
                    break
        active = [z for z in active if z[2] < window and c[i] >= z[0]]
        for z in active:
            z[2] += 1
        if zones[i] is not None:
            active.append([zones[i][0], zones[i][1], 0])
        pos[i] = p
    return pd.Series(pos, index=df.index)


def to_4h(h1):
    g = h1.resample("4h", origin="epoch")
    out = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last()})
    return out.dropna()


def bar_returns(df, pos):
    r = df["close"].pct_change().fillna(0)
    held = pos.shift(1).fillna(0)
    return held * r - R.FEE * pos.diff().abs().fillna(0)


def run(frames, rule, coins, per_day):
    daily = {}
    trades = []
    for c in coins:
        df = frames[c]
        pos = rule(df)
        rr = bar_returns(df, pos)
        daily[c] = rr.groupby(rr.index.floor("D")).sum()
        trades.append(((pos.diff() > 0).sum()) / (len(df) / per_day / 365))
    m = pd.DataFrame(daily)
    started = m.notna() & (m.notna().cumsum() > 200)
    return m.where(started).mean(axis=1).fillna(0), float(np.mean(trades))


def trend_for(df, bars_per_day):
    return df["close"] > df["close"].rolling(50 * bars_per_day).mean()


if __name__ == "__main__":
    folder = Path(sys.argv[1])
    d1 = R.load_daily(folder)
    h4 = {c: to_4h(R.load_hourly(folder, c)) for c in R.FOCUS}
    res = []
    for fee in (0.001, 0.0025):
        R.FEE = fee
        for tf, frames, per_day, win, hold in (("1d", d1, 1, 20, 30), ("4h", h4, 6, 60, 90)):
            variants = {
                "FVG": lambda d: zone_retest(d, fvg_zones(d), win, 2.0, hold),
                "FVG + Trendfilter": lambda d: zone_retest(d, fvg_zones(d), win, 2.0, hold, trend_for(d, per_day)),
                "Order Block": lambda d: zone_retest(d, ob_zones(d), win, 2.0, hold),
                "Order Block + Trendfilter": lambda d: zone_retest(d, ob_zones(d), win, 2.0, hold, trend_for(d, per_day)),
                "Order Block + Trend, Ziel 3R": lambda d: zone_retest(d, ob_zones(d), win, 3.0, hold, trend_for(d, per_day)),
            }
            for name, rule in variants.items():
                r, tpy = run(frames, rule, R.FOCUS, per_day)
                ins, oos = R.split(r)
                res.append({"name": name, "tf": tf, "fee": fee, "in": R.metrics(ins), "out": R.metrics(oos), "trades_pro_coin_jahr": tpy})
                print(f"{fee*100:.2f}% {tf} {name:30s} | IN {R.fmt(R.metrics(ins))} | OUT {R.fmt(R.metrics(oos))} | {tpy:.0f} Trades/J")
    (Path(__file__).resolve().parent.parent / "results" / "research4_results.json").write_text(json.dumps(res, default=str, indent=1))
