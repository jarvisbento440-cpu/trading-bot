from unittest import mock

from signalbot import markets, yahoo
from signalbot.config import Config
from signalbot.db import Database

H = 3_600_000


def chart_json(ts, close):
    n = len(ts)
    return {"chart": {"result": [{"timestamp": [t // 1000 for t in ts], "indicators": {"quote": [{
        "open": close, "high": [c + 1 for c in close], "low": [c - 1 for c in close], "close": close, "volume": [100] * n}]}}]}}


def test_fetch_drops_live_tick_off_grid():
    ts = [1_700_000_000_000 // H * H + 1_800_000 + i * H for i in range(5)] + [1_700_000_000_000 // H * H + 5 * H + 1_234_000]
    resp = mock.Mock(json=lambda: chart_json(ts, [1.0] * 6), raise_for_status=lambda: None)
    with mock.patch.object(yahoo.requests, "get", return_value=resp):
        rows = yahoo.fetch("^GSPC", "60m", "5d")
    assert len(rows) == 5 and all(r[0] % H == 1_800_000 for r in rows)


def test_to_4h_buckets():
    rows = [[i * H, 1, 2, 0.5, 1.5, 10] for i in range(8)]
    out = yahoo.to_4h(rows)
    assert len(out) == 2 and out[0][2] == 2 and out[0][5] == 40


def test_watchlist_and_exchange(tmp_path):
    cfg = Config(symbols=["BTC/USDT"], database=str(tmp_path / "x.db"))
    markets.add(cfg, "GC=F", "Gold", "Rohstoff")
    markets.add(cfg, "BTC/USDT")  # schon fest drin: nicht doppelt
    assert markets.all_symbols(cfg) == ["BTC/USDT", "GC=F"]
    assert markets.exchange_for(cfg, "GC=F") == "yahoo" and markets.exchange_for(cfg, "BTC/USDT") == cfg.exchange
    markets.remove(cfg, "GC=F")
    assert markets.all_symbols(cfg) == ["BTC/USDT"]


def test_sync_normalizes_daily(tmp_path):
    db = Database(str(tmp_path / "y.db"))
    h1 = [[i * H, 1.0, 2.0, 0.5, 1.5, 5.0] for i in range(48)]
    d1 = [[i * 86_400_000 + 13 * H + 1_800_000, 1.0, 2.0, 0.5, 1.5, 5.0] for i in range(3)]
    with mock.patch.object(yahoo, "fetch", side_effect=[h1, d1]):
        yahoo.sync(db, "^GSPC")
    d = db.candles("yahoo", "^GSPC", "1d")
    assert (d["ts"] % 86_400_000 == 0).all() and len(db.candles("yahoo", "^GSPC", "4h")) == 12
