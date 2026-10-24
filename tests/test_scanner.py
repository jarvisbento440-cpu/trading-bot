import numpy as np
import pandas as pd

from signalbot import scanner
from signalbot.config import Config
from signalbot.db import Database
from signalbot.notify import Notifier

DAY = 86_400_000
T0 = 1_700_000_000_000 // DAY * DAY


def daily(closes, vols=None):
    closes = np.asarray(closes, float)
    vols = np.ones(len(closes)) * 1000 if vols is None else np.asarray(vols, float)
    return pd.DataFrame({"ts": T0 + np.arange(len(closes)) * DAY, "open": closes, "high": closes * 1.01,
                         "low": closes * 0.99, "close": closes, "volume": vols})


def now_after(df):
    return int(df["ts"].iloc[-1]) + DAY + 1  # letzte Kerze ist abgeschlossen


def test_tradable_filters():
    assert scanner.tradable("SUI")
    for b in ("USDC", "FDUSD", "WBTC", "PAXG", "BTCUP", "ETHDOWN", "BNBBULL"):
        assert not scanner.tradable(b)


def test_features_no_lookahead():
    df = daily(np.linspace(100, 200, 120))
    full = scanner.features(df)
    cut = scanner.features(df.iloc[:80])
    pd.testing.assert_frame_equal(full.iloc[:80].reset_index(drop=True), cut.reset_index(drop=True))


def test_days_on_counts_since_switch():
    closes = np.r_[np.linspace(200, 100, 80), np.linspace(100, 140, 20)]
    f = scanner.features(daily(closes))
    assert not f["on"].iloc[60]
    last = f.iloc[-1]
    assert last["on"] and 0 <= last["days_on"] < 20
    assert f["days_on"].iloc[-2] == last["days_on"] - 1


def test_analyze_scores_only_green_and_ranks_strength():
    n = 120
    btc = daily(np.linspace(100, 110, n))
    strong = daily(np.linspace(100, 180, n), vols=np.r_[np.ones(n - 3) * 1000, [5000] * 3])
    weak = daily(np.linspace(100, 112, n))
    down = daily(np.linspace(100, 60, n))
    t = scanner.analyze({"BTC/USDT": btc, "STRONG/USDT": strong, "WEAK/USDT": weak, "DOWN/USDT": down},
                        "BTC/USDT", now_after(btc))
    assert np.isnan(t.loc["DOWN/USDT", "score"]) and not t.loc["DOWN/USDT", "on"]
    assert t.index[0] == "STRONG/USDT"
    assert t.loc["STRONG/USDT", "score"] > t.loc["WEAK/USDT", "score"]
    assert t.loc["STRONG/USDT", "vol_surge"] > 4
    assert abs(t.loc["STRONG/USDT", "rs30"] - (t.loc["STRONG/USDT", "ret30"] - t.loc["BTC/USDT", "ret30"])) < 1e-9


def test_analyze_skips_short_and_stale_history():
    btc = daily(np.linspace(100, 110, 120))
    t = scanner.analyze({"BTC/USDT": btc, "NEW/USDT": daily(np.linspace(1, 2, 30)),
                         "OLD/USDT": daily(np.linspace(1, 2, 100))}, "BTC/USDT", now_after(btc))
    assert list(t.index) == ["BTC/USDT"]


class FakeExchange:
    id = "fake"

    def __init__(self, data):
        self.data = data
        self.markets = {s: {"spot": True, "quote": "USDT", "base": s.split("/")[0], "active": True}
                        for s in [*data, "USDC/USDT", "BTCUP/USDT"]}
        self.now = now_after(next(iter(data.values())))

    def load_markets(self):
        return self.markets

    def fetch_tickers(self):
        vols = {"BTC/USDT": 9e9, "SUI/USDT": 5e8, "TINY/USDT": 1e3, "USDC/USDT": 9e9, "BTCUP/USDT": 9e9,
                "ETH/USDT": 4e9, "PEPE/USDT": 3e8}
        return {s: {"quoteVolume": v, "last": 1.0, "percentage": 1.5} for s, v in vols.items()}

    def milliseconds(self):
        return self.now

    def fetch_ohlcv(self, symbol, tf, since=None, limit=None):
        return self.data[symbol].values.tolist()


def test_run_universe_report_and_daily_telegram(tmp_path, capsys):
    n = 120
    data = {"BTC/USDT": daily(np.linspace(100, 110, n)), "ETH/USDT": daily(np.linspace(100, 90, n)),
            "SUI/USDT": daily(np.linspace(1, 2, n)), "PEPE/USDT": daily(np.linspace(1, 0.5, n)),
            "TINY/USDT": daily(np.linspace(1, 3, n))}
    cfg = Config(symbols=["BTC/USDT", "ETH/USDT"], database=str(tmp_path / "s.db"))
    ex = FakeExchange(data)
    r = scanner.run(cfg, ex)
    syms = [c["symbol"] for c in r["coins"]]
    assert "TINY/USDT" not in syms and "USDC/USDT" not in syms and "BTCUP/USDT" not in syms  # Volumen / Filter
    assert set(syms) == {"BTC/USDT", "ETH/USDT", "SUI/USDT", "PEPE/USDT"}
    assert r["green"] == 2 and r["breadth"] == 50
    assert [c["symbol"] for c in scanner.picks(r, 5)] == ["SUI/USDT"]
    text = scanner.format_report(r)
    assert "SUI" in text and "2 von 4" in text and "kein Kaufsignal" in text

    db = Database(cfg.database)
    note = Notifier("", "")
    assert scanner.maybe_run(cfg, ex, db, note) is not None
    assert scanner.load(cfg)["scanned"] == 4
    assert scanner.maybe_run(cfg, ex, db, note) is None  # zu früh für den nächsten Scan
    cfg.scanner.every_hours = 0
    assert scanner.maybe_run(cfg, ex, db, note) is not None
    out = capsys.readouterr().out
    assert out.count("Coin-Scanner") == 1  # Telegram-Übersicht nur einmal am Tag


def test_api_marks_watched(tmp_path):
    from signalbot import markets
    from signalbot.ui import Api, Worker
    cfg = Config(symbols=["BTC/USDT"], database=str(tmp_path / "s.db"))
    scanner.save(cfg, {"created_at": 1, "coins": [{"symbol": "SUI/USDT", "watched": False}]})
    api = Api(cfg, Worker(cfg, sync=False))
    assert api.scanner()["result"]["coins"][0]["watched"] is False
    markets.add(cfg, "SUI/USDT", "SUI", "Krypto")
    assert api.scanner()["result"]["coins"][0]["watched"] is True
    assert api.start_scanner() is False  # offline: kein Scan
