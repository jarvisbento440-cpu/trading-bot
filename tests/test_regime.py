import numpy as np
import pandas as pd

from signalbot import regime
from signalbot.db import Database

DAY = regime.DAY_MS


def daily(closes):
    c = np.asarray(closes, dtype=float)
    ts = np.arange(len(c)) * DAY + 1_600_000_000_000 // DAY * DAY
    return pd.DataFrame({"ts": ts, "open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1.0})


def test_long_above_sma_and_switch():
    up = np.linspace(100, 200, 120)
    d = daily(up)
    now = int(d["ts"].iloc[-1]) + 2 * DAY
    r = regime.current(d, now)
    assert r["state"] == "long" and 0 < r["size"] <= 1 and not r["switched"]
    crash = daily(np.r_[up, [120.0]])
    r = regime.current(crash, int(crash["ts"].iloc[-1]) + 2 * DAY)
    assert r["state"] == "flat" and r["switched"] and r["size"] == 0
    assert r["since"] == int(crash["ts"].iloc[-1]) + DAY


def test_running_daily_candle_ignored():
    up = np.linspace(100, 200, 120)
    d = daily(np.r_[up, [50.0]])  # letzte Kerze läuft noch
    r = regime.current(d, int(d["ts"].iloc[-1]) + DAY // 2)
    assert r["state"] == "long" and r["close"] == up[-1]


def test_high_volatility_reduces_size():
    rng = np.random.default_rng(1)
    calm = 100 * np.exp(np.cumsum(0.003 + rng.normal(0, 0.01, 200)))
    wild = 100 * np.exp(np.cumsum(0.003 + rng.normal(0, 0.08, 200)))
    a = regime.positions(daily(calm))["size"].iloc[-60:].mean()
    b = regime.positions(daily(wild))["size"].iloc[-60:].mean()
    assert a > b


def test_switch_alert_only_once(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    assert db.insert_regime_alert("BTC/USDT", 1, "long")
    assert not db.insert_regime_alert("BTC/USDT", 1, "long")
