"""Trendampel: Tages-Trendfilter mit Positionsgröße nach Schwankung.

Regel (an Tagesschlusskursen, ohne Blick in die Zukunft):
- Schlusskurs über dem 50-Tage-Durchschnitt  -> HALTEN (long)
- Schlusskurs darunter                      -> RAUS (flat, kein Short)
- Anteil = Ziel-Schwankung 50 % p. a. / Schwankung der letzten 30 Tage, höchstens 100 %.

Die einzige Regel, die in der Forschung (scripts/research.py, docs/trendampel.md) sowohl
2021–2025 (Entwicklung) als auch im Prüfjahr 2025/26 vorne lag. Ihr Vorteil ist vor allem,
große Abstürze zu vermeiden – kein Gewinn in jedem Jahr.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

SMA = 50
VOL_TARGET = 0.5
VOL_LOOK = 30
DAY_MS = 86_400_000

# Ergebnisse aus scripts/research.py (Coinbase, 0,1 % Gebühr pro Seite)
BACKTEST = {
    "focus": "BTC, ETH, SOL, XRP, ONDO",
    "rows": [
        # Zeitraum, Trendampel, Kaufen & Halten
        ("2021/22", -26, -70),
        ("2022/23", 13, 14),
        ("2023/24", 89, 183),
        ("2024/25", 55, 101),
        ("2025/26 (Prüfjahr)", 13, -32),
    ],
    "maxdd": (-44, -85),
}


def positions(daily: pd.DataFrame, sma: int = SMA, vol_target: float = VOL_TARGET,
              vol_look: int = VOL_LOOK) -> pd.DataFrame:
    """Je Tageskerze: Signal (1 = halten, 0 = raus) und empfohlener Anteil, gültig ab dem nächsten Tag."""
    c = daily["close"].astype(float)
    ma = c.rolling(sma).mean()
    on = (c > ma).astype(float).where(ma.notna(), 0.0)
    vol = c.pct_change().rolling(vol_look).std() * math.sqrt(365)
    size = (vol_target / vol).clip(upper=1.0).fillna(0.0)
    return pd.DataFrame({"ts": daily["ts"].values, "close": c.values, "sma": ma.values, "on": on.values,
                         "size": (on * size).values, "vol": vol.values})


def closed_daily(daily: pd.DataFrame, now_ms: int) -> pd.DataFrame:
    if len(daily) and daily["ts"].iloc[-1] + DAY_MS > now_ms:
        return daily.iloc[:-1]
    return daily


def current(daily: pd.DataFrame, now_ms: int) -> dict | None:
    """Aktueller Stand der Trendampel aus abgeschlossenen Tageskerzen."""
    d = closed_daily(daily.reset_index(drop=True), now_ms)
    if len(d) < SMA + 1:
        return None
    p = positions(d)
    last = p.iloc[-1]
    on = p["on"].values
    # Seit wann gilt der aktuelle Zustand?
    change = np.flatnonzero(on != on[-1])
    since_i = int(change[-1]) + 1 if len(change) else 0
    since_close = float(p["close"].iloc[since_i])
    return {
        "state": "long" if last["on"] else "flat",
        "since": int(p["ts"].iloc[since_i]) + DAY_MS,  # gilt ab dem Tag nach der Signal-Kerze
        "since_close": since_close,
        "since_change": (float(last["close"]) / since_close - 1) * 100,
        "bar_ts": int(last["ts"]),
        "close": float(last["close"]),
        "sma": float(last["sma"]),
        "distance": (float(last["close"]) / float(last["sma"]) - 1) * 100,
        "size": float(last["size"]),
        "vol": None if pd.isna(last["vol"]) else float(last["vol"]),
        "switched": len(on) >= 2 and on[-1] != on[-2],
    }


def sma_line(daily: pd.DataFrame, sma: int = SMA) -> pd.Series:
    return daily["close"].rolling(sma).mean()


def format_switch(symbol: str, r: dict) -> str:
    from .notify import fmt_price
    if r["state"] == "long":
        head = f"🟢 {symbol} Trendampel: HALTEN / KAUFEN"
        why = f"Tagesschluss {fmt_price(r['close'])} über dem 50-Tage-Schnitt {fmt_price(r['sma'])}."
        size = f"Empfohlener Anteil deines Coin-Budgets: {r['size'] * 100:.0f} % (je wilder der Kurs, desto weniger)."
    else:
        head = f"⚪ {symbol} Trendampel: RAUS"
        why = f"Tagesschluss {fmt_price(r['close'])} unter dem 50-Tage-Schnitt {fmt_price(r['sma'])}."
        size = "Empfehlung: Position schließen und warten, bis die Ampel wieder grün wird."
    return "\n".join([head, why, size, "",
                      "Langsames Tagessignal, etwa 10 Wechsel pro Jahr. Schützt vor großen Abstürzen, "
                      "verpasst aber einen Teil starker Anstiege. Keine Gewinngarantie."])
