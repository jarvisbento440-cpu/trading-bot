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
from . import backtest
from .indicators import bollinger, fibonacci, liquidity_zones, trend_series
from .main import closed_candles, scan
from .notify import Notifier
from . import heatmap, markets, paper, regime
from .strategies import BY_KEY, STRATEGIES, prepare, scan_history

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
                markets.sync_extra(self.cfg, ex, db)
                scan(self.cfg, ex, db, notifier)
                paper.update(self.cfg, db)
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
        self.bt_running, self.bt_error = False, None
        self._hm_cache: dict = {}
        self.loading: set[str] = set()
        self._lock = threading.Lock()
        self._ex = None

    def _db(self) -> Database:
        return Database(self.cfg.database)

    def state(self) -> dict:
        db = self._db()
        coins = []
        extra = {x["symbol"]: x for x in markets.load_extra(self.cfg)}
        for sym in markets.all_symbols(self.cfg):
            ex = markets.exchange_for(self.cfg, sym)
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
            light = None
            if self.cfg.trend_light and self.cfg.trend_timeframe == "1d" and len(daily):
                light = regime.current(daily.drop(columns=["time"]), int(time.time() * 1000))
            info = extra.get(sym, {})
            coins.append({"symbol": sym, "price": price, "change24h": change, "trend": trend, "regime": light,
                          "name": info.get("name") or sym.split("/")[0], "kind": info.get("type", "Krypto"),
                          "extra": sym in extra, "loading": sym in self.loading})
        rows = db.conn.execute(
            "SELECT id, created_at, strategy, symbol, timeframe, bar_ts, side, score, entry, stop, target1, target2, reasons, status "
            "FROM signals ORDER BY id DESC LIMIT 50"
        ).fetchall()
        cols = ["id", "created_at", "strategy", "symbol", "timeframe", "bar_ts", "side", "score", "entry", "stop",
                "target1", "target2", "reasons", "status"]
        return {
            "status": self.worker.status,
            "error": self.worker.error,
            "last_update": self.worker.last_update,
            "timeframes": self.cfg.signal_timeframes + [self.cfg.trend_timeframe],
            "min_score": self.cfg.min_score,
            "coins": coins,
            "signals": [dict(zip(cols, r)) for r in rows],
            "strategies": self.strategies(),
            "trend_light": regime.BACKTEST if self.cfg.trend_light else None,
            "backtest_running": self.bt_running,
            "backtest_error": self.bt_error,
        }

    def strategies(self) -> list[dict]:
        bt = backtest.latest_result(self.cfg)
        out = []
        for st in STRATEGIES:
            stats = (bt or {}).get("strategies", {}).get(st.key, {}).get("all") if bt else None
            out.append({"key": st.key, "name": st.name, "short": st.short, "color": st.color,
                        "description": st.description, "enabled": st.key in self.cfg.strategies,
                        "stats": stats if stats and stats.get("trades") else None})
        return out

    def heatmap(self, symbol: str, rng: str) -> dict | None:
        """Liquidations-Heatmap; feinste vorhandene Zeitebene (15m, sonst 1h)."""
        window = heatmap.RANGES.get(rng)
        if not window:
            return None
        db = self._db()
        now = int(time.time() * 1000)
        for tf in ("15m", "1h"):
            tf_ms = TF_MS[tf]
            need = int(window * 2 / tf_ms) + 5
            df = closed_candles(db.candles(markets.exchange_for(self.cfg, symbol), symbol, tf, need).drop(columns=["time"]), tf_ms, now)
            fresh = len(df) and df["ts"].iloc[-1] >= now - 2 * 3_600_000 - tf_ms
            if len(df) < need * 0.6 or (tf == "15m" and not fresh):
                continue  # zu wenig oder veraltete 15m-Daten: 1h nehmen
            df = df.reset_index(drop=True)
            key = (symbol, rng, tf, int(df["ts"].iloc[-1]))
            if key not in self._hm_cache:
                self._hm_cache = {k: v for k, v in self._hm_cache.items() if k[:2] != key[:2]}
                out = heatmap.compute(df, window)
                if out:
                    out.update(range=rng, tf=tf, step=tf_ms // 1000)
                self._hm_cache[key] = out
            return self._hm_cache[key]
        return None

    def _exchange(self):
        if self._ex is None:
            self._ex = make_exchange(self.cfg.exchange)
        return self._ex

    def search(self, q: str) -> list[dict]:
        return markets.search(self.cfg, self._exchange() if self.worker.sync else None, q)

    def watch_add(self, symbol: str, name: str, kind: str) -> bool:
        if not symbol:
            return False
        markets.add(self.cfg, symbol, name, kind)
        if not self.worker.sync:
            return True
        self.loading.add(symbol)

        def job():  # Historie sofort laden, nicht erst beim nächsten Durchlauf
            try:
                db = Database(self.cfg.database)
                if markets.yahoo.is_yahoo(symbol):
                    markets.yahoo.sync(db, symbol)
                else:
                    sync_all(self._exchange(), db, [symbol], self.cfg.store_timeframes, self.cfg.backfill_days)
            except Exception:
                log.exception("Laden von %s fehlgeschlagen", symbol)
            finally:
                self.loading.discard(symbol)

        threading.Thread(target=job, daemon=True).start()
        return True

    def watch_remove(self, symbol: str) -> bool:
        markets.remove(self.cfg, symbol)
        return True

    def paper(self) -> dict:
        db = self._db()
        paper.update(self.cfg, db)  # auch im Offline-Modus mit vorhandenen Kerzen weiterrechnen
        ts = paper.trades(db)
        out = {"all": paper.stats(ts), "light": paper.stats([t for t in ts if t["follows_light"]]),
               "by_strategy": {}, "trades": ts[:2000], "since": min((t["bar_ts"] for t in ts), default=None)}
        for st in STRATEGIES:
            mine = [t for t in ts if t["strategy"] == st.key]
            out["by_strategy"][st.key] = {"name": st.name, "all": paper.stats(mine),
                                          "light": paper.stats([t for t in mine if t["follows_light"]])}
        # Kurve in R über die Zeit (abgeschlossene Trades)
        def curve(sel):
            eq, pts = 0.0, []
            for t in sorted((t for t in sel if t["status"] in ("win", "loss", "timeout")), key=lambda t: t["exit_ts"]):
                eq += t["r"]
                pts.append([t["exit_ts"], eq])
            return pts
        out["curve"] = {"all": curve(ts), "light": curve([t for t in ts if t["follows_light"]])}
        return out

    # ---------- eigene Zeichnungen (Long/Short-Positionen, Linien) ----------
    def _drawings_path(self) -> Path:
        return Path(self.cfg.database).parent / "drawings.json"

    def drawings(self) -> dict:
        try:
            data = json.loads(self._drawings_path().read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_drawings(self, symbol: str, items: list) -> bool:
        if not symbol or not isinstance(items, list):
            return False
        with self._lock:
            data = self.drawings()
            data[symbol] = [x for x in items if isinstance(x, dict)][:200]
            if not data[symbol]:
                data.pop(symbol)
            p = self._drawings_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(p)
        return True

    def backtest_result(self) -> dict | None:
        r = backtest.latest_result(self.cfg)
        if r:
            r = {k: v for k, v in r.items() if k != "trades"}
        return r

    def start_backtest(self, days: int = 365) -> bool:
        if self.bt_running:
            return False
        self.bt_running, self.bt_error = True, None

        def job():
            try:
                db = Database(self.cfg.database)
                ex = make_exchange(self.cfg.exchange)
                sync_all(ex, db, self.cfg.symbols, ["1h", "4h", "1d"], days + 250)
                backtest.save(backtest.run(self.cfg, days, exchange=ex.id), Path(self.cfg.database).parent)
            except Exception as e:
                log.exception("Backtest fehlgeschlagen")
                self.bt_error = str(e)
            finally:
                self.bt_running = False

        threading.Thread(target=job, daemon=True).start()
        return True

    def chart(self, symbol: str, tf: str) -> dict:
        db = self._db()
        ex = markets.exchange_for(self.cfg, symbol)
        tf_ms = TF_MS.get(tf, 3_600_000)
        df = db.candles(ex, symbol, tf, 800)
        if df.empty:
            return {"candles": []}
        df = df.drop(columns=["time"])
        closed = closed_candles(df, tf_ms, int(time.time() * 1000)).reset_index(drop=True)
        d = prepare(closed)
        d["bb_up"], d["bb_lo"] = bollinger(d["close"])
        view_from = int(df["ts"].iloc[max(0, len(df) - 500)])
        view = df[df["ts"] >= view_from]
        dv = d[d["ts"] >= view_from]

        daily = db.candles(ex, symbol, self.cfg.trend_timeframe, 400).drop(columns=["time"])
        trends = trend_series(daily, TF_MS.get(self.cfg.trend_timeframe, 86_400_000), d["ts"])
        sma = []
        if self.cfg.trend_light and self.cfg.trend_timeframe == "1d" and len(daily):
            dd = regime.closed_daily(daily, int(time.time() * 1000)).reset_index(drop=True)
            ma = regime.sma_line(dd)
            # Gilt ab dem Ende der Tageskerze; grün = Ampel an, grau = raus
            sma = [{"time": (int(t) + regime.DAY_MS) // 1000, "value": float(m),
                    "color": "#26a69a" if c > m else "#8b949e"}
                   for t, c, m in zip(dd["ts"], dd["close"], ma) if pd.notna(m) and int(t) + regime.DAY_MS >= view_from]
        first = int(d.index[d["ts"] >= view_from][0]) if len(dv) else len(d)
        setups = scan_history(d, trends, min_score=self.cfg.min_score, start=first)
        bt = backtest.latest_result(self.cfg)
        last_ts = int(d["ts"].iloc[-1]) if len(d) else 0

        def pack(s):
            st = backtest.stats_for(bt, s.strategy, tf, s.score if s.strategy == "score" else None)
            return {"time": s.bar_ts // 1000, "strategy": s.strategy, "name": BY_KEY[s.strategy].name,
                    "side": s.side, "score": s.score, "entry": s.entry, "stop": s.stop,
                    "target1": s.target1, "target2": s.target2, "reasons": s.reasons,
                    "winrate": st.get("winrate") if st else None, "trades": st.get("trades") if st else None,
                    "avg_r": st.get("avg_r") if st else None}

        # Aktuelle Signale: höchstens 6 Kerzen alt
        active = [pack(s) for s in setups if last_ts - s.bar_ts <= 6 * tf_ms]
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
            "ema20": _line(dv, "ema20"),
            "ema50": _line(dv, "ema50"),
            "ema200": _line(dv, "ema200"),
            "bb_up": _line(dv, "bb_up"),
            "bb_lo": _line(dv, "bb_lo"),
            "supertrend": _line(dv, "st_line"),
            "sma50": sma,
            "rsi": _num(d["rsi"].iloc[-1]) if len(d) else None,
            "trend": trends.iloc[-1] if len(trends) else "flat",
            "setups": [pack(s) for s in setups],
            "active": active[-1] if active else None,
            "active_all": active,
            "fib": fibonacci(df),
            "zones": liquidity_zones(df),
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
                if url.path == "/api/backtest":
                    return self._json(api.backtest_result())
                if url.path == "/api/backtest/run":
                    return self._json({"started": api.start_backtest(int(q.get("days", 365)))})
                if url.path == "/api/search":
                    return self._json(api.search(q.get("q", "")))
                if url.path == "/api/watch/add":
                    return self._json({"ok": api.watch_add(q.get("symbol", ""), q.get("name", ""), q.get("type", ""))})
                if url.path == "/api/watch/remove":
                    return self._json({"ok": api.watch_remove(q.get("symbol", ""))})
                if url.path == "/api/drawings":
                    return self._json(api.drawings())
                if url.path == "/api/paper":
                    return self._json(api.paper())
                if url.path == "/api/heatmap":
                    return self._json(api.heatmap(q.get("symbol", ""), q.get("range", "3d")))
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

        def do_POST(self) -> None:
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):
                return self._send(403, b"forbidden", "text/plain")  # nur die eigene Oberflaeche darf speichern
            try:
                n = min(int(self.headers.get("Content-Length", 0)), 1_000_000)
                body = json.loads(self.rfile.read(n) or b"null")
                if url.path == "/api/drawings":
                    return self._json({"ok": api.save_drawings(q.get("symbol", ""), body)})
                self._send(404, b"not found", "text/plain")
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
