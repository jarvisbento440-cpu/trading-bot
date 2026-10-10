import numpy as np
import pandas as pd

from signalbot.config import Risk
from signalbot.db import Database
from signalbot.indicators import trend_direction
from signalbot.main import closed_candles
from signalbot.notify import format_signal
from signalbot.strategy import evaluate

HOUR = 3_600_000


def make_df(closes, vol_last=1000.0):
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    vol = np.full(n, 1000.0) + np.random.default_rng(0).normal(0, 50, n)
    vol[-1] = vol_last
    return pd.DataFrame({
        "ts": np.arange(n) * HOUR,
        "open": np.r_[closes[0], closes[:-1]],
        "high": closes * 1.003,
        "low": closes * 0.997,
        "close": closes,
        "volume": vol,
    })


def uptrend_with_breakout():
    rng = np.random.default_rng(1)
    base = 100 + np.cumsum(rng.normal(0.15, 0.4, 300))
    base[-1] = base[-21:-1].max() * 1.02  # Ausbruch auf der letzten Kerze
    return base


def test_long_breakout_scores_high():
    df = make_df(uptrend_with_breakout(), vol_last=3000)
    s = evaluate(df, "up", Risk())
    assert s is not None and s.side == "long"
    assert s.score >= 65
    assert s.stop < s.entry < s.target1 < s.target2
    assert any("Ausbruch" in r for r in s.reasons)


def test_short_mirror():
    closes = 400 - uptrend_with_breakout()  # gespiegelt: Abwärtstrend mit Bruch nach unten
    df = make_df(closes, vol_last=3000)
    s = evaluate(df, "down", Risk())
    assert s is not None and s.side == "short"
    assert s.target2 < s.target1 < s.entry < s.stop


def test_trend_filter_blocks_countertrend():
    df = make_df(uptrend_with_breakout(), vol_last=3000)
    s = evaluate(df, "down", Risk())  # Aufwärts-Ausbruch, aber Tages-Trend abwärts
    assert s is None or (s.side == "short" and s.score < 65)
    assert evaluate(df, "flat", Risk()) is None


def test_trend_direction():
    assert trend_direction(make_df(uptrend_with_breakout())) == "up"
    assert trend_direction(make_df(400 - uptrend_with_breakout())) == "down"


def test_too_little_history():
    assert evaluate(make_df(np.linspace(100, 120, 50)), "up", Risk()) is None


def test_closed_candles_drops_running_bar():
    df = make_df(np.linspace(100, 110, 10))
    last = df["ts"].iloc[-1]
    assert len(closed_candles(df, HOUR, last + HOUR // 2)) == 9
    assert len(closed_candles(df, HOUR, last + HOUR)) == 10


def test_db_roundtrip_and_dedup():
    db = Database(":memory:")
    rows = [[i * HOUR, 1, 2, 0.5, 1.5, 10] for i in range(5)]
    db.save_candles("binance", "BTC/USDT", "1h", rows)
    db.save_candles("binance", "BTC/USDT", "1h", rows)
    assert len(db.candles("binance", "BTC/USDT", "1h")) == 5
    assert db.last_ts("binance", "BTC/USDT", "1h") == 4 * HOUR
    sig = dict(created_at=0, symbol="BTC/USDT", timeframe="1h", bar_ts=HOUR, side="long",
               score=70, entry=1, stop=0.9, target1=1.15, target2=1.25, reasons="x")
    assert db.insert_signal(sig) is True
    assert db.insert_signal(sig) is False


def test_format_signal_german():
    s = evaluate(make_df(uptrend_with_breakout(), 3000), "up", Risk())
    text = format_signal("SOL/USDT", "4h", s)
    assert "SOL/USDT LONG (4h)" in text and "Stop:" in text and "keine Gewinngarantie" in text
