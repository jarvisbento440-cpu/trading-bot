"""Strategie-Forschung auf Tagesbasis mit sauberer Trennung:
In-Sample (Entwicklung) bis SPLIT, Out-of-Sample (Prüfung) danach.

Positionen werden zum Tagesschluss festgelegt und gelten ab dem nächsten Tag (kein Blick in die Zukunft).
Gebühr: FEE pro gehandeltem Anteil (0,1 % pro Seite).
"""
from __future__ import annotations

import gzip
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

FEE = 0.001
SPLIT = pd.Timestamp("2025-10-11", tz="UTC")
END = pd.Timestamp("2026-10-11", tz="UTC")
FOCUS = ["BTC", "ETH", "SOL", "XRP", "ONDO"]


def load_daily(folder: Path) -> dict[str, pd.DataFrame]:
    out = {}
    for f in sorted(folder.glob("*_1d.csv.gz")):
        coin = f.name.split("_")[0]
        df = pd.read_csv(f)
        df.index = pd.to_datetime(df["ts"], unit="ms", utc=True)
        out[coin] = _after_gap(df[df.index < END])
    return out


def _after_gap(df: pd.DataFrame, max_gap=pd.Timedelta(days=3)) -> pd.DataFrame:
    """Nur den Teil nach der letzten großen Datenlücke behalten (z. B. XRP-Delisting bei Coinbase 2021–2023)."""
    gaps = np.flatnonzero(df.index.to_series().diff() > max_gap)
    return df.iloc[gaps[-1]:] if len(gaps) else df


def load_hourly(folder: Path, coin: str) -> pd.DataFrame:
    df = pd.read_csv(folder / f"{coin}_1h.csv.gz")
    df.index = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return _after_gap(df[df.index < END])


# ---------- Positions-Regeln (je Coin, Tagesdaten) -> Serie in [-1, 1] ----------

def sma_filter(df, n, short=False):
    c = df["close"]
    up = c > c.rolling(n).mean()
    return up.astype(float) - (0 if not short else (~up).astype(float))


def ema_cross(df, f, s, short=False):
    c = df["close"]
    up = c.ewm(span=f, adjust=False).mean() > c.ewm(span=s, adjust=False).mean()
    return up.astype(float) - (0 if not short else (~up).astype(float))


def donchian(df, n_in, n_out, short=False):
    h, l, c = df["high"], df["low"], df["close"]
    hi = h.shift(1).rolling(n_in).max()
    lo_exit = l.shift(1).rolling(n_out).min()
    lo = l.shift(1).rolling(n_in).min()
    hi_exit = h.shift(1).rolling(n_out).max()
    pos = np.zeros(len(df))
    p = 0.0
    for i in range(len(df)):
        ci = c.iat[i]
        if p == 0:
            if ci > hi.iat[i]:
                p = 1.0
            elif short and ci < lo.iat[i]:
                p = -1.0
        elif p == 1 and ci < lo_exit.iat[i]:
            p = -1.0 if short and ci < lo.iat[i] else 0.0
        elif p == -1 and ci > hi_exit.iat[i]:
            p = 1.0 if ci > hi.iat[i] else 0.0
        pos[i] = p
    return pd.Series(pos, index=df.index)


def tsmom(df, look, short=False):
    r = df["close"].pct_change(look)
    return (r > 0).astype(float) - (0 if not short else (r <= 0).astype(float))


def mtf(df, lens=(10, 20, 50, 100, 200)):
    c = df["close"]
    return sum((c > c.rolling(n).mean()).astype(float) for n in lens) / len(lens)


def dip_buy(df, z=2.0, hold=3, trend=200):
    c = df["close"]
    r = c.pct_change()
    sd = r.rolling(20).std()
    trig = (r < -z * sd) & (c > c.rolling(trend).mean())
    pos = pd.Series(0.0, index=df.index)
    for i in np.flatnonzero(trig.values):
        pos.iloc[i:i + hold] = 1.0
    return pos


def vol_target(pos, df, target=0.5, look=30):
    vol = df["close"].pct_change().rolling(look).std() * np.sqrt(365)
    scale = (target / vol).clip(upper=1.0).fillna(0)
    return pos * scale


# ---------- Auswertung ----------

def coin_returns(df, pos):
    r = df["close"].pct_change().fillna(0)
    pos = pos.fillna(0)
    held = pos.shift(1).fillna(0)
    turnover = pos.diff().abs().fillna(pos.abs())
    return held * r - FEE * turnover


def portfolio(daily, rule, coins):
    rets = {}
    for c in coins:
        if c not in daily:
            continue
        df = daily[c]
        rets[c] = coin_returns(df, rule(df))
    m = pd.DataFrame(rets)
    # Gleichgewichtet über Coins, die an dem Tag schon Daten (und 200 Tage Vorlauf) haben
    started = pd.DataFrame({c: daily[c]["close"].rolling(200).count() >= 200 for c in rets}).reindex(m.index).fillna(False)
    m = m.where(started)
    return m.mean(axis=1).fillna(0)


def metrics(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) < 30:
        return {}
    eq = (1 + r).cumprod()
    years = len(r) / 365
    cagr = eq.iloc[-1] ** (1 / years) - 1
    sharpe = r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else 0
    dd = (eq / eq.cummax() - 1).min()
    return {"cagr": cagr, "sharpe": sharpe, "maxdd": dd, "total": eq.iloc[-1] - 1}


