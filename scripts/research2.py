"""Zweite Forschungsrunde (22.10.2026): Kandidaten aus der Web-Recherche.

Gleiche Regeln wie research.py: Position zum Tagesschluss, gilt ab dem nächsten Tag,
In-Sample bis SPLIT, Out-of-Sample danach, Gebühr pro Seite (0,1 % und 0,25 %).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import research as R


def donchian_ensemble(df, looks=(5, 10, 20, 30, 60, 90, 150, 250, 360), target=0.25):
    """Zarattini/Pagani/Barbon 2025: Einstieg bei Schluss über dem höchsten Schluss der letzten n Tage,
    nachgezogener Stopp = max(alter Stopp, Mitte aus höchstem und tiefstem Schluss der n Tage).
    Je Lookback Größe auf 25 % Jahresschwankung, kein Hebel (max. 100 %), Mittelwert über alle Lookbacks."""
    c = df["close"]
    vol = c.pct_change().rolling(90).std() * np.sqrt(365)
    size = (target / vol).clip(upper=1.0).fillna(0).values
    total = np.zeros(len(df))
    cv = c.values
    for n in looks:
        hi = c.shift(1).rolling(n).max().values
        mid = ((c.rolling(n).max() + c.rolling(n).min()) / 2).values
        p, stop = 0.0, -np.inf
        for i in range(len(df)):
            if p == 0 and not np.isnan(hi[i]) and cv[i] > hi[i]:
                p, stop = 1.0, mid[i]
            elif p == 1:
                stop = max(stop, mid[i])
                if cv[i] < stop:
                    p = 0.0
            total[i] += p * size[i]
    return pd.Series(total / len(looks), index=df.index)


def at_max(df, n, hold=1):
    """Quantpedia MAX: kaufen, wenn der Schluss das n-Tage-Hoch ist; `hold` Tage halten."""
    c = df["close"]
    trig = (c >= c.rolling(n).max()).values
    pos = np.zeros(len(df))
    for i in np.flatnonzero(trig):
        pos[i:i + hold] = 1.0
    return pd.Series(pos, index=df.index)


def low_vol(daily, coins, look=365, top=3, every=30, trend=None):
    """Kaya/Mostowfi 2022: monatlich die `top` Coins mit der niedrigsten Schwankung halten."""
    closes = pd.DataFrame({c: daily[c]["close"] for c in coins if c in daily})
    rets = closes.pct_change().fillna(0)
    vol = closes.pct_change().rolling(look, min_periods=look).std()
    w = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    cur = pd.Series(0.0, index=closes.columns)
    for i, t in enumerate(closes.index):
        if i % every == 0:
            v = vol.loc[t].dropna().sort_values().head(top)
            cur = pd.Series(0.0, index=closes.columns)
            if len(v) == top:
                cur[v.index] = 1.0 / top
        w.loc[t] = cur
    if trend:
        w = w * (closes > closes.rolling(trend).mean()).astype(float)
    held = w.shift(1).fillna(0)
    turnover = w.diff().abs().sum(axis=1).fillna(0)
    return (held * rets).sum(axis=1) - R.FEE * turnover


def equal_weight(daily, coins):
    closes = pd.DataFrame({c: daily[c]["close"] for c in coins if c in daily})
    started = closes.rolling(365, min_periods=365).count().notna() & closes.notna()
    return closes.pct_change().where(started).mean(axis=1).fillna(0)


def trades_per_year(daily, rule, coins):
    n = []
    for c in coins:
        p = rule(daily[c])
        n.append(((p > 0).astype(int).diff().abs() > 0).sum() / (len(p) / 365))
    return float(np.mean(n))


if __name__ == "__main__":
    folder = Path(sys.argv[1])
    daily = R.load_daily(folder)
    coins = list(daily)
    rules = {
        "Trendampel (SMA50 + Vol)": lambda d: R.vol_target(R.sma_filter(d, 50), d),
        "Donchian-Ensemble (Zarattini)": donchian_ensemble,
        "Donchian-Ensemble kurz (5-60)": lambda d: donchian_ensemble(d, (5, 10, 20, 30, 60)),
        "Donchian-Ensemble lang (60-360)": lambda d: donchian_ensemble(d, (60, 90, 150, 250, 360)),
        "MAX 10 Tage, 1 Tag halten": lambda d: at_max(d, 10, 1),
        "MAX 20 Tage, 1 Tag halten": lambda d: at_max(d, 20, 1),
        "MAX 10 Tage, 5 Tage halten": lambda d: at_max(d, 10, 5),
        "MAX 20 Tage, 10 Tage halten": lambda d: at_max(d, 20, 10),
    }
    res = []
    for fee in (0.001, 0.0025):
        R.FEE = fee
        for group, cs in (("alle 10", coins), ("Fokus 5", R.FOCUS)):
            for name, rule in rules.items():
                ins, oos = R.split(R.portfolio(daily, rule, cs))
                res.append({"name": name, "coins": group, "fee": fee, "in": R.metrics(ins), "out": R.metrics(oos),
                            "wechsel_pro_jahr": trades_per_year(daily, rule, cs) if fee == 0.001 else None})
            ins, oos = R.split(R.portfolio(daily, lambda d: pd.Series(1.0, index=d.index), cs))
            res.append({"name": "Kaufen & Halten", "coins": group, "fee": fee, "in": R.metrics(ins), "out": R.metrics(oos)})
        for name, kw in (("Niedrig-Vol 3 aus 10", {}), ("Niedrig-Vol 3 aus 10 + SMA50", {"trend": 50})):
            ins, oos = R.split(low_vol(daily, coins, **kw))
            res.append({"name": name, "coins": "alle 10", "fee": fee, "in": R.metrics(ins), "out": R.metrics(oos)})
        ins, oos = R.split(equal_weight(daily, coins))
        res.append({"name": "Gleichgewicht alle (Vergleich)", "coins": "alle 10", "fee": fee, "in": R.metrics(ins), "out": R.metrics(oos)})
    R.FEE = 0.001
    yearly = {}
    for name in ("Trendampel (SMA50 + Vol)", "MAX 10 Tage, 1 Tag halten", "MAX 20 Tage, 1 Tag halten", "Kaufen & Halten"):
        rule = rules.get(name, lambda d: pd.Series(1.0, index=d.index))
        r = R.portfolio(daily, rule, R.FOCUS)
        yearly[name] = {f"{y}/{y+1-2000}": float((1 + r[(r.index >= pd.Timestamp(f"{y}-10-11", tz="UTC")) & (r.index < pd.Timestamp(f"{y+1}-10-11", tz="UTC"))]).prod() - 1)
                        for y in range(2021, 2026)}
    print(json.dumps(yearly, indent=1))
    res.append({"name": "Jahre Fokus 5 (0,1 %)", "yearly": yearly})
    for r in res:
        if "yearly" in r:
            continue
        w = f" | {r['wechsel_pro_jahr']:.0f} Wechsel/J" if r.get("wechsel_pro_jahr") else ""
        print(f"{r['fee']*100:.2f}% {r['coins']:8s} {r['name']:32s} | IN {R.fmt(r['in'])} | OUT {R.fmt(r['out'])}{w}")
    (Path(__file__).resolve().parent.parent / "results" / "research2_results.json").write_text(json.dumps(res, default=str, indent=1))
