import sqlite3

import numpy as np
import pandas as pd

from signalbot.backtest import resample, simulate
from signalbot.db import Database
from signalbot.indicators import liquidity_zones
from signalbot.strategies import RULES, Signal, prepare, scan_history
from tests.test_bot import HOUR, make_df, uptrend_with_breakout


def _bars(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"]).assign(
        ts=lambda d: np.arange(len(d)) * HOUR, volume=1.0)


def test_simulate_win_loss_and_same_bar_is_loss():
    d = _bars([[100, 100, 100, 100], [100, 101, 99.5, 100.5], [100.5, 103, 100, 102.5]])
    win = simulate(d, Signal("x", 0, 0, "long", 100, 98, 102, 104), 10)
    assert win["result"] == "win" and win["r"] > 0.85  # 1 R minus Gebühren
    d2 = _bars([[100, 100, 100, 100], [100, 103, 97, 100]])  # Stop und Ziel in derselben Kerze
    assert simulate(d2, Signal("x", 0, 0, "long", 100, 98, 102, 104), 10)["result"] == "loss"


def test_simulate_short_and_open_trade():
    d = _bars([[100, 100, 100, 100], [100, 100.5, 97.5, 98]])
    assert simulate(d, Signal("x", 0, 0, "short", 100, 102, 98, 96), 10)["result"] == "win"
    d3 = _bars([[100, 100, 100, 100], [100, 100.5, 99.5, 100]])
    assert simulate(d3, Signal("x", 0, 0, "long", 100, 98, 102, 104), 10)["result"] == "open"


def test_all_strategies_run_and_respect_trend():
    d = prepare(make_df(uptrend_with_breakout(), 3000))
    sigs = scan_history(d, pd.Series(["up"] * len(d)), min_score=30)
    assert {s.side for s in sigs} <= {"long"}
    for s in sigs:
        assert s.stop < s.entry < s.target1 < s.target2
    assert set(RULES) == {"score", "donchian", "supertrend", "macd", "rsi", "squeeze", "fib", "sweep"}


def test_resample_4h():
    df = make_df(np.linspace(100, 120, 16))
    r = resample(df, 4 * HOUR)
    assert len(r) == 4 and r["high"].iloc[0] == df["high"].iloc[:4].max()


def test_liquidity_zones_shape():
    df = make_df(100 + 5 * np.sin(np.arange(400) / 10) + np.random.default_rng(1).normal(0, .3, 400))
    zones = liquidity_zones(df)
    assert zones and all(z["top"] > z["bottom"] for z in zones)
    price = df["close"].iloc[-1]
    for z in zones:
        if not z["swept"]:
            assert (z["bottom"] > price - 1) if z["kind"] == "buy" else (z["top"] < price + 1)


def test_db_migration_adds_strategy(tmp_path):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE signals (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at INTEGER NOT NULL,
        symbol TEXT NOT NULL, timeframe TEXT NOT NULL, bar_ts INTEGER NOT NULL, side TEXT NOT NULL,
        score INTEGER NOT NULL, entry REAL, stop REAL, target1 REAL, target2 REAL, reasons TEXT,
        status TEXT NOT NULL DEFAULT 'open', closed_at INTEGER, UNIQUE (symbol, timeframe, bar_ts, side))""")
    con.execute("INSERT INTO signals (created_at, symbol, timeframe, bar_ts, side, score) VALUES (1,'BTC/USDT','1h',5,'long',70)")
    con.commit(); con.close()
    db = Database(str(path))
    assert db.conn.execute("SELECT strategy FROM signals").fetchone()[0] == "score"
    base = dict(created_at=2, symbol="BTC/USDT", timeframe="1h", bar_ts=5, side="long", score=0,
                entry=1, stop=0.9, target1=1.1, target2=1.2, reasons="")
    assert db.insert_signal({**base, "strategy": "donchian"}) is True
