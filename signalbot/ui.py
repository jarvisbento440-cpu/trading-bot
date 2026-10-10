"""Lokale Oberfläche: kleiner Webserver + Fenster mit allen Charts."""
from __future__ import annotations

import json
import logging
import math
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

from .config import Config
from .data import make_exchange, sync_all
from .db import Database
from .indicators import add_indicators, bollinger, fibonacci, support_resistance, trend_series
from .main import closed_candles, scan
from .notify import Notifier
from .strategy import history_setups

log = logging.getLogger(__name__)
WEB = Path(__file__).parent / "web"
TF_MS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8"}


class Worker(threading.Thread):
    """Holt im Hintergrund Kurse und sucht Signale."""

    def __init__(self, cfg: Config, sync: bool):
        super().__init__(daemon=True)
        self.cfg, self.sync = cfg, sync
        self.status = "Starte…" if sync else "Offline (keine Aktualisierung)"
        self.last_update: float | None = None
        self.error: str | None = None

    def run(self) -> None:
        if not self.sync:
            return
        db = Database(self.cfg.database)
        ex = make_exchange(self.cfg.exchange)
        notifier = Notifier(self.cfg.telegram_token, self.cfg.telegram_chat_id)
        first = db.last_ts(ex.id, self.cfg.symbols[0], self.cfg.store_timeframes[0]) is None
        while True:
            try:
                self.status = "Lade Kurs-Historie (erster Start, einige Minuten)…" if first else "Aktualisiere…"
                sync_all(ex, db, self.cfg.symbols, self.cfg.store_timeframes, self.cfg.backfill_days)
                scan(self.cfg, ex, db, notifier)
                first = False
                self.error = None
                self.last_update = time.time()
                self.status = "Live"
            except Exception as e:  # weiterlaufen, nächster Versuch beim nächsten Intervall
                log.exception("Fehler im Durchlauf")
                self.error = str(e)
                self.status = "Fehler, neuer Versuch gleich"
            time.sleep(self.cfg.poll_minutes * 60 if not self.error else 30)


def _num(x) -> float | None:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return float(x)


def _clean(x):
    """NaN/Inf -> None, numpy -> Python, damit es gültiges JSON wird."""
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (bool, str)) or x is None:
        return x
    if isinstance(x, int) and not isinstance(x, bool):
        return x
    try:
        f = float(x)
    except (TypeError, ValueError):
        return x
    if math.isnan(f) or math.isinf(f):
        return None
    return int(f) if hasattr(x, "dtype") and "int" in str(x.dtype) else f


