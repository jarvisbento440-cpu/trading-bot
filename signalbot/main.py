from __future__ import annotations

import argparse
import logging
import sys
import time

from .config import Config, load_config
from .data import make_exchange, sync_all
from .db import Database
from .indicators import trend_series
from .markets import sync_extra
from .notify import Notifier, format_signal

log = logging.getLogger("signalbot")


def closed_candles(df, tf_ms: int, now_ms: int):
    """Entfernt die letzte Kerze, wenn sie noch läuft."""
    if len(df) and df["ts"].iloc[-1] + tf_ms > now_ms:
        return df.iloc[:-1]
    return df


def scan(cfg: Config, ex, db: Database, notifier: Notifier) -> int:
    """Prüft alle Strategien auf der letzten abgeschlossenen Kerze und verschickt neue Signale."""
    from . import hitrates, tracking
    from .backtest import latest_result, stats_for
    from .strategies import BY_KEY, prepare, signals_at

    now = ex.milliseconds()
    bt = latest_result(cfg)
    table = hitrates.load(cfg)
    sent = 0
    from .markets import all_symbols
    from .yahoo import EXCHANGE as YAHOO, is_yahoo

    for symbol in all_symbols(cfg):
        src = YAHOO if is_yahoo(symbol) else ex.id
        daily = db.candles(src, symbol, cfg.trend_timeframe, 400).drop(columns=["time"])
        if cfg.trend_light and cfg.trend_timeframe == "1d":
            sent += _trend_light(symbol, daily, now, db, notifier)
        for tf in cfg.signal_timeframes:
            tf_ms = ex.parse_timeframe(tf) * 1000
            df = closed_candles(db.candles(src, symbol, tf, 600).drop(columns=["time"]), tf_ms, now)
            if len(df) < 220:
                continue
            d = prepare(df.reset_index(drop=True))
            trend = trend_series(daily, ex.parse_timeframe(cfg.trend_timeframe) * 1000, d["ts"]).iloc[-1]
            for sig in signals_at(d, len(d) - 1, trend, [k for k in cfg.strategies if k in BY_KEY], cfg.min_score):
                log.info("%s %s: %s %s", symbol, tf, sig.strategy, sig.side)
                last = db.last_signal_bar(symbol, tf, sig.side, sig.strategy)
                if last is not None and sig.bar_ts - last < cfg.risk.cooldown_bars * tf_ms:
                    continue
                is_new = db.insert_signal({
                    "created_at": now, "strategy": sig.strategy, "symbol": symbol, "timeframe": tf,
                    "bar_ts": sig.bar_ts, "side": sig.side, "score": sig.score, "entry": sig.entry,
                    "stop": sig.stop, "target1": sig.target1, "target2": sig.target2,
                    "reasons": "; ".join(sig.reasons),
                })
                if is_new:
                    setup, hr = tracking.expected_for(table, d, len(d) - 1, sig.strategy, tf, sig.side, sig.score)
                    tracking.remember(db, sig.strategy, symbol, tf, sig.bar_ts, sig.side, setup, hr)
                    hist = None if hr else stats_for(bt, sig.strategy, tf, sig.score if sig.strategy == "score" else None)
                    notifier.send(format_signal(symbol, tf, sig, BY_KEY[sig.strategy].name, hist, hr, setup))
                    sent += 1
    return sent


def _trend_light(symbol: str, daily, now: int, db: Database, notifier: Notifier) -> int:
    """Meldet, wenn die Trendampel auf der letzten Tageskerze umgesprungen ist."""
    from .regime import current, format_switch
    r = current(daily, now)
    if not r or not r["switched"]:
        return 0
    if not db.insert_regime_alert(symbol, r["bar_ts"], r["state"]):
        return 0
    log.info("%s Trendampel: %s", symbol, r["state"])
    notifier.send(format_switch(symbol, r))
    return 1


def main() -> None:
    p = argparse.ArgumentParser(description="Krypto-Signal-Bot")
    p.add_argument("command", choices=["ui", "backfill", "once", "run", "backtest", "bericht"], nargs="?", default="ui",
                   help="ui = Oberfläche (Standard), backfill = Historie laden, "
                        "once = einmal prüfen, run = Dauerbetrieb ohne Oberfläche, "
                        "backtest = Strategien an der Vergangenheit testen, "
                        "bericht = Wochenbericht jetzt erstellen und schicken")
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

    if args.command == "bericht":
        from . import paper, tracking
        paper.update(cfg, db)
        text = tracking.weekly_report(cfg, db)
        log.info("Bericht gespeichert: %s", tracking.save_report(cfg, text))
        notifier.send(text)
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
            sync_extra(cfg, ex, db)
            scan(cfg, ex, db, notifier)
            from .tracking import after_update
            after_update(cfg, db, notifier)
        except Exception:
            log.exception("Fehler im Durchlauf, nächster Versuch beim nächsten Intervall")
        time.sleep(cfg.poll_minutes * 60)


if __name__ == "__main__":
    main()
