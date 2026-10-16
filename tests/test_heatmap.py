import base64

import numpy as np
import pandas as pd

from signalbot import heatmap

H = 3_600_000


def candles(closes, vol=None):
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame({"ts": np.arange(len(c)) * H, "open": c, "high": c * 1.001, "low": c * 0.999,
                         "close": c, "volume": vol if vol is not None else np.ones(len(c))})


def test_zones_on_both_sides_and_grid_shape():
    out = heatmap.compute(candles(100 + np.sin(np.arange(200) / 5)), 72 * H, bins=80)
    img = np.frombuffer(base64.b64decode(out["data"]), np.uint8).reshape(len(out["times"]), 80)
    assert img.shape == (72, 80) and img.max() == 255
    price = 100 + np.sin(199 / 5)
    assert all((z["price"] > price) == (z["side"] == "above") for z in out["zones"])
    assert {z["side"] for z in out["zones"]} == {"above", "below"}


def test_liquidity_disappears_when_price_hits_it():
    # Großes Volumen bei 100 legt 10x-Long-Liquidation bei ~90.4 an; danach Absturz auf 85 holt sie ab
    closes = np.r_[np.full(100, 100.0), np.linspace(100, 85, 20), np.full(30, 85.0)]
    vol = np.ones(len(closes)); vol[95] = 1000
    out = heatmap.compute(candles(closes, vol), 100 * H, bins=100)
    img = np.frombuffer(base64.b64decode(out["data"]), np.uint8).reshape(len(out["times"]), 100)
    edges = np.linspace(out["pmin"], out["pmax"], 101)
    b = np.searchsorted(edges, 100 * (1 - 0.1 + heatmap.MMR)) - 1
    t95 = out["times"].index(96 * H // 1000)
    assert img[t95, b] > 100  # Zone sichtbar nach der Kerze mit großem Volumen
    assert img[-1, b] < 20    # nach dem Absturz abgeholt
