"""Regelbasierter Score (Stufe 1). Noch keine Wahrscheinlichkeit, die kommt aus dem Backtest."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .config import Risk
from .indicators import add_indicators

MIN_BARS = 210  # EMA200 braucht genug Historie


@dataclass
class Setup:
    side: str            # long / short
    score: int           # 0-100
    entry: float
    stop: float
    target1: float
    target2: float
    bar_ts: int
    reasons: list[str] = field(default_factory=list)


def _score(row: pd.Series, prev: pd.Series, side: str) -> tuple[int, list[str]]:
    up = side == "long"
    sign = 1 if up else -1
    score, reasons = 0, []

    # 1. Trend auf dieser Zeitebene
    if up and row["close"] > row["ema20"] > row["ema50"]:
        score += 20; reasons.append("Kurs über EMA20 > EMA50")
    if not up and row["close"] < row["ema20"] < row["ema50"]:
        score += 20; reasons.append("Kurs unter EMA20 < EMA50")

    # 2a. Ausbruch aus 20-Kerzen-Spanne
    if up and row["close"] > row["hh20"]:
        score += 25; reasons.append("Ausbruch über 20-Kerzen-Hoch")
    if not up and row["close"] < row["ll20"]:
        score += 25; reasons.append("Bruch unter 20-Kerzen-Tief")

    # 2b. Rücksetzer an EMA20 im Trend
    if up and row["low"] <= row["ema20"] < row["close"] and row["close"] > row["ema50"]:
        score += 20; reasons.append("Rücksetzer an EMA20 gehalten")
    if not up and row["high"] >= row["ema20"] > row["close"] and row["close"] < row["ema50"]:
        score += 20; reasons.append("Rücksetzer an EMA20 abgewiesen")

    # 3. Momentum (RSI)
    r = row["rsi"]
    if (up and 50 <= r <= 70) or (not up and 30 <= r <= 50):
        score += 15; reasons.append(f"RSI {r:.0f} im Trendbereich")
    elif (up and r > 75) or (not up and r < 25):
        score -= 15; reasons.append(f"RSI {r:.0f} überdehnt")

    # 4. MACD-Histogramm in Richtung und steigend
    if sign * row["macd_hist"] > 0 and sign * (row["macd_hist"] - prev["macd_hist"]) > 0:
        score += 15; reasons.append("MACD-Momentum dreht mit")

    # 5. Volumen
    vz = row["vol_z"]
    if pd.notna(vz) and vz > 2:
        score += 20; reasons.append("Sehr hohes Volumen")
    elif pd.notna(vz) and vz > 1:
        score += 10; reasons.append("Erhöhtes Volumen")

    return max(0, min(100, score)), reasons


def evaluate(df: pd.DataFrame, higher_trend: str, risk: Risk) -> Setup | None:
    """Bewertet die letzte abgeschlossene Kerze. Gibt das beste Setup oder None zurück."""
    if len(df) < MIN_BARS:
        return None
    d = add_indicators(df)
    row, prev = d.iloc[-1], d.iloc[-2]

    best = None
    for side, needed in (("long", "up"), ("short", "down")):
        if higher_trend != needed:
            continue  # nur mit dem übergeordneten Trend handeln
        score, reasons = _score(row, prev, side)
        reasons.insert(0, f"Übergeordneter Trend {'aufwärts' if side == 'long' else 'abwärts'}")
        if best is None or score > best[1]:
            best = (side, score, reasons)
    if best is None:
        return None

    side, score, reasons = best
    entry = float(row["close"])
    risk_abs = risk.stop_atr * float(row["atr"])
    sign = 1 if side == "long" else -1
    return Setup(
        side=side,
        score=score,
        entry=entry,
        stop=entry - sign * risk_abs,
        target1=entry + sign * risk.target1_r * risk_abs,
        target2=entry + sign * risk.target2_r * risk_abs,
        bar_ts=int(row["ts"]),
        reasons=reasons,
    )
