from __future__ import annotations

import logging
import time

import ccxt

from .db import Database

log = logging.getLogger(__name__)


def make_exchange(name: str) -> ccxt.Exchange:
    # Nur öffentliche Daten: keine API-Keys nötig
    return getattr(ccxt, name)({"enableRateLimit": True})


def sync_candles(ex: ccxt.Exchange, db: Database, symbol: str, timeframe: str, backfill_days: int) -> int:
    """Lädt fehlende Kerzen nach (beim ersten Mal die ganze Historie)."""
    tf_ms = ex.parse_timeframe(timeframe) * 1000
    last = db.last_ts(ex.id, symbol, timeframe)
    # letzte gespeicherte Kerze neu laden, weil sie evtl. noch nicht fertig war
    since = last if last is not None else ex.milliseconds() - backfill_days * 86_400_000
    total = 0
    while True:
        rows = ex.fetch_ohlcv(symbol, timeframe, since=since, limit=300 if ex.id.startswith("coinbase") else 1000)
        if not rows:
            break
        total += db.save_candles(ex.id, symbol, timeframe, rows)
        next_since = rows[-1][0] + tf_ms
        if next_since <= since or next_since > ex.milliseconds():
            break
        since = next_since
        if len(rows) < 2:
            break
    log.info("%s %s: %d Kerzen aktualisiert", symbol, timeframe, total)
    return total


def sync_all(ex: ccxt.Exchange, db: Database, symbols, timeframes, backfill_days: int) -> None:
    ex.load_markets()
    for symbol in symbols:
        if symbol not in ex.markets:
            log.warning("%s gibt es auf %s nicht, wird übersprungen", symbol, ex.id)
            continue
        for tf in timeframes:
            if ex.timeframes and tf not in ex.timeframes:
                continue  # z. B. kein 4h bei Coinbase, wird beim Backtest aus 1h gebaut
            try:
                sync_candles(ex, db, symbol, tf, backfill_days)
            except ccxt.BaseError as e:
                log.error("Fehler bei %s %s: %s", symbol, tf, e)
                time.sleep(2)
