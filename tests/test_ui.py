import json

import numpy as np

from signalbot.config import Config
from signalbot.db import Database
from signalbot.indicators import add_indicators, fibonacci, support_resistance, trend_series
from signalbot.strategy import history_setups
from signalbot.ui import Api, Worker, _clean
from tests.test_bot import HOUR, make_df, uptrend_with_breakout


def test_fibonacci_up_move():
    df = make_df(uptrend_with_breakout())
    fib = fibonacci(df)
    assert fib["direction"] == "up"
    prices = [l["price"] for l in fib["levels"]]
    assert prices == sorted(prices, reverse=True)  # 0 % = Hoch, 100 % = Tief


def test_support_resistance_sides():
    df = make_df(100 + 5 * np.sin(np.arange(300) / 8))
    price = df["close"].iloc[-1]
    for lvl in support_resistance(df):
        assert (lvl["price"] > price) == (lvl["kind"] == "resistance")


def test_trend_series_no_lookahead():
    daily = make_df(uptrend_with_breakout())
    daily["ts"] = daily["ts"] * 24
    ts = daily["ts"].iloc[[0, 250, 299]]
    t = trend_series(daily, 24 * HOUR, ts)
    assert t.iloc[0] == "flat"  # Tageskerze zählt erst nach ihrem Ende
    assert t.iloc[-1] == "up"


def test_history_setups_respects_cooldown():
    d = add_indicators(make_df(uptrend_with_breakout(), 3000))
    trends = d["ts"].map(lambda _: "up")
    setups = history_setups(d, trends, Config().risk, 30, cooldown_bars=6)
    longs = [s.bar_ts for s in setups if s.side == "long"]
    assert all(b - a >= 6 * HOUR for a, b in zip(longs, longs[1:]))


def test_api_chart_json(tmp_path):
    cfg = Config(symbols=["SOL/USDT"], database=str(tmp_path / "t.db"))
    db = Database(cfg.database)
    df = make_df(uptrend_with_breakout())
    rows = df[["ts", "open", "high", "low", "close", "volume"]].values.tolist()
    db.save_candles("binance", "SOL/USDT", "1h", rows)
    db.save_candles("binance", "SOL/USDT", "1d", rows)
    api = Api(cfg, Worker(cfg, sync=False))
    data = json.loads(json.dumps(_clean(api.chart("SOL/USDT", "1h")), allow_nan=False))
    assert len(data["candles"]) == 300 and data["fib"] and "setups" in data
    state = json.loads(json.dumps(_clean(api.state()), allow_nan=False))
    assert state["coins"][0]["symbol"] == "SOL/USDT"
    assert "regime" in state["coins"][0] and state["trend_light"]["rows"]
    assert "sma50" in data
