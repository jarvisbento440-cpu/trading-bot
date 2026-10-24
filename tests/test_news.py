import json
import time

from signalbot import context, news, onchain
from signalbot.config import Config
from signalbot.db import Database

H = 3_600_000

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Bitcoin surges to record high as ETF inflows jump</title><link>https://x/1</link>
<pubDate>Fri, 23 Oct 2026 21:32:16 +0000</pubDate></item>
<item><title>Solana DeFi protocol hacked, $50M drained - CoinDesk</title><link>https://x/2</link>
<pubDate>Fri, 23 Oct 2026 20:00:00 GMT</pubDate><source url="https://coindesk.com">CoinDesk</source></item>
<item><title>ohne Datum</title></item>
</channel></rss>"""

ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>XRP Ledger upgrade goes live</title>
<link href="https://y/1"/><updated>2026-10-23T10:00:00Z</updated></entry></feed>"""


def test_parse_rss_and_atom():
    items = news.parse_feed(RSS, "Test")
    assert [i["title"] for i in items] == ["Bitcoin surges to record high as ETF inflows jump",
                                           "Solana DeFi protocol hacked, $50M drained"]
    assert items[1]["source"] == "CoinDesk"  # Google-News-Stil: Quelle aus <source>, aus dem Titel entfernt
    assert items[0]["ts"] == 1792791136000
    a = news.parse_feed(ATOM, "Atom")
    assert a[0]["url"] == "https://y/1" and a[0]["ts"] > 0
    assert news.parse_feed("kaputt <", "x") == []


def test_score_and_coins():
    assert news.score_title("Bitcoin surges to record high as ETF inflows jump") == 2
    assert news.score_title("Solana DeFi protocol hacked, $50M drained") == -2
    assert news.score_title("Ethereum developers meet on Thursday") == 0
    assert news.score_title("Bitcoin to dodge AI crash, analyst says") > -1  # Verneinung schwächt ab
    assert news.score_title("Shorts liquidated as bitcoin rebounds") > 0
    assert news.coins_in("Solana and $ETH rally, sol del dia") == ["ETH", "SOL"]
    assert news.coins_in("XRP price analysis") == ["XRP"]
    assert news.coins_in("console logs") == []  # "sol" klein geschrieben zählt nicht


def _db_with_news(tmp_path, scores, coin="BTC", hours_ago=1):
    db = Database(str(tmp_path / "n.db"))
    now = int(time.time() * 1000)
    db.save_news([{"id": f"id{i}", "ts": now - (hours_ago + i) * H, "source": "T", "title": f"Meldung {i} {s}",
                   "url": "", "coins": coin, "score": s} for i, s in enumerate(scores)])
    return db, now


def test_summary_filter_and_dedupe(tmp_path):
    db, now = _db_with_news(tmp_path, [-1.0, -0.5, 0.0, -0.7])
    s = news.summary(db, "BTC/USDT", now=now)
    assert s["news3_n"] == 4 and s["news3"] == -0.55 and s["filter"] is True
    assert news.summary(db, "ETH/USDT", now=now)["news3"] is None  # zu wenig Meldungen
    db.save_news([{"id": "dup", "ts": now - H, "source": "B", "title": "Meldung 0 -1.0", "coins": "BTC", "score": -1.0}])
    assert news.summary(db, "BTC/USDT", now=now)["news3_n"] == 4  # gleicher Titel zählt einmal


def test_headwind_only_long_for_filter(tmp_path):
    db, now = _db_with_news(tmp_path, [-1.0, -1.0, -1.0])
    cfg = Config(database=str(tmp_path / "n.db"), onchain=False)
    ctx = context.coin_context(db, cfg, "BTC/USDT")
    assert context.headwind(ctx, "long") and not context.headwind(ctx, "short")
    snap = context.snapshot(ctx)
    assert snap["news_filter"] is True and json.dumps(snap)


def test_strong_news_alert_once(tmp_path):
    db, _ = _db_with_news(tmp_path, [-2.0, 0.5, 2.0])
    sent = []

    class N:
        def send(self, t):
            sent.append(t)

    assert context.alert_strong_news(db, ["BTC"], N()) == 1  # zweite starke Meldung: Pause je Coin
    assert context.alert_strong_news(db, ["BTC"], N()) == 0
    assert "BTC" in sent[0]


def test_onchain_view():
    snap = {"ts": 1, "market": {"stables": {"value": 3e11, "chg30": 0.02}},
            "coins": {"BTC": {"funding": 1e-5, "funding7": 5e-5, "oi_usd": 3.5e9, "oi_chg24": 0.05,
                              "hash_ribbon": -0.03, "fee_fast": 3, "mempool_tx": 40000}}}
    v = onchain.view(snap, "BTC/USDT")
    names = [r["name"] for r in v["rows"]]
    assert names[0] == "Funding (Ø 7 Tage)" and "überhitzt" in v["rows"][0]["note"]
    assert "Hashrate 30 T vs. 60 T" in names
    assert v["score"] == 0  # ungetestete Werte geben kein Signal
    assert onchain.view(None, "BTC/USDT")["rows"] == []


def test_onchain_change():
    s = [(i * 86_400_000, 100.0 + i) for i in range(40)]
    assert abs(onchain._change(s, 30) - (139 / 109 - 1)) < 1e-12
    assert onchain._change(s[:1], 30) is None


def test_signals_ctx_column_migration(tmp_path):
    import sqlite3
    p = str(tmp_path / "old.db")
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE signals (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at INTEGER NOT NULL, symbol TEXT NOT NULL, "
              "timeframe TEXT NOT NULL, bar_ts INTEGER NOT NULL, strategy TEXT NOT NULL DEFAULT 'score', side TEXT NOT NULL, "
              "score INTEGER NOT NULL, entry REAL, stop REAL, target1 REAL, target2 REAL, reasons TEXT, "
              "status TEXT NOT NULL DEFAULT 'open', closed_at INTEGER, UNIQUE (strategy, symbol, timeframe, bar_ts, side))")
    c.commit()
    c.close()
    db = Database(p)
    assert db.insert_signal({"created_at": 1, "symbol": "BTC/USDT", "timeframe": "1h", "bar_ts": 1, "side": "long",
                             "score": 0, "entry": 1, "stop": 0.9, "target1": 1.1, "target2": 1.2, "reasons": "",
                             "ctx": "{}"})
    db.set_context("x", {"a": 1})
    assert db.get_context("x") == {"a": 1}
