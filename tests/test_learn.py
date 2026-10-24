import numpy as np
import pandas as pd

from signalbot import learn, main
from signalbot.config import Config
from signalbot.db import Database
from signalbot.notify import Notifier
from signalbot.strategies import Signal, prepare
from tests.test_bot import HOUR, make_df, uptrend_with_breakout

DAY = 24 * HOUR


def test_model_learns_simple_pattern_and_explains():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(3000, len(learn.FEATURES)))
    k = learn.FEATURES.index("light_with")
    y = (rng.random(3000) < np.where(X[:, k] > 0, 0.6, 0.3)).astype(float)
    m = learn.Model().fit(X, y)
    hi, lo = X[0].copy(), X[0].copy()
    hi[k], lo[k] = 2, -2
    assert m.predict(np.array([hi]))[0] > m.predict(np.array([lo]))[0] + 0.15
    assert m.explain(lo)[0] == ("Trendampel spricht dafür", m.explain(lo)[0][1]) and m.explain(lo)[0][1] < 0
    back = learn.Model.from_dict(m.to_dict())
    assert np.allclose(back.predict(X[:5]), m.predict(X[:5]))


def test_prior_keeps_base_model_with_few_trades():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(3000, len(learn.FEATURES)))
    y = (rng.random(3000) < 1 / (1 + np.exp(-X[:, 0]))).astype(float)
    base = learn.Model().fit(X, y)
    few = learn.Model(50.0).fit(X[:10], 1 - y[:10], prior=base)  # 10 widersprüchliche Trades
    assert np.abs(few.w - base.w).max() < 0.2


def test_daily_context_has_no_lookahead():
    daily = make_df(uptrend_with_breakout())
    daily["ts"] = daily["ts"] * 24
    ctx = learn._daily_ctx(daily)
    ts = pd.Series([int(daily["ts"].iat[100]), int(daily["ts"].iat[100]) + DAY - HOUR])
    got = learn._asof(ts, ctx, ["dist"], HOUR)["dist"]
    # Die Tageskerze 100 ist erst nach ihrem Ende bekannt: um 23 Uhr noch Kerze 99, danach Kerze 100
    assert got.iat[0] == ctx["dist"].iat[99] and got.iat[1] == ctx["dist"].iat[100]


def test_recent_only_uses_trades_closed_before_signal():
    ts = [
        {"strategy": "rsi", "symbol": "BTC", "bar_ts": 0, "exit_ts": 10, "r": -1.0},
        {"strategy": "rsi", "symbol": "BTC", "bar_ts": 5, "exit_ts": 30, "r": 2.0},
        {"strategy": "rsi", "symbol": "BTC", "bar_ts": 20, "exit_ts": 40, "r": 0.5},
    ]
    learn.add_recent(ts)
    assert ts[0]["recent_strat"] == 0 and ts[1]["recent_strat"] == 0
    assert ts[2]["recent_strat"] == -1 / 6  # nur der erste Trade war vorher fertig


def test_scan_stores_assessment_and_filters(tmp_path, monkeypatch):
    cfg = Config(symbols=["BTC/USDT"], database=str(tmp_path / "s.db"), strategies=["rsi"])
    db = Database(cfg.database)
    closes = uptrend_with_breakout()
    df = make_df(np.r_[closes, closes[-1]])
    db.save_candles(cfg.exchange, "BTC/USDT", "1h", df.values.tolist())
    daily = df.copy()
    daily["ts"] = daily["ts"] * 24 - 300 * DAY
    db.save_candles(cfg.exchange, "BTC/USDT", "1d", daily.values.tolist())
    d = prepare(df.iloc[:-1].reset_index(drop=True))
    i = len(d) - 1
    c = float(d["close"].iat[i])
    sig = Signal("rsi", i, int(d["ts"].iat[i]), "long", c, c * 0.98, c * 1.03, c * 1.05, 0, ["Test"])
    monkeypatch.setattr("signalbot.strategies.signals_at", lambda *a, **k: [sig])

    class Ex:
        id = cfg.exchange

        def milliseconds(self):
            return int(df["ts"].iat[-1]) + HOUR

        def parse_timeframe(self, tf):
            return {"1h": 3600, "4h": 14400, "1d": 86400}[tf]

    sent = []
    n = Notifier("", "")
    n.send = sent.append
    cfg.signal_timeframes = ["1h"]
    main.scan(cfg, Ex(), db, n)
    row = db.conn.execute("SELECT p_win, exp_r, take FROM signal_learn").fetchone()
    assert row is not None and 0 < row[0] < 1
    assert bool(row[2]) == (len(sent) == 1)  # Telegram nur, wenn der Lernfilter durchlässt
    if sent:
        assert "Lernmodell:" in sent[0]
