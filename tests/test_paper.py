from signalbot import paper
from signalbot.config import Config
from signalbot.db import Database

H = 3_600_000
T0 = 1_700_000_000_000 // H * H


def setup(tmp_path, closes, side="long", stop=95.0, t1=110.0):
    cfg = Config(symbols=["BTC/USDT"], database=str(tmp_path / "p.db"))
    db = Database(cfg.database)
    rows = [[T0 + i * H, c, c + 0.5, c - 0.5, c, 1.0] for i, c in enumerate(closes)]
    db.save_candles(cfg.exchange, "BTC/USDT", "1h", rows)
    db.insert_signal({"created_at": T0, "strategy": "rsi", "symbol": "BTC/USDT", "timeframe": "1h", "bar_ts": T0,
                      "side": side, "score": 0, "entry": closes[0], "stop": stop, "target1": t1, "target2": 120.0,
                      "reasons": ""})
    return cfg, db


def test_win_after_target(tmp_path):
    cfg, db = setup(tmp_path, [100, 101, 104, 108, 111, 112])
    paper.update(cfg, db, now_ms=T0 + 100 * H)
    t = paper.trades(db)[0]
    assert t["status"] == "win" and t["entry"] == 101 and abs(t["r"] - (9 / 6 - 2 * 0.001 * 101 / 6)) < 1e-9
    assert db.conn.execute("SELECT status FROM signals").fetchone()[0] == "target1"


def test_open_then_stop_incrementally(tmp_path):
    cfg, db = setup(tmp_path, [100, 100, 99, 98])
    paper.update(cfg, db, now_ms=T0 + 100 * H)
    t = paper.trades(db)[0]
    assert t["status"] == "open" and t["r"] < 0
    db.save_candles(cfg.exchange, "BTC/USDT", "1h", [[T0 + 4 * H, 98, 98, 94, 94.5, 1.0]])
    paper.update(cfg, db, now_ms=T0 + 100 * H)
    t = paper.trades(db)[0]
    assert t["status"] == "loss" and t["r"] < -1


def test_running_candle_not_used_and_stats(tmp_path):
    cfg, db = setup(tmp_path, [100, 101, 115])
    paper.update(cfg, db, now_ms=T0 + 2 * H + H // 2)  # Kerze 2 läuft noch
    assert paper.trades(db)[0]["status"] == "open"
    s = paper.stats(paper.trades(db))
    assert s["trades"] == 0 and s["open"] == 1