def split(r):
    return r[r.index < SPLIT], r[r.index >= SPLIT]


def run_grid(daily, coins):
    grid = {
        "Kaufen & Halten": [((), lambda d: pd.Series(1.0, index=d.index))],
        "SMA-Trendfilter": [((n,), (lambda n: lambda d: sma_filter(d, n))(n)) for n in (20, 50, 100, 150, 200)],
        "SMA-Trendfilter Long/Short": [((n,), (lambda n: lambda d: sma_filter(d, n, True))(n)) for n in (20, 50, 100, 200)],
        "EMA-Kreuz": [((f, s), (lambda f, s: lambda d: ema_cross(d, f, s))(f, s)) for f, s in ((10, 30), (20, 50), (20, 100), (50, 200))],
        "Donchian Tag": [((a, b), (lambda a, b: lambda d: donchian(d, a, b))(a, b)) for a, b in ((20, 10), (30, 15), (50, 20), (55, 20))],
        "Donchian Tag Long/Short": [((a, b), (lambda a, b: lambda d: donchian(d, a, b, True))(a, b)) for a, b in ((20, 10), (50, 20))],
        "Zeitreihen-Momentum": [((l,), (lambda l: lambda d: tsmom(d, l))(l)) for l in (14, 30, 60, 90)],
        "Mehrfach-Trend (MTF)": [((), mtf)],
        "Dip-Kauf im Aufwärtstrend": [((z, h), (lambda z, h: lambda d: dip_buy(d, z, h))(z, h)) for z, h in ((1.5, 3), (2.0, 3), (2.0, 5), (2.5, 5))],
    }
    # Volatilitätsgesteuerte Varianten der Trendregeln
    grid["SMA-Trendfilter + Vol-Steuerung"] = [((n,), (lambda n: lambda d: vol_target(sma_filter(d, n), d))(n)) for n in (50, 100, 200)]
    grid["Mehrfach-Trend + Vol-Steuerung"] = [((), lambda d: vol_target(mtf(d), d))]
    grid["Donchian + Vol-Steuerung"] = [((a, b), (lambda a, b: lambda d: vol_target(donchian(d, a, b), d))(a, b)) for a, b in ((20, 10), (50, 20))]

    results = []
    for name, variants in grid.items():
        for params, rule in variants:
            r = portfolio(daily, rule, coins)
            ins, oos = split(r)
            results.append({"name": name, "params": params, "in": metrics(ins), "out": metrics(oos)})
    return results


def xs_momentum(daily, coins, look=30, top=3, every=7):
    """Rotation: wöchentlich die `top` Coins mit dem besten `look`-Tage-Momentum halten (nur wenn > 0)."""
    closes = pd.DataFrame({c: daily[c]["close"] for c in coins if c in daily})
    rets = closes.pct_change().fillna(0)
    mom = closes.pct_change(look)
    w = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    cur = pd.Series(0.0, index=closes.columns)
    for i, t in enumerate(closes.index):
        if i % every == 0:
            m = mom.loc[t].dropna()
            m = m[m > 0].sort_values(ascending=False).head(top)
            cur = pd.Series(0.0, index=closes.columns)
            if len(m):
                cur[m.index] = 1.0 / top
        w.loc[t] = cur
    held = w.shift(1).fillna(0)
    turnover = w.diff().abs().sum(axis=1).fillna(0)
    return (held * rets).sum(axis=1) - FEE * turnover


def seasonality(folder, coin="BTC", hours=(21, 22)):
    """Nur in bestimmten UTC-Stunden long (Quantpedia: 21–23 Uhr UTC)."""
    h = load_hourly(folder, coin)
    r = h["close"].pct_change().fillna(0)
    inside = h.index.hour.isin(hours)
    gross = r.where(inside, 0)
    # Einstieg vor der ersten, Ausstieg nach der letzten Stunde: 2 Seiten pro Tag
    fees = pd.Series(0.0, index=h.index)
    fees[h.index.hour == hours[0]] = 2 * FEE
    hourly = gross - fees
    return hourly.groupby(hourly.index.floor("D")).sum()


def fmt(m):
    if not m:
        return "–"
    return f"CAGR {m['cagr']*100:+6.1f}% Sharpe {m['sharpe']:+.2f} MaxDD {m['maxdd']*100:5.1f}%"


if __name__ == "__main__":
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "history")
    coins = sys.argv[2].split(",") if len(sys.argv) > 2 else None
    daily = load_daily(folder)
    coins = coins or list(daily)
    print("Coins:", coins, {c: str(daily[c].index[0].date()) for c in coins})
    res = run_grid(daily, coins)
    for look, top in itertools.product((14, 30, 60), (1, 2, 3)):
        ins, oos = split(xs_momentum(daily, coins, look, top))
        res.append({"name": "Momentum-Rotation", "params": (look, top), "in": metrics(ins), "out": metrics(oos)})
    for hrs in ((21, 22), (22, 23), (21, 22, 23)):
        try:
            ins, oos = split(seasonality(folder, "BTC", hrs))
            res.append({"name": "Uhrzeit-Effekt BTC", "params": hrs, "in": metrics(ins), "out": metrics(oos)})
        except FileNotFoundError:
            pass
    for r in res:
        print(f"{r['name']:32s} {str(r['params']):12s} | IN {fmt(r['in'])} | OUT {fmt(r['out'])}")
    Path("research_results.json").write_text(json.dumps(res, default=str))
