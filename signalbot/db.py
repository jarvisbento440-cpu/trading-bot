import sqlite3
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
    side       TEXT NOT NULL,     -- long / short
    score      INTEGER NOT NULL,
    entry REAL, stop REAL, target1 REAL, target2 REAL,
    reasons    TEXT,
    status     TEXT NOT NULL DEFAULT 'open',  -- open / target1 / target2 / stopped / expired
    closed_at  INTEGER,
    UNIQUE (symbol, timeframe, bar_ts, side)
);
"""


class Database:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)

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

    def insert_signal(self, sig: dict) -> bool:
        """Speichert ein Signal. False, wenn es schon existiert."""
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO signals "
            "(created_at, symbol, timeframe, bar_ts, side, score, entry, stop, target1, target2, reasons) "
            "VALUES (:created_at, :symbol, :timeframe, :bar_ts, :side, :score, :entry, :stop, :target1, :target2, :reasons)",
            sig,
        )
        self.conn.commit()
        return cur.rowcount == 1

    def last_signal_bar(self, symbol: str, timeframe: str, side: str) -> int | None:
        row = self.conn.execute(
            "SELECT MAX(bar_ts) FROM signals WHERE symbol=? AND timeframe=? AND side=?",
            (symbol, timeframe, side),
        ).fetchone()
        return row[0]
