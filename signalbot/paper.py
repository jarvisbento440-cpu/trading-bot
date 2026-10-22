"""Papier-Test: jedes echte Signal wird als virtueller Trade mitgeschrieben und automatisch ausgewertet.

Gleiche Regeln wie im Backtest, damit beides vergleichbar ist:
- Einstieg zum Eröffnungskurs der Kerze nach dem Signal.
- Stop zuerst prüfen (berühren Stop und Ziel dieselbe Kerze, zählt es als Verlust), dann Ziel 1.
- Nach MAX_BARS Kerzen ohne Ergebnis wird zum Schlusskurs geschlossen.
- 0,1 % Gebühr pro Seite, Ergebnis in R (Vielfache des Risikos Einstieg–Stop).
Zusätzlich wird gespeichert, ob die Trendampel beim Signal dafür sprach.
"""
from __future__ import annotations

import logging
import time

import pandas as pd

from .backtest import FEE, MAX_BARS
from .config import Config
from .db import Database
from . import markets, regime

log = logging.getLogger(__name__)
TF_MS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}

SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_trades (
    signal_id  INTEGER PRIMARY KEY,
    strategy   TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    timeframe  TEXT NOT NULL,
    side       TEXT NOT NULL,
    bar_ts     INTEGER NOT NULL,
    entry_ts   INTEGER,
    entry      REAL,
    stop       REAL,
    target1    REAL,
    light      TEXT,              -- Trendampel beim Signal: long / flat / NULL (unbekannt)
    status     TEXT NOT NULL,     -- waiting / open / win / loss / timeout / skipped
    checked_ts INTEGER,           -- letzte ausgewertete Kerze
    exit_ts    INTEGER,
    exit_price REAL,
    r          REAL,              -- Ergebnis nach Gebühren (bei offenen: aktueller Stand)
    bars       INTEGER DEFAULT 0
);
"""


def ensure(db: Database) -> None:
    db.conn.executescript(SCHEMA)


def _candles_after(db: Database, exchange: str, symbol: str, tf: str, after_ts: int) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT ts, open, high, low, close FROM candles WHERE exchange=? AND symbol=? AND timeframe=? AND ts>? ORDER BY ts",
        db.conn, params=(exchange, symbol, tf, after_ts))


def _light_at(db: Database, exchange: str, symbol: str, close_ts: int) -> str | None:
    daily = db.candles(exchange, symbol, "1d", 400).drop(columns=["time"])
    daily = daily[daily["ts"] < close_ts]
    r = regime.current(daily, close_ts)
    return r["state"] if r else None


def follows_light(t: dict) -> bool:
    """Spricht die Trendampel für den Trade? Long nur bei Grün, Short nur bei ausgeschalteter Ampel."""
    return (t["side"] == "long" and t["light"] == "long") or (t["side"] == "short" and t["light"] == "flat")


def update(cfg: Config, db: Database, now_ms: int | None = None) -> int:
    """Neue Signale übernehmen und offene virtuelle Trades weiterrechnen. Gibt Zahl der Änderungen zurück."""
    ensure(db)
    now = now_ms or int(time.time() * 1000)
    changed = 0
    new = db.conn.execute(
        "SELECT s.id, s.strategy, s.symbol, s.timeframe, s.side, s.bar_ts, s.stop, s.target1 FROM signals s "
        "LEFT JOIN paper_trades p ON p.signal_id = s.id WHERE p.signal_id IS NULL").fetchall()
    for sid, strat, sym, tf, side, bar_ts, stop, t1 in new:
        ex = markets.exchange_for(cfg, sym)
        light = _light_at(db, ex, sym, bar_ts + TF_MS.get(tf, 3_600_000))
        db.conn.execute(
            "INSERT INTO paper_trades (signal_id, strategy, symbol, timeframe, side, bar_ts, stop, target1, light, status, checked_ts) "
            "VALUES (?,?,?,?,?,?,?,?,?, 'waiting', ?)", (sid, strat, sym, tf, side, bar_ts, stop, t1, light, bar_ts))
        changed += 1

    rows = db.conn.execute(
        "SELECT signal_id, symbol, timeframe, side, bar_ts, entry, stop, target1, status, checked_ts, bars "
        "FROM paper_trades WHERE status IN ('waiting', 'open')").fetchall()
    for sid, sym, tf, side, bar_ts, entry, stop, t1, status, checked, bars in rows:
        tf_ms = TF_MS.get(tf, 3_600_000)
        c = _candles_after(db, markets.exchange_for(cfg, sym), sym, tf, checked)
        c = c[c["ts"] + tf_ms <= now]  # nur abgeschlossene Kerzen
        if c.empty:
            continue
        long = side == "long"
        upd = {}
        if status == "waiting":
            entry = float(c["open"].iat[0])
            risk = (entry - stop) if long else (stop - entry)
            reward = (t1 - entry) if long else (entry - t1)
            if risk <= 0 or reward <= 0:  # Kurs schon über Stop/Ziel hinaus: Trade wäre nicht möglich gewesen
                db.conn.execute("UPDATE paper_trades SET status='skipped', entry=?, entry_ts=? WHERE signal_id=?",
                                (entry, int(c["ts"].iat[0]), sid))
                changed += 1
                continue
            upd.update(status="open", entry=entry, entry_ts=int(c["ts"].iat[0]))
            status = "open"
        risk = (entry - stop) if long else (stop - entry)
        fee_r = 2 * FEE * entry / risk
        max_bars = MAX_BARS.get(tf, 60)
        last_ts = checked
        for row in c.itertuples():
            bars += 1
            last_ts = int(row.ts)
            stop_hit = row.low <= stop if long else row.high >= stop
            t1_hit = row.high >= t1 if long else row.low <= t1
            if stop_hit:
                upd.update(status="loss", exit_ts=last_ts, exit_price=stop, r=-1 - fee_r)
                break
            if t1_hit:
                upd.update(status="win", exit_ts=last_ts, exit_price=t1, r=abs(t1 - entry) / risk - fee_r)
                break
            if bars >= max_bars:
                move = (row.close - entry) if long else (entry - row.close)
                upd.update(status="timeout", exit_ts=last_ts, exit_price=float(row.close), r=move / risk - fee_r)
                break
            move = (row.close - entry) if long else (entry - row.close)
            upd["r"] = move / risk - fee_r  # Zwischenstand
        upd.update(checked_ts=last_ts, bars=bars)
        sets = ", ".join(f"{k}=?" for k in upd)
        db.conn.execute(f"UPDATE paper_trades SET {sets} WHERE signal_id=?", (*upd.values(), sid))
        # Status in der Signal-Tabelle mitführen
        if upd.get("status") in ("win", "loss", "timeout"):
            db.conn.execute("UPDATE signals SET status=?, closed_at=? WHERE id=?",
                            ({"win": "target1", "loss": "stopped", "timeout": "expired"}[upd["status"]], upd["exit_ts"], sid))
        changed += 1
    db.conn.commit()
    return changed


def trades(db: Database, limit: int = 2000) -> list[dict]:
    ensure(db)
    cur = db.conn.execute("SELECT * FROM paper_trades ORDER BY bar_ts DESC LIMIT ?", (limit,))
    cols = [d[0] for d in cur.description]
    out = [dict(zip(cols, r)) for r in cur.fetchall()]
    for t in out:
        t["follows_light"] = follows_light(t)
    return out


def stats(ts: list[dict]) -> dict:
    closed = [t for t in ts if t["status"] in ("win", "loss", "timeout")]
    open_ = [t for t in ts if t["status"] == "open"]
    n = len(closed)
    rs = [t["r"] for t in closed]
    eq, peak, dd = 0.0, 0.0, 0.0
    for r in sorted(closed, key=lambda t: t["exit_ts"] or 0):
        eq += r["r"]
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return {
        "trades": n, "open": len(open_),
        "wins": sum(t["status"] == "win" for t in closed),
        "winrate": (sum(t["status"] == "win" for t in closed) / n) if n else None,
        "total_r": sum(rs), "avg_r": (sum(rs) / n) if n else None, "max_dd_r": dd,
        "open_r": sum(t["r"] or 0 for t in open_),
    }
