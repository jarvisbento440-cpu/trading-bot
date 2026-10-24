from datetime import datetime

from signalbot import hitrates, paper, tracking
from signalbot.config import Config
from signalbot.db import Database

H = 3_600_000
T0 = 1_700_000_000_000 // H * H


class Sink:
    def __init__(self):
        self.msgs = []

    def send(self, text):
        self.msgs.append(text)


def trade(strategy="rsi", tf="1h", side="long", setup=50, result="win", r=1.4, ts=T0):
    return {"strategy": strategy, "tf": tf, "side": side, "setup": setup, "result": result, "r": r, "bar_ts": ts}


def test_wilson_and_breakeven():
    lo, hi = hitrates.wilson(40, 100)
    assert 0.31 < lo < 0.40 < hi < 0.49
    s = hitrates.summarize([trade(r=1.5)] * 4 + [trade(result="loss", r=-1.0)] * 6)
    assert s["n"] == 10 and s["winrate"] == 0.4 and abs(s["breakeven"] - 0.4) < 1e-9 and abs(s["avg_r"]) < 1e-9


def test_lookup_falls_back_to_coarser_group():
    ts = ([trade(setup=75) for _ in range(20)] + [trade(setup=75, result="loss", r=-1) for _ in range(20)]
          + [trade(setup=20, tf="4h", result="loss", r=-1) for _ in range(5)])
    table = hitrates.build(ts, split_ms=T0 + 1)
    h = hitrates.lookup(table, "rsi", "1h", "long", 78)
    assert h["group"] == "rsi|1h|long|70-79" and h["n"] == 40 and h["winrate"] == 0.5
    h = hitrates.lookup(table, "rsi", "4h", "long", 20)  # 4h hat nur 5 Trades -> ganze Strategie
    assert h["group"] == "rsi" and h["n"] == 45
    assert hitrates.lookup(table, "macd", "1h", "long", 50) is None
    assert "Echte Trefferquote: 50 %" in hitrates.format_line(hitrates.lookup(table, "rsi", "1h", "long", 78))
    assert "Score-Modell" in hitrates.report(table) or "RSI-Rücksetzer" in hitrates.report(table)


def setup_db(tmp_path, closes):
    cfg = Config(symbols=["BTC/USDT"], database=str(tmp_path / "t.db"), trend_light=False)
    db = Database(cfg.database)
    rows = [[T0 + i * H, c, c + 0.5, c - 0.5, c, 1.0] for i, c in enumerate(closes)]
    db.save_candles(cfg.exchange, "BTC/USDT", "1h", rows)
    db.insert_signal({"created_at": T0, "strategy": "rsi", "symbol": "BTC/USDT", "timeframe": "1h", "bar_ts": T0,
                      "side": "long", "score": 0, "entry": closes[0], "stop": 95.0, "target1": 110.0,
                      "target2": 120.0, "reasons": ""})
    tracking.remember(db, "rsi", "BTC/USDT", "1h", T0, "long", 55, {"group": "rsi", "winrate": 0.42, "n": 800})
    return cfg, db


def test_result_is_notified_once(tmp_path):
    cfg, db = setup_db(tmp_path, [100, 101, 104, 108, 111, 112])
    now = T0 + 10 * H
    paper.update(cfg, db, now_ms=now)
    sink = Sink()
    assert tracking.notify_closed(db, sink, now_ms=now) == 1
    assert "Ziel 1 erreicht" in sink.msgs[0] and "42 %" in sink.msgs[0] and "BTC/USDT LONG" in sink.msgs[0]
    assert tracking.notify_closed(db, sink, now_ms=now) == 0


def test_old_results_not_spammed(tmp_path):
    cfg, db = setup_db(tmp_path, [100, 101, 104, 108, 111, 112])
    now = T0 + 10 * 86_400_000
    paper.update(cfg, db, now_ms=now)
    sink = Sink()
    assert tracking.notify_closed(db, sink, now_ms=now) == 0 and not sink.msgs


def test_weekly_report_once_per_week(tmp_path):
    cfg, db = setup_db(tmp_path, [100, 101, 104, 108, 111, 112])
    paper.update(cfg, db, now_ms=T0 + 10 * H)
    text = tracking.weekly_report(cfg, db, now_ms=T0 + 20 * H)
    assert "Wochenbericht" in text and "Treffer: 1 von 1" in text and "Erwartet laut Historie: 42 %" in text
    assert "RSI-Rücksetzer: 1/1" in text

    sink = Sink()
    cfg.report_weekday, cfg.report_hour = datetime.fromtimestamp((T0 + 20 * H) / 1000).weekday(), 0
    assert tracking.maybe_weekly(cfg, db, sink, now_ms=T0 + 20 * H)
    assert not tracking.maybe_weekly(cfg, db, sink, now_ms=T0 + 21 * H)
    assert len(sink.msgs) == 1
    assert list((tmp_path / "berichte").glob("woche-*.md"))
    cfg.weekly_report = False
    assert not tracking.maybe_weekly(cfg, db, sink, now_ms=T0 + 8 * 24 * H)
