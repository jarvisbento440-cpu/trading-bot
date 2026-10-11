"""Handelsstrategien. Jede liefert Signale mit Einstieg, Stop und zwei Zielen.

Alle Strategien handeln nur in Richtung des Tages-Trends (Long im Aufwärts-, Short im Abwärtstrend).
Ein Signal entsteht auf einer abgeschlossenen Kerze; Einstieg ist deren Schlusskurs.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .indicators import add_indicators, add_strategy_columns


@dataclass
class Signal:
    strategy: str
    i: int               # Position der Signal-Kerze im DataFrame
    bar_ts: int
    side: str            # long / short
    entry: float
    stop: float
    target1: float
    target2: float
    score: int = 0
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StrategyInfo:
    key: str
    name: str
    short: str
    color: str
    description: str


STRATEGIES: list[StrategyInfo] = [
    StrategyInfo("score", "Score-Modell", "S", "#4f9cf9",
                 "Punkte aus Trend, Ausbruch, Rücksetzer, RSI, MACD und Volumen."),
    StrategyInfo("donchian", "Donchian-Ausbruch", "D", "#f2b84b",
                 "Turtle-Regel: Schluss über dem 20-Kerzen-Hoch bzw. unter dem 20-Kerzen-Tief."),
    StrategyInfo("supertrend", "Supertrend-Wechsel", "T", "#c678dd",
                 "Supertrend (10, 3) dreht in Richtung des Tages-Trends."),
    StrategyInfo("macd", "MACD-Kreuzung", "M", "#56b6c2",
                 "MACD kreuzt die Signallinie unterhalb der Null-Linie (Ende eines Rücksetzers)."),
    StrategyInfo("rsi", "RSI-Rücksetzer", "R", "#e06c75",
                 "RSI kommt aus überverkauft (30) bzw. überkauft (70) zurück, über/unter EMA200."),
    StrategyInfo("squeeze", "Bollinger-Squeeze", "B", "#98c379",
                 "Nach sehr engen Bollinger-Bändern schließt der Kurs außerhalb des Bandes."),
    StrategyInfo("fib", "Fibonacci Golden Pocket", "F", "#d19a66",
                 "Rücksetzer in die 61,8–65 %-Zone des letzten Impulses mit Umkehrkerze."),
    StrategyInfo("sweep", "Liquiditäts-Sweep", "L", "#ff7eb6",
                 "Kurs sticht unter ein Swing-Tief (über ein Swing-Hoch), holt die Stops ab und schließt zurück."),
]
BY_KEY = {s.key: s for s in STRATEGIES}

MIN_BARS = 210


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    return add_strategy_columns(add_indicators(df))


def _mk(strategy, d, i, side, stop, r1, r2, reasons, score=0, target2=None, target1=None):
    entry = float(d["close"].iat[i])
    risk = abs(entry - stop)
    a = float(d["atr"].iat[i])
    if not np.isfinite(risk) or risk < 0.3 * a or risk > 6 * a:
        return None
    sign = 1 if side == "long" else -1
    t1 = target1 if target1 is not None else entry + sign * r1 * risk
    t2 = target2 if target2 is not None else entry + sign * r2 * risk
    if sign * (t1 - entry) < 0.8 * risk:  # zu wenig Chance
        return None
    if sign * (t2 - t1) <= 0:
        t2 = entry + sign * max(r2 * risk, abs(t1 - entry) * 1.5)
    return Signal(strategy, i, int(d["ts"].iat[i]), side, entry, float(stop), float(t1), float(t2),
                  score, reasons)


def _sides(trend: str):
    return {"up": ["long"], "down": ["short"]}.get(trend, [])


# ---- einzelne Regeln: (d, i, side) -> Signal | None --------------------------------------

def s_score(d, i, side, min_score=65):
    from .strategy import _score  # bestehendes Punktesystem
    score, reasons = _score(d.iloc[i], d.iloc[i - 1], side)
    if score < min_score:
        return None
    a = d["atr"].iat[i]
    sign = 1 if side == "long" else -1
    return _mk("score", d, i, side, d["close"].iat[i] - sign * 1.5 * a, 1.5, 2.5, reasons, score)


def s_donchian(d, i, side):
    c, a = d["close"], d["atr"].iat[i]
    if side == "long":
        ok = c.iat[i] > d["hh20"].iat[i] and c.iat[i - 1] <= d["hh20"].iat[i - 1] and c.iat[i] > d["ema50"].iat[i]
        return _mk("donchian", d, i, side, c.iat[i] - 2 * a, 2, 3, ["Schluss über 20-Kerzen-Hoch"]) if ok else None
    ok = c.iat[i] < d["ll20"].iat[i] and c.iat[i - 1] >= d["ll20"].iat[i - 1] and c.iat[i] < d["ema50"].iat[i]
    return _mk("donchian", d, i, side, c.iat[i] + 2 * a, 2, 3, ["Schluss unter 20-Kerzen-Tief"]) if ok else None


def s_supertrend(d, i, side):
    want = 1 if side == "long" else -1
    if not (d["st_dir"].iat[i] == want and d["st_dir"].iat[i - 1] == -want):
        return None
    a = d["atr"].iat[i]
    line = d["st_line"].iat[i]
    sign = 1 if side == "long" else -1
    stop = line - sign * 0.2 * a
    return _mk("supertrend", d, i, side, stop, 1.5, 3, ["Supertrend dreht " + ("aufwärts" if side == "long" else "abwärts")])


def s_macd(d, i, side):
    m, s = d["macd"], d["macd_sig"]
    a = d["atr"].iat[i]
    c = d["close"].iat[i]
    if side == "long":
        ok = m.iat[i] > s.iat[i] and m.iat[i - 1] <= s.iat[i - 1] and m.iat[i] < 0 and c > d["ema200"].iat[i]
        return _mk("macd", d, i, side, c - 1.5 * a, 1.5, 3, ["MACD kreuzt unter Null nach oben", "Kurs über EMA200"]) if ok else None
    ok = m.iat[i] < s.iat[i] and m.iat[i - 1] >= s.iat[i - 1] and m.iat[i] > 0 and c < d["ema200"].iat[i]
    return _mk("macd", d, i, side, c + 1.5 * a, 1.5, 3, ["MACD kreuzt über Null nach unten", "Kurs unter EMA200"]) if ok else None


def s_rsi(d, i, side):
    r = d["rsi"]
    a = d["atr"].iat[i]
    c = d["close"].iat[i]
    if side == "long":
        ok = r.iat[i - 1] < 30 <= r.iat[i] and c > d["ema200"].iat[i]
        return _mk("rsi", d, i, side, min(d["low"].iat[i], d["low"].iat[i - 1]) - 0.5 * a, 1.5, 2.5,
                   ["RSI kommt aus überverkauft zurück", "Kurs über EMA200"]) if ok else None
    ok = r.iat[i - 1] > 70 >= r.iat[i] and c < d["ema200"].iat[i]
    return _mk("rsi", d, i, side, max(d["high"].iat[i], d["high"].iat[i - 1]) + 0.5 * a, 1.5, 2.5,
               ["RSI kommt aus überkauft zurück", "Kurs unter EMA200"]) if ok else None


def s_squeeze(d, i, side):
    if not (d["bb_width"].iat[i - 1] <= d["bb_width_q"].iat[i - 1]):
        return None
    c = d["close"].iat[i]
    a = d["atr"].iat[i]
    if side == "long" and c > d["bb_up"].iat[i]:
        return _mk("squeeze", d, i, side, min(d["bb_mid"].iat[i], c - 1.5 * a), 1.5, 3,
                   ["Bänder sehr eng (Squeeze)", "Schluss über oberem Band"])
    if side == "short" and c < d["bb_lo"].iat[i]:
        return _mk("squeeze", d, i, side, max(d["bb_mid"].iat[i], c + 1.5 * a), 1.5, 3,
                   ["Bänder sehr eng (Squeeze)", "Schluss unter unterem Band"])
    return None


def s_fib(d, i, side):
    sh, sl = d["sh"].iat[i], d["sl"].iat[i]
    shi, sli = d["sh_idx"].iat[i], d["sl_idx"].iat[i]
    if not (np.isfinite(sh) and np.isfinite(sl)):
        return None
    rng = sh - sl
    a = d["atr"].iat[i]
    if rng < 4 * a:
        return None
    o, c, lo, hi = d["open"].iat[i], d["close"].iat[i], d["low"].iat[i], d["high"].iat[i]
    if side == "long" and sli < shi:  # Aufwärtsimpuls: Tief -> Hoch
        p618, p65, p786 = sh - 0.618 * rng, sh - 0.65 * rng, sh - 0.786 * rng
        first = d["low"].iloc[int(shi) + 1:i].min() > p618 if i - shi > 1 else True
        if first and lo <= p618 and c > p786 and c > o and c > p65:
            return _mk("fib", d, i, side, p786 - 0.25 * a, 0, 0, ["Rücksetzer in Golden Pocket 61,8–65 %", "Bullische Umkehrkerze"],
                       target1=sh, target2=sh + 0.272 * rng)
    if side == "short" and shi < sli:  # Abwärtsimpuls: Hoch -> Tief
        p618, p65, p786 = sl + 0.618 * rng, sl + 0.65 * rng, sl + 0.786 * rng
        first = d["high"].iloc[int(sli) + 1:i].max() < p618 if i - sli > 1 else True
        if first and hi >= p618 and c < p786 and c < o and c < p65:
            return _mk("fib", d, i, side, p786 + 0.25 * a, 0, 0, ["Rücksetzer in Golden Pocket 61,8–65 %", "Bärische Umkehrkerze"],
                       target1=sl, target2=sl - 0.272 * rng)
    return None


def s_sweep(d, i, side):
    a = d["atr"].iat[i]
    c, lo, hi = d["close"].iat[i], d["low"].iat[i], d["high"].iat[i]
    if side == "long":
        lvl = d["sl"].iat[i]
        if np.isfinite(lvl) and lo < lvl - 0.1 * a and c > lvl and d["low"].iat[i - 1] >= lvl:
            t = d["sh"].iat[i]
            return _mk("sweep", d, i, side, lo - 0.25 * a, 1.5, 3,
                       ["Stops unter Swing-Tief abgeholt", "Schluss zurück über dem Tief"],
                       target2=t if np.isfinite(t) and t > c else None)
        return None
    lvl = d["sh"].iat[i]
    if np.isfinite(lvl) and hi > lvl + 0.1 * a and c < lvl and d["high"].iat[i - 1] <= lvl:
        t = d["sl"].iat[i]
        return _mk("sweep", d, i, side, hi + 0.25 * a, 1.5, 3,
                   ["Stops über Swing-Hoch abgeholt", "Schluss zurück unter dem Hoch"],
                   target2=t if np.isfinite(t) and t < c else None)
    return None


RULES = {
    "score": s_score, "donchian": s_donchian, "supertrend": s_supertrend, "macd": s_macd,
    "rsi": s_rsi, "squeeze": s_squeeze, "fib": s_fib, "sweep": s_sweep,
}


def signals_at(d: pd.DataFrame, i: int, trend: str, keys=None, min_score: int = 65) -> list[Signal]:
    out = []
    if i < MIN_BARS:
        return out
    for side in _sides(trend):
        for key in keys or RULES:
            rule = RULES[key]
            s = rule(d, i, side, min_score) if key == "score" else rule(d, i, side)
            if s is not None:
                out.append(s)
    return out


def scan_history(d: pd.DataFrame, trends: pd.Series, keys=None, min_score: int = 65,
                 start: int = MIN_BARS) -> list[Signal]:
    out = []
    tr = trends.values
    for i in range(max(start, MIN_BARS), len(d)):
        out.extend(signals_at(d, i, tr[i], keys, min_score))
    return out
