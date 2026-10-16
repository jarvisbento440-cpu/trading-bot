"""Liquidations-Heatmap (geschätzt), ähnlich Coinglass/Hyblock.

Idee: In jeder Kerze eröffnen Trader gehebelte Long- und Short-Positionen. Deren Liquidationspreis liegt
bei Long = Preis × (1 − 1/Hebel + Wartungsmarge), bei Short = Preis × (1 + 1/Hebel − Wartungsmarge).
Jede Kerze legt also Liquidität (gewichtet mit ihrem Volumen) auf diese Preise. Ein Niveau bleibt
"offen", bis der Kurs es erreicht (dann sind die Positionen liquidiert und die Liquidität ist abgeholt).

Das ist ein Modell aus Kursen und Volumen, keine echten Positionsdaten. Es zeigt, wo sich besonders viele
Stops/Liquidationen sammeln dürften, also Preise, die der Kurs oft "anläuft".
"""
from __future__ import annotations

import base64

import numpy as np
import pandas as pd

# Hebel und angenommener Anteil des Volumens
LEVERAGE = {10: 0.30, 25: 0.30, 50: 0.25, 100: 0.15}
MMR = 0.004  # Wartungsmarge
RANGES = {"3d": 3 * 86_400_000, "1w": 7 * 86_400_000}


def compute(df: pd.DataFrame, window_ms: int, bins: int = 120, warmup: float = 1.0) -> dict | None:
    """df: Kerzen (ts, open, high, low, close, volume), aufsteigend, nur abgeschlossene.

    Gibt ein Gitter Zeit × Preis zurück (Werte 0–255, base64) plus die stärksten offenen Zonen.
    `warmup`: so viel Zeit vor dem Fenster (in Fensterlängen) zählt mit, damit ältere offene Positionen drin sind.
    """
    if len(df) < 20:
        return None
    end = int(df["ts"].iloc[-1])
    d = df[df["ts"] > end - window_ms * (1 + warmup)].reset_index(drop=True)
    show = (d["ts"] > end - window_ms).to_numpy()
    if show.sum() < 10:
        return None
    hi, lo = d["high"].to_numpy(float), d["low"].to_numpy(float)
    tp = (d["high"] + d["low"] + d["close"]).to_numpy(float) / 3
    qv = d["volume"].to_numpy(float) * tp

    # Niveaus: (Erzeugungs-Kerze, Preis, Menge, Seite)
    lev = np.array(list(LEVERAGE))
    share = np.array(list(LEVERAGE.values()))
    n = len(d)
    long_px = tp[:, None] * (1 - 1 / lev[None, :] + MMR)
    short_px = tp[:, None] * (1 + 1 / lev[None, :] - MMR)
    amt = qv[:, None] * share[None, :] / 2
    born = np.repeat(np.arange(n), len(lev))
    px = np.r_[long_px.ravel(), short_px.ravel()]
    amount = np.r_[amt.ravel(), amt.ravel()]
    born = np.r_[born, born]
    is_long = np.r_[np.ones(n * len(lev), bool), np.zeros(n * len(lev), bool)]

    # Wann wird ein Niveau getroffen? Erste spätere Kerze mit Tief <= Long-Niveau bzw. Hoch >= Short-Niveau
    hit = np.full(len(px), n)
    later_lo = np.minimum.accumulate(lo[::-1])[::-1]  # Minimum ab Kerze i bis Ende
    later_hi = np.maximum.accumulate(hi[::-1])[::-1]
    for k in range(len(px)):
        b = born[k] + 1
        if b >= n:
            continue
        if is_long[k]:
            if later_lo[b] > px[k]:
                continue
            hit[k] = b + int(np.argmax(lo[b:] <= px[k]))
        else:
            if later_hi[b] < px[k]:
                continue
            hit[k] = b + int(np.argmax(hi[b:] >= px[k]))

    cols = np.flatnonzero(show)
    pmin = float(lo[show].min()) * 0.9
    pmax = float(hi[show].max()) * 1.1
    edges = np.linspace(pmin, pmax, bins + 1)
    bidx = np.clip(np.searchsorted(edges, px) - 1, 0, bins - 1)
    inside = (px >= pmin) & (px <= pmax)

    # Gitter: Niveau ist sichtbar von Kerze born+1 bis hit-1 (danach abgeholt)
    grid = np.zeros((len(cols), bins))
    c0 = cols[0]
    for k in np.flatnonzero(inside):
        a, z = max(born[k] + 1, c0), min(hit[k], n)
        if z > a:
            grid[a - c0:z - c0, bidx[k]] += amount[k]
    if grid.max() <= 0:
        return None
    # Kumulativ wirkt die Liquidität stärker: sanfte Glättung über benachbarte Preise
    kernel = np.array([0.25, 0.5, 1.0, 0.5, 0.25])
    grid = np.apply_along_axis(lambda r: np.convolve(r, kernel, mode="same"), 1, grid)
    scaled = grid / grid.max()
    img = (scaled * 255).round().astype(np.uint8)

    # Stärkste offene Zonen jetzt (letzte Spalte), oberhalb und unterhalb des Kurses
    last = grid[-1]
    price = float(d["close"].iloc[-1])
    centers = (edges[:-1] + edges[1:]) / 2
    zones = []
    peak = last.max() or 1.0
    for side, mask in (("above", centers > price), ("below", centers < price)):
        idx = np.flatnonzero(mask)
        # lokale Maxima
        cand = [i for i in idx if last[i] > 0 and last[i] >= last[max(i - 1, 0)] and last[i] >= last[min(i + 1, bins - 1)]]
        for i in sorted(cand, key=lambda i: -last[i])[:3]:
            zones.append({"side": side, "price": float(centers[i]), "low": float(edges[i]), "high": float(edges[i + 1]),
                          "strength": float(last[i] / peak), "distance": float(centers[i] / price - 1) * 100})
    return {
        "times": [int(t) // 1000 for t in d["ts"].to_numpy()[cols]],
        "pmin": pmin, "pmax": pmax, "bins": bins,
        "data": base64.b64encode(img.tobytes()).decode(),  # Zeile = Zeit, Spalte = Preis-Bin (unten -> oben)
        "zones": zones,
    }
