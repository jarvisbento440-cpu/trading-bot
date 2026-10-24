from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
    exchange  TEXT NOT NULL,
    symbol    TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    ts        INTEGER NOT NULL,  -- Kerzen-Start in ms (UTC)
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (exchange, symbol, timeframe, ts)
);
CREATE TABLE IF NOT EXISTS signals (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at INTEGER NOT NULL,  -- ms
    symbol     TEXT NOT NULL,
    timeframe  TEXT NOT NULL,
    bar_ts     INTEGER NOT NULL,  -- Kerze, auf der das Signal entstand
    strategy   TEXT NOT NULL DEFAULT 'score',
    side       TEXT NOT NULL,     -- long / short
    score      INTEGER NOT NULL,
    entry REAL, stop REAL, target1 REAL, target2 REAL,
    reasons    TEXT,
    ctx        TEXT,              -- News/On-Chain beim Signal (JSON), für die Auswertung
    status     TEXT NOT NULL DEFAULT 'open',  -- open / target1 / target2 / stopped / expired
    closed_at  INTEGER,
    UNIQUE (strategy, symbol, timeframe, bar_ts, side)
);
CREATE TABLE IF NOT EXISTS regime_alerts (
    symbol TEXT NOT NULL,
    bar_ts INTEGER NOT NULL,  -- Tageskerze, auf der die Trendampel umsprang
    state  TEXT NOT NULL,     -- long / flat
    PRIMARY KEY (symbol, bar_ts)
);
CREATE TABLE IF NOT EXISTS news (
    id      TEXT PRIMARY KEY,   -- Hash aus Link/Titel
    ts      INTEGER NOT NULL,   -- Veröffentlichung in ms (UTC)
    source  TEXT,
    title   TEXT NOT NULL,
    url     TEXT,
    coins   TEXT,               -- betroffene Coins, z. B. "BTC,ETH"; leer = allgemeine Marktmeldung
    score   REAL NOT NULL,      -- Stimmung −2 … +2
    alerted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS news_ts ON news (ts);
CREATE TABLE IF NOT EXISTS context (
    key  TEXT PRIMARY KEY,      -- z. B. fear_greed, onchain
    ts   INTEGER NOT NULL,
    data TEXT NOT NULL          -- JSON
);
"""


class Database:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, timeout=30)
        self._migrate()
        self.conn.executescript(SCHEMA)

    def _migrate(self) -> None:
        """Ältere Datenbanken: Spalte `strategy` nachrüsten."""
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(signals)")]
        if cols and "strategy" not in cols:
            self.conn.execute("ALTER TABLE signals RENAME TO signals_old")
            self.conn.executescript(SCHEMA)
            self.conn.execute(
                "INSERT INTO signals (id, created_at, symbol, timeframe, bar_ts, side, score, entry, stop, "
                "target1, target2, reasons, status, closed_at) SELECT id, created_at, symbol, timeframe, bar_ts, "
                "side, score, entry, stop, target1, target2, reasons, status, closed_at FROM signals_old"
            )
            self.conn.execute("DROP TABLE signals_old")
            self.conn.commit()
            cols = [r[1] for r in self.conn.execute("PRAGMA table_info(signals)")]
        if cols and "ctx" not in cols:
            self.conn.execute("ALTER TABLE signals ADD COLUMN ctx TEXT")
            self.conn.commit()

    def save_candles(self, exchange: str, symbol: str, timeframe: str, rows: list[list]) -> int:
        if not rows:
            return 0
        self.conn.executemany(
            "INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?,?)",
            [(exchange, symbol, timeframe, *r[:6]) for r in rows],
        )
        self.conn.commit()
        return len(rows)

    def last_ts(self, exchange: str, symbol: str, timeframe: str) -> int | None:
        row = self.conn.execute(
            "SELECT MAX(ts) FROM candles WHERE exchange=? AND symbol=? AND timeframe=?",
            (exchange, symbol, timeframe),
        ).fetchone()
        return row[0]

    def candles(self, exchange: str, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        df = pd.read_sql_query(
            "SELECT ts, open, high, low, close, volume FROM candles "
            "WHERE exchange=? AND symbol=? AND timeframe=? ORDER BY ts DESC LIMIT ?",
            self.conn,
            params=(exchange, symbol, timeframe, limit),
        )
        df = df.iloc[::-1].reset_index(drop=True)
        df["time"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        return df

    def insert_regime_alert(self, symbol: str, bar_ts: int, state: str) -> bool:
        """Merkt sich einen Trendampel-Wechsel. False, wenn er schon gemeldet wurde."""
        cur = self.conn.execute("INSERT OR IGNORE INTO regime_alerts VALUES (?, ?, ?)", (symbol, bar_ts, state))
        self.conn.commit()
        return cur.rowcount > 0

    def insert_signal(self, sig: dict) -> bool:
        """Speichert ein Signal. False, wenn es schon existiert."""
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO signals "
            "(created_at, strategy, symbol, timeframe, bar_ts, side, score, entry, stop, target1, target2, reasons, ctx) "
            "VALUES (:created_at, :strategy, :symbol, :timeframe, :bar_ts, :side, :score, :entry, :stop, :target1, "
            ":target2, :reasons, :ctx)",
            {"strategy": "score", "ctx": None, **sig},
        )
        self.conn.commit()
        return cur.rowcount == 1

    def signal_id(self, strategy: str, symbol: str, timeframe: str, bar_ts: int, side: str) -> int | None:
        row = self.conn.execute(
            "SELECT id FROM signals WHERE strategy=? AND symbol=? AND timeframe=? AND bar_ts=? AND side=?",
            (strategy, symbol, timeframe, bar_ts, side)).fetchone()
        return row[0] if row else None

    def last_signal_bar(self, symbol: str, timeframe: str, side: str, strategy: str = "score") -> int | None:
        row = self.conn.execute(
            "SELECT MAX(bar_ts) FROM signals WHERE symbol=? AND timeframe=? AND side=? AND strategy=?",
            (symbol, timeframe, side, strategy),
        ).fetchone()
        return row[0]

    # ---------- News und On-Chain ----------
    def save_news(self, rows: list[dict]) -> int:
        """Speichert neue Schlagzeilen, gibt die Anzahl neuer zurück."""
        n = 0
        for r in rows:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO news (id, ts, source, title, url, coins, score) VALUES (?,?,?,?,?,?,?)",
                (r["id"], r["ts"], r.get("source"), r["title"], r.get("url"), r.get("coins", ""), r["score"]))
            n += cur.rowcount
        self.conn.commit()
        return n

    def news_since(self, since_ms: int, coin: str | None = None, limit: int = 500) -> list[dict]:
        cols = ["id", "ts", "source", "title", "url", "coins", "score", "alerted"]
        if coin:
            rows = self.conn.execute(
                f"SELECT {', '.join(cols)} FROM news WHERE ts >= ? AND (',' || coins || ',') LIKE ? "
                "ORDER BY ts DESC LIMIT ?", (since_ms, f"%,{coin},%", limit)).fetchall()
        else:
            rows = self.conn.execute(f"SELECT {', '.join(cols)} FROM news WHERE ts >= ? ORDER BY ts DESC LIMIT ?",
                                     (since_ms, limit)).fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def mark_news_alerted(self, news_id: str) -> bool:
        cur = self.conn.execute("UPDATE news SET alerted = 1 WHERE id = ? AND alerted = 0", (news_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def prune_news(self, before_ms: int) -> None:
        self.conn.execute("DELETE FROM news WHERE ts < ?", (before_ms,))
        self.conn.commit()

    def set_context(self, key: str, data) -> None:
        self.conn.execute("INSERT OR REPLACE INTO context VALUES (?, ?, ?)",
                          (key, int(time.time() * 1000), json.dumps(data)))
        self.conn.commit()

    def get_context(self, key: str, with_ts: bool = False):
        row = self.conn.execute("SELECT ts, data FROM context WHERE key = ?", (key,)).fetchone()
        if not row:
            return (None, None) if with_ts else None
        data = json.loads(row[1])
        return (data, row[0]) if with_ts else data
