"""Signal-Tracking und Wochenbericht.

Der Papier-Test (paper.py) rechnet jedes Signal als virtuellen Trade weiter. Hier kommt dazu:
- Telegram-Nachricht, sobald ein Signal Ziel 1 oder den Stop erreicht (oder die Zeit abläuft),
  mit dem Ergebnis in R und der Trefferquote, die laut Historie zu erwarten war.
- Einmal pro Woche ein Bericht: Ergebnis der Woche, je Strategie, offene Trades, Vergleich
  „erwartet laut Historie“ gegen „tatsächlich“ und der Stand der Trendampel.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import hitrates, markets, paper, regime
from .config import Config
from .db import Database
from .notify import fmt_price

log = logging.getLogger(__name__)
WEEK_MS = 7 * 86_400_000
NOTIFY_MAX_AGE_MS = 2 * 86_400_000  # ältere Ergebnisse (z. B. nach langer Pause) nicht mehr einzeln melden

SCHEMA = """
CREATE TABLE IF NOT EXISTS signal_expect (
    signal_id INTEGER PRIMARY KEY,
    setup     INTEGER,      -- Setup-Score beim Signal
    grp       TEXT,         -- Gruppe der Trefferquoten-Tabelle
    winrate   REAL,         -- erwartete Trefferquote laut Historie
    n         INTEGER
);
CREATE TABLE IF NOT EXISTS signal_notes (
    signal_id INTEGER PRIMARY KEY,   -- Ergebnis wurde gemeldet
    sent_at   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
    week    TEXT PRIMARY KEY,        -- z. B. 2026-W43
    sent_at INTEGER NOT NULL
);
"""

RESULT_TEXT = {"win": ("✅", "Ziel 1 erreicht"), "loss": ("❌", "Stop erreicht"), "timeout": ("⏱", "Zeit abgelaufen")}


def ensure(db: Database) -> None:
    paper.ensure(db)
    db.conn.executescript(SCHEMA)


def remember(db: Database, strategy: str, symbol: str, tf: str, bar_ts: int, side: str, setup: int,
             h: dict | None) -> None:
    """Setup-Score und erwartete Trefferquote eines verschickten Signals merken."""
    ensure(db)
    row = db.conn.execute("SELECT id FROM signals WHERE strategy=? AND symbol=? AND timeframe=? AND bar_ts=? AND side=?",
                          (strategy, symbol, tf, bar_ts, side)).fetchone()
    if not row:
        return
    signal_id = row[0]
    db.conn.execute("INSERT OR REPLACE INTO signal_expect VALUES (?,?,?,?,?)",
                    (signal_id, setup, h["group"] if h else None, h["winrate"] if h else None, h["n"] if h else None))
    db.conn.commit()


def _names() -> dict:
    from .strategies import BY_KEY
    return {k: v.name for k, v in BY_KEY.items()}


def _r(x: float | None) -> str:
    return "–" if x is None else f"{x:+.2f} R".replace(".", ",")


def _pct(x: float | None) -> str:
    return "–" if x is None else f"{x * 100:.0f} %"


def format_result(t: dict, expect: float | None = None) -> str:
    icon, what = RESULT_TEXT[t["status"]]
    name = _names().get(t["strategy"], t["strategy"])
    hours = round((t["exit_ts"] - t["entry_ts"]) / 3_600_000) if t.get("exit_ts") and t.get("entry_ts") else None
    lines = [
        f"{icon} {t['symbol']} {t['side'].upper()} ({t['timeframe']}) · {name}: {what}",
        f"Einstieg {fmt_price(t['entry'])} → {fmt_price(t['exit_price'])}, Ergebnis {_r(t['r'])} nach Gebühren"
        + (f", nach {hours} Std." if hours is not None else ""),
    ]
    if expect is not None:
        lines.append(f"Laut Historie treffen solche Signale in {_pct(expect)} der Fälle.")
    return "\n".join(lines)


def notify_closed(db: Database, notifier, now_ms: int | None = None) -> int:
    """Meldet frisch abgeschlossene Papier-Trades einmal per Telegram."""
    ensure(db)
    now = now_ms or int(time.time() * 1000)
    rows = db.conn.execute(
        "SELECT p.*, e.winrate AS expect FROM paper_trades p "
        "LEFT JOIN signal_notes n ON n.signal_id = p.signal_id "
        "LEFT JOIN signal_expect e ON e.signal_id = p.signal_id "
        "WHERE n.signal_id IS NULL AND p.status IN ('win', 'loss', 'timeout')")
    cols = [c[0] for c in rows.description]
    sent = 0
    for r in rows.fetchall():
        t = dict(zip(cols, r))
        if now - (t["exit_ts"] or 0) <= NOTIFY_MAX_AGE_MS:
            notifier.send(format_result(t, t["expect"]))
            sent += 1
        db.conn.execute("INSERT OR IGNORE INTO signal_notes VALUES (?, ?)", (t["signal_id"], now))
    db.conn.commit()
    return sent


def _week_key(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def weekly_report(cfg: Config, db: Database, now_ms: int | None = None) -> str:
    """Bericht über die letzten 7 Tage als Text (Telegram und Datei)."""
    ensure(db)
    now = now_ms or int(time.time() * 1000)
    start = now - WEEK_MS
    names = _names()
    cur = db.conn.execute(
        "SELECT p.*, e.winrate AS expect FROM paper_trades p LEFT JOIN signal_expect e ON e.signal_id = p.signal_id")
    cols = [c[0] for c in cur.description]
    trades = [dict(zip(cols, r)) for r in cur.fetchall()]
    for t in trades:
        t["follows_light"] = paper.follows_light(t)
    week = [t for t in trades if t["status"] in ("win", "loss", "timeout") and (t["exit_ts"] or 0) >= start]
    opened = [t for t in trades if t["bar_ts"] >= start]
    open_now = [t for t in trades if t["status"] == "open"]
    day = lambda ms: datetime.fromtimestamp(ms / 1000).strftime("%d.%m.")  # noqa: E731

    s = paper.stats(week)
    lines = [f"📅 Wochenbericht {day(start)}–{day(now)}", ""]
    lines.append(f"Neue Signale: {len(opened)} · abgeschlossen: {s['trades']} · offen: {len(open_now)}")
    if s["trades"]:
        lines.append(f"Treffer: {s['wins']} von {s['trades']} ({_pct(s['winrate'])}), Ergebnis {_r(s['total_r'])}, "
                     f"Ø {_r(s['avg_r'])} pro Trade")
        exp = [t["expect"] for t in week if t["expect"] is not None]
        if exp:
            lines.append(f"Erwartet laut Historie: {_pct(sum(exp) / len(exp))} Treffer "
                         f"({'besser' if s['winrate'] > sum(exp) / len(exp) else 'schlechter'} als üblich)")
        light = paper.stats([t for t in week if t["follows_light"]])
        if light["trades"]:
            lines.append(f"Nur mit Trendampel: {light['trades']} Trades, {_pct(light['winrate'])}, {_r(light['total_r'])}")
        lines += ["", "Je Strategie:"]
        by: dict[str, list] = {}
        for t in week:
            by.setdefault(t["strategy"], []).append(t)
        for k, ts in sorted(by.items(), key=lambda kv: -sum(t["r"] for t in kv[1])):
            m = paper.stats(ts)
            lines.append(f"• {names.get(k, k)}: {m['wins']}/{m['trades']} Treffer, {_r(m['total_r'])}")
        best = max(week, key=lambda t: t["r"])
        worst = min(week, key=lambda t: t["r"])
        lines += ["", f"Bester Trade: {best['symbol']} {best['side']} ({names.get(best['strategy'], best['strategy'])}) {_r(best['r'])}",
                  f"Schlechtester: {worst['symbol']} {worst['side']} ({names.get(worst['strategy'], worst['strategy'])}) {_r(worst['r'])}"]
    else:
        lines.append("Diese Woche wurde kein Trade abgeschlossen.")
    if open_now:
        lines += ["", "Offen:"]
        for t in sorted(open_now, key=lambda t: t["bar_ts"])[:10]:
            lines.append(f"• {t['symbol']} {t['side']} ({t['timeframe']}, {names.get(t['strategy'], t['strategy'])}): {_r(t['r'])}")
        if len(open_now) > 10:
            lines.append(f"… und {len(open_now) - 10} weitere")
    total = paper.stats(trades)
    if total["trades"]:
        lines += ["", f"Seit Beginn: {total['trades']} Trades, {_pct(total['winrate'])} Treffer, {_r(total['total_r'])}"]
    if cfg.trend_light and cfg.trend_timeframe == "1d":
        lights = []
        for sym in markets.all_symbols(cfg):
            daily = db.candles(markets.exchange_for(cfg, sym), sym, "1d", 400).drop(columns=["time"])
            r = regime.current(daily, now)
            if r:
                lights.append(f"{sym.split('/')[0]} {'🟢' if r['state'] == 'long' else '⚪'}")
        if lights:
            lines += ["", "Trendampel: " + " ".join(lights)]
    lines += ["", "Papier-Test: nichts wurde wirklich gehandelt. Erst ab 30–50 Trades sagt das Ergebnis etwas aus."]
    return "\n".join(lines)


def save_report(cfg: Config, text: str, now_ms: int | None = None) -> Path:
    dt = datetime.fromtimestamp((now_ms or time.time() * 1000) / 1000)
    folder = Path(cfg.database).parent / "berichte"
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"woche-{_week_key(dt)}.md"
    p.write_text(text + "\n", encoding="utf-8")
    return p


def maybe_weekly(cfg: Config, db: Database, notifier, now_ms: int | None = None) -> bool:
    """Schickt den Wochenbericht einmal pro Woche ab dem eingestellten Wochentag und der Uhrzeit (Ortszeit)."""
    if not cfg.weekly_report:
        return False
    ensure(db)
    now = now_ms or int(time.time() * 1000)
    dt = datetime.fromtimestamp(now / 1000)
    due = (dt - timedelta(days=(dt.weekday() - cfg.report_weekday) % 7)).replace(
        hour=cfg.report_hour, minute=0, second=0, microsecond=0)
    if dt < due:
        return False
    key = _week_key(due)
    if db.conn.execute("SELECT 1 FROM reports WHERE week=?", (key,)).fetchone():
        return False
    db.conn.execute("INSERT INTO reports VALUES (?, ?)", (key, now))
    db.conn.commit()
    if not db.conn.execute("SELECT 1 FROM paper_trades LIMIT 1").fetchone():
        return False  # noch nichts aufgezeichnet: keine leere Nachricht
    text = weekly_report(cfg, db, now)
    save_report(cfg, text, now)
    notifier.send(text)
    log.info("Wochenbericht %s verschickt", key)
    return True


def after_update(cfg: Config, db: Database, notifier) -> None:
    """Nach jedem Durchlauf: Papier-Trades weiterrechnen, Ergebnisse melden, ggf. Wochenbericht."""
    paper.update(cfg, db)
    if cfg.track_results:
        notify_closed(db, notifier)
    maybe_weekly(cfg, db, notifier)


def expected_for(table: dict | None, d, i: int, strategy: str, tf: str, side: str, score: int) -> tuple[int, dict | None]:
    """Setup-Score und passende Trefferquote für ein Signal."""
    setup = score if strategy == "score" else hitrates.setup_score(d, i, side)
    return setup, hitrates.lookup(table, strategy, tf, side, setup)
