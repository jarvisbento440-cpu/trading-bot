from __future__ import annotations

import argparse
import logging
import sys
import time

from .config import Config, load_config
from .data import make_exchange, sync_all
from .db import Database
from .indicators import trend_direction
from .notify import Notifier, format_signal
from .strategy import evaluate

log = logging.getLogger("signalbot")


def closed_candles(df, tf_ms: int, now_ms: int):
    """Entfernt die letzte Kerze, wenn sie noch läuft."""
    if len(df) and df["ts"].iloc[-1] + tf_ms > now_ms:
        return df.iloc[:-1]
    return df


def scan(cfg: Config, ex, db: Database, notifier: Notifier) -> int:
    now = ex.milliseconds()
    sent = 0
    for symbol in cfg.symbols:
        trend_df = closed_candles(
            db.candles(ex.id, symbol, cfg.trend_timeframe, 400),
            ex.parse_timeframe(cfg.trend_timeframe) * 1000, now,
        )
        trend = trend_direction(trend_df)
        for tf in cfg.signal_timeframes:
            tf_ms = ex.parse_timeframe(tf) * 1000
            df = closed_candles(db.candles(ex.id, symbol, tf, 500), tf_ms, now)
            setup = evaluate(df, trend, cfg.risk)
            if setup is None:
                continue
            log.info("%s %s: %s Score %d (Trend %s)", symbol, tf, setup.side, setup.score, trend)
            if setup.score < cfg.min_score:
                continue
            last = db.last_signal_bar(symbol, tf, setup.side)
            if last is not None and setup.bar_ts - last < cfg.risk.cooldown_bars * tf_ms:
                continue
            is_new = db.insert_signal({
                "created_at": now, "symbol": symbol, "timeframe": tf, "bar_ts": setup.bar_ts,
                "side": setup.side, "score": setup.score, "entry": setup.entry, "stop": setup.stop,
                "target1": setup.target1, "target2": setup.target2,
                "reasons": "; ".join(setup.reasons),
            })
            if is_new:
                notifier.send(format_signal(symbol, tf, setup))
                sent += 1
    return sent


def main() -> None:
    p = argparse.ArgumentParser(description="Krypto-Signal-Bot")
    p.add_argument("command", choices=["ui", "backfill", "once", "run", "backtest"], nargs="?", default="ui",
                   help="ui = Oberfläche (Standard), backfill = Historie laden, "
                        "once = einmal prüfen, run = Dauerbetrieb ohne Oberfläche, "
                        "backtest = Strategien an der Vergangenheit testen")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--offline", action="store_true", help="Oberfläche ohne Kurs-Aktualisierung")
    p.add_argument("--no-window", action="store_true", help="kein Fenster öffnen")
    p.add_argument("--days", type=int, default=365, help="Backtest-Zeitraum in Tagen")
    p.add_argument("--exchange", help="andere Börse für den Backtest, z. B. coinbaseexchange")
    p.add_argument("--quote", help="andere Quote-Währung, z. B. USD statt USDT")
    p.add_argument("--out", default="data", help="Ordner für die Backtest-Ergebnisse")
    args = p.parse_args()

    # Windows-Konsole: Umlaute und Emojis nicht abstürzen lassen
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(args.config)
    db = Database(cfg.database)
    ex = make_exchange(cfg.exchange)
    notifier = Notifier(cfg.telegram_token, cfg.telegram_chat_id)

    if args.command == "ui":
        from .ui import serve
        serve(cfg, port=args.port, sync=not args.offline, open_browser=not args.no_window)
        return

    if args.command == "backtest":
        from . import backtest
        if args.exchange:
            cfg.exchange = args.exchange
        if args.quote:
            cfg.symbols = [s.split("/")[0] + "/" + args.quote for s in cfg.symbols]
        ex = make_exchange(cfg.exchange)
        sync_all(ex, db, cfg.symbols, ["1h", "4h", "1d"], args.days + 250)
        result = backtest.run(cfg, args.days, exchange=ex.id)
        path = backtest.save(result, args.out)
        print(backtest.report(result))
        log.info("Ergebnis gespeichert: %s", path)
        return

    if args.command == "backfill":
        sync_all(ex, db, cfg.symbols, cfg.store_timeframes, cfg.backfill_days)
        return

    if args.command == "once":
        sync_all(ex, db, cfg.symbols, cfg.store_timeframes, cfg.backfill_days)
        log.info("%d Signal(e) verschickt", scan(cfg, ex, db, notifier))
        return

    notifier.send("🤖 Signal-Bot gestartet: " + ", ".join(cfg.symbols))
    while True:
        try:
            sync_all(ex, db, cfg.symbols, cfg.store_timeframes, cfg.backfill_days)
            scan(cfg, ex, db, notifier)
        except Exception:
            log.exception("Fehler im Durchlauf, nächster Versuch beim nächsten Intervall")
        time.sleep(cfg.poll_minutes * 60)


if __name__ == "__main__":
    main()