def _line(d: pd.DataFrame, col: str) -> list[dict]:
    return [{"time": int(t) // 1000, "value": float(v)} for t, v in zip(d["ts"], d[col]) if pd.notna(v)]


class Api:
    def __init__(self, cfg: Config, worker: Worker):
        self.cfg, self.worker = cfg, worker

    def _db(self) -> Database:
        return Database(self.cfg.database)

    def state(self) -> dict:
        db = self._db()
        ex = self.cfg.exchange
        coins = []
        for sym in self.cfg.symbols:
            h1 = db.candles(ex, sym, "1h", 30)
            daily = db.candles(ex, sym, self.cfg.trend_timeframe, 400)
            price = change = None
            if len(h1):
                price = float(h1["close"].iloc[-1])
                ref = h1["close"].iloc[-25] if len(h1) >= 25 else h1["open"].iloc[0]
                change = (price / float(ref) - 1) * 100
            trend = "flat"
            if len(daily) >= 60:
                trend = trend_series(daily, TF_MS.get(self.cfg.trend_timeframe, 86_400_000),
                                     pd.Series([int(time.time() * 1000)])).iloc[-1]
            coins.append({"symbol": sym, "price": price, "change24h": change, "trend": trend})
        rows = db.conn.execute(
            "SELECT id, created_at, symbol, timeframe, bar_ts, side, score, entry, stop, target1, target2, reasons, status "
            "FROM signals ORDER BY id DESC LIMIT 50"
        ).fetchall()
        cols = ["id", "created_at", "symbol", "timeframe", "bar_ts", "side", "score", "entry", "stop",
                "target1", "target2", "reasons", "status"]
        return {
            "status": self.worker.status,
            "error": self.worker.error,
            "last_update": self.worker.last_update,
            "timeframes": self.cfg.signal_timeframes + [self.cfg.trend_timeframe],
            "min_score": self.cfg.min_score,
            "coins": coins,
            "signals": [dict(zip(cols, r)) for r in rows],
        }

    def chart(self, symbol: str, tf: str) -> dict:
        db = self._db()
        ex = self.cfg.exchange
        tf_ms = TF_MS.get(tf, 3_600_000)
        df = db.candles(ex, symbol, tf, 700)
        if df.empty:
            return {"candles": []}
        df = df.drop(columns=["time"])
        d = add_indicators(df)
        d["bb_up"], d["bb_lo"] = bollinger(d["close"])
        view = d.tail(500)

        closed = closed_candles(df, tf_ms, int(time.time() * 1000))
        dc = add_indicators(closed)
        daily = db.candles(ex, symbol, self.cfg.trend_timeframe, 400).drop(columns=["time"])
        trends = trend_series(daily, TF_MS.get(self.cfg.trend_timeframe, 86_400_000), dc["ts"])
        setups = history_setups(dc, trends, self.cfg.risk, self.cfg.min_score, self.cfg.risk.cooldown_bars)
        last = setups[-1] if setups else None
        # Ein Setup gilt als aktuell, wenn es höchstens 6 Kerzen alt ist
        active = last if last and (int(dc["ts"].iloc[-1]) - last.bar_ts) <= 6 * tf_ms else None

        return {
            "symbol": symbol,
            "tf": tf,
            "candles": [
                {"time": int(r.ts) // 1000, "open": r.open, "high": r.high, "low": r.low, "close": r.close}
                for r in view.itertuples()
            ],
            "volume": [
                {"time": int(r.ts) // 1000, "value": r.volume,
                 "color": "rgba(38,166,154,0.35)" if r.close >= r.open else "rgba(239,83,80,0.35)"}
                for r in view.itertuples()
            ],
            "ema20": _line(view, "ema20"),
            "ema50": _line(view, "ema50"),
            "ema200": _line(view, "ema200"),
            "bb_up": _line(view, "bb_up"),
            "bb_lo": _line(view, "bb_lo"),
            "rsi": _num(d["rsi"].iloc[-1]),
            "setups": [
                {"time": s.bar_ts // 1000, "side": s.side, "score": s.score, "entry": s.entry, "stop": s.stop,
                 "target1": s.target1, "target2": s.target2, "reasons": s.reasons}
                for s in setups if s.bar_ts >= int(view["ts"].iloc[0])
            ],
            "active": None if active is None else {
                "time": active.bar_ts // 1000, "side": active.side, "score": active.score,
                "entry": active.entry, "stop": active.stop, "target1": active.target1,
                "target2": active.target2, "reasons": active.reasons,
            },
            "fib": fibonacci(df),
            "sr": support_resistance(df),
        }


def make_handler(api: Api):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # Konsole ruhig halten
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path == "/api/state":
                    return self._json(api.state())
                if url.path == "/api/chart":
                    return self._json(api.chart(q.get("symbol", ""), q.get("tf", "4h")))
                path = "index.html" if url.path in ("", "/") else url.path.lstrip("/")
                f = (WEB / path).resolve()
                if WEB.resolve() not in f.parents or not f.is_file():
                    return self._send(404, b"not found", "text/plain")
                self._send(200, f.read_bytes(), CONTENT_TYPES.get(f.suffix, "application/octet-stream"))
            except Exception as e:
                log.exception("Fehler bei %s", self.path)
                self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")

        def _json(self, data) -> None:
            self._send(200, json.dumps(_clean(data)).encode(), "application/json")

    return Handler


def open_window(url: str) -> None:
    """Unter Windows als eigenes Fenster (Edge-App-Modus), sonst im Standard-Browser."""
    if sys.platform == "win32":
        try:
            subprocess.Popen(["cmd", "/c", "start", "", "msedge", f"--app={url}"], shell=False)
            return
        except OSError:
            pass
    webbrowser.open(url)


def serve(cfg: Config, port: int = 8765, sync: bool = True, open_browser: bool = True) -> None:
    worker = Worker(cfg, sync)
    worker.start()
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(Api(cfg, worker)))
    url = f"http://127.0.0.1:{port}"
    print(f"Oberfläche läuft auf {url}  (Fenster schließen + hier Strg+C zum Beenden)")
    if open_browser:
        threading.Timer(1.0, open_window, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
