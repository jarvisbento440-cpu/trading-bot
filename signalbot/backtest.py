"""Backtest: Wie oft hätten die Signale der letzten N Tage ihr Ziel vor dem Stop erreicht?

Regeln (bewusst vorsichtig):
- Einstieg zum Eröffnungskurs der Kerze nach dem Signal.
- Treffer = Ziel 1 wird vor dem Stop erreicht. Berühren beide dieselbe Kerze, zählt es als Verlust.
- Nach `max_bars` Kerzen ohne Ergebnis wird zum Schlusskurs geschlossen.
- Gebühren: 0,1 % pro Seite.
- Pro Strategie und Coin nur ein offener Trade gleichzeitig.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config
from .db import Database
from .indicators import trend_series
from .strategies import BY_KEY, STRATEGIES, Signal, prepare, scan_history

log = logging.getLogger(__name__)
TF_MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
FEE = 0.001
MAX_BARS = {"1h": 72, "4h": 42}
SCORE_BUCKETS = [(50, 59), (60, 69), (70, 79), (80, 100)]


def resample(df: pd.DataFrame, tf_ms: int) -> pd.DataFrame:
    g = df.assign(bucket=df["ts"] // tf_ms * tf_ms).groupby("bucket")
    out = pd.DataFrame({
        "ts": g["ts"].first().index.astype("int64"),
        "open": g["open"].first().values, "high": g["high"].max().values,
        "low": g["low"].min().values, "close": g["close"].last().values,
        "volume": g["volume"].sum().values,
    })
    return out.reset_index(drop=True)


def load(db: Database, exchange: str, symbol: str, tf: str, limit: int = 100_000) -> pd.DataFrame:
    df = db.candles(exchange, symbol, tf, limit)
    if df.empty and tf == "4h":  # manche Börsen haben keine 4h-Kerzen
        h1 = db.candles(exchange, symbol, "1h", limit * 4)
        if not h1.empty:
            return resample(h1.drop(columns=["time"]), TF_MS["4h"])
    return df.drop(columns=["time"], errors="ignore")


def simulate(d: pd.DataFrame, sig: Signal, max_bars: int) -> dict | None:
    """Spielt einen Trade durch. Gibt None zurück, wenn der Einstieg nicht möglich war."""
    n = len(d)
    j0 = sig.i + 1
    if j0 >= n:
        return None
    o, h, l, c = (d[k].values for k in ("open", "high", "low", "close"))
    long = sig.side == "long"
    entry = o[j0]
    risk = (entry - sig.stop) if long else (sig.stop - entry)
    reward = (sig.target1 - entry) if long else (entry - sig.target1)
    if risk <= 0 or reward <= 0:
        return None  # Kurs ist schon über Stop/Ziel hinaus gelaufen
    fee_r = 2 * FEE * entry / risk
    hit_t2 = False
    for j in range(j0, min(n, j0 + max_bars)):
        stop_hit = l[j] <= sig.stop if long else h[j] >= sig.stop
        t1_hit = h[j] >= sig.target1 if long else l[j] <= sig.target1
        if stop_hit:
            return dict(result="loss", r=-1 - fee_r, bars=j - sig.i, exit_i=j)
        if t1_hit:
            # Ziel 2 vor Rückkehr zum Einstieg?
            for k in range(j, min(n, j0 + max_bars)):
                if (h[k] >= sig.target2) if long else (l[k] <= sig.target2):
                    hit_t2 = True
                    break
                if k > j and ((l[k] <= entry) if long else (h[k] >= entry)):
                    break
            return dict(result="win", r=reward / risk - fee_r, bars=j - sig.i, exit_i=j, t2=hit_t2)
    if j0 + max_bars > n:
        return dict(result="open", r=0.0, bars=n - 1 - sig.i, exit_i=n - 1)
    j = j0 + max_bars - 1
    move = (c[j] - entry) if long else (entry - c[j])
    return dict(result="timeout", r=move / risk - fee_r, bars=j - sig.i, exit_i=j)


def _stats(trades: list[dict]) -> dict:
    closed = [t for t in trades if t["result"] in ("win", "loss", "timeout")]
    n = len(closed)
    if not n:
        return {"trades": 0}
    wins = sum(t["result"] == "win" for t in closed)
    rs = np.array([t["r"] for t in closed])
    gain, loss = rs[rs > 0].sum(), -rs[rs < 0].sum()
    eq = np.cumsum(rs)
    dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
    return {
        "trades": n,
        "wins": int(wins),
        "winrate": wins / n,
        "t2_rate": sum(bool(t.get("t2")) for t in closed) / n,
        "avg_r": float(rs.mean()),
        "total_r": float(rs.sum()),
        "profit_factor": float(gain / loss) if loss > 0 else None,
        "max_dd_r": dd,
        "avg_bars": float(np.mean([t["bars"] for t in closed])),
    }


def run(cfg: Config, days: int = 365, exchange: str | None = None, symbols: list[str] | None = None,
        timeframes=("1h", "4h")) -> dict:
    exchange = exchange or cfg.exchange
    symbols = symbols or cfg.symbols
    db = Database(cfg.database)
    now = int(time.time() * 1000)
    start_ms = now - days * 86_400_000
    trades: list[dict] = []
    coverage = {}
    for sym in symbols:
        daily = load(db, exchange, sym, "1d")
        for tf in timeframes:
            df = load(db, exchange, sym, tf)
            if len(df) < 300:
                log.warning("%s %s: zu wenig Daten (%d Kerzen)", sym, tf, len(df))
                continue
            d = prepare(df)
            trends = trend_series(daily, TF_MS["1d"], d["ts"])
            first = int(np.searchsorted(d["ts"].values, start_ms))
            coverage[f"{sym} {tf}"] = {
                "from": int(d["ts"].iat[max(first, 210)]), "to": int(d["ts"].iat[-1]), "bars": len(d) - first,
            }
            sigs = scan_history(d, trends, min_score=50, start=first)
            busy_until: dict[str, int] = {}
            for s in sigs:
                if s.i <= busy_until.get(s.strategy, -1):
                    continue
                res = simulate(d, s, MAX_BARS.get(tf, 60))
                if res is None:
                    continue
                busy_until[s.strategy] = res["exit_i"]
                trades.append({
                    "strategy": s.strategy, "symbol": sym, "tf": tf, "side": s.side, "score": s.score,
                    "bar_ts": s.bar_ts, "entry": s.entry, "stop": s.stop, "target1": s.target1, **res,
                })
            log.info("%s %s: %d Signale", sym, tf, len(sigs))

    min_score = cfg.min_score
    def live(t):  # Score-Signale unter dem Mindest-Score würden live nicht verschickt
        return t["strategy"] != "score" or t["score"] >= min_score

    by_strategy = {}
    for st in STRATEGIES:
        ts = [t for t in trades if t["strategy"] == st.key and live(t)]
        by_strategy[st.key] = {
            "name": st.name, "all": _stats(ts),
            "long": _stats([t for t in ts if t["side"] == "long"]),
            "short": _stats([t for t in ts if t["side"] == "short"]),
            "by_tf": {tf: _stats([t for t in ts if t["tf"] == tf]) for tf in timeframes},
            "by_symbol": {sym: _stats([t for t in ts if t["symbol"] == sym]) for sym in symbols},
        }
    score_buckets = [
        {"from": lo, "to": hi, **_stats([t for t in trades if t["strategy"] == "score" and lo <= t["score"] <= hi])}
        for lo, hi in SCORE_BUCKETS
    ]
    result = {
        "created_at": now, "days": days, "exchange": exchange, "symbols": symbols,
        "timeframes": list(timeframes), "fee": FEE, "coverage": coverage,
        "overall": _stats([t for t in trades if live(t)]),
        "strategies": by_strategy, "score_buckets": score_buckets,
        "trades": [t for t in trades if live(t)],
    }
    return result


def save(result: dict, folder: str | Path) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / "backtest.json"
    p.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    (folder / "backtest-bericht.md").write_text(report(result), encoding="utf-8")
    return p


def latest_result(cfg: Config) -> dict | None:
    """Neuestes Backtest-Ergebnis: eigener Lauf (data/) oder mitgeliefert (results/)."""
    found = [r for r in (load_result(Path(cfg.database).parent), load_result("results")) if r]
    return max(found, key=lambda r: r.get("created_at", 0)) if found else None


def load_result(folder: str | Path) -> dict | None:
    p = Path(folder) / "backtest.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _pct(x):
    return "–" if x is None else f"{x * 100:.0f} %"


def _num(x, nd=2):
    return "–" if x is None else f"{x:.{nd}f}".replace(".", ",")


def report(r: dict) -> str:
    from datetime import datetime, timezone
    when = datetime.fromtimestamp(r["created_at"] / 1000, timezone.utc).strftime("%d.%m.%Y")
    lines = [
        f"# Backtest {r['days']} Tage (Stand {when})",
        "",
        f"Daten: {r['exchange']}, {', '.join(r['symbols'])}, Zeitebenen {', '.join(r['timeframes'])}. "
        "Treffer = Ziel 1 vor dem Stop. Einstieg zum nächsten Eröffnungskurs, 0,1 % Gebühr pro Seite.",
        "",
        "| Strategie | Trades | Trefferquote | Ø Ergebnis (R) | Summe (R) | Profit-Faktor | Max. Drawdown (R) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    rows = sorted(r["strategies"].items(), key=lambda kv: -(kv[1]["all"].get("avg_r") or -99))
    for key, s in rows:
        a = s["all"]
        if not a.get("trades"):
            lines.append(f"| {s['name']} | 0 | – | – | – | – | – |")
            continue
        lines.append(f"| {s['name']} | {a['trades']} | {_pct(a['winrate'])} | {_num(a['avg_r'])} | "
                     f"{_num(a['total_r'], 1)} | {_num(a['profit_factor'])} | {_num(a['max_dd_r'], 1)} |")
    o = r["overall"]
    if o.get("trades"):
        lines += ["", f"**Alle zusammen:** {o['trades']} Trades, Trefferquote {_pct(o['winrate'])}, "
                      f"Ø {_num(o['avg_r'])} R pro Trade."]
    lines += ["", "## Score-Modell: Trefferquote je Score", "", "| Score | Trades | Trefferquote | Ø R |", "|---|---:|---:|---:|"]
    for b in r["score_buckets"]:
        lines.append(f"| {b['from']}–{b['to']} | {b.get('trades', 0)} | {_pct(b.get('winrate'))} | {_num(b.get('avg_r'))} |")
    lines += ["", "## Je Coin und Zeitebene", ""]
    for key, s in rows:
        lines.append(f"**{s['name']}:** " + ", ".join(
            f"{sym.split('/')[0]} {_pct(v.get('winrate'))} ({v.get('trades', 0)})" for sym, v in s["by_symbol"].items())
            + " · " + ", ".join(f"{tf} {_pct(v.get('winrate'))} ({v.get('trades', 0)})" for tf, v in s["by_tf"].items()))
        lines.append("")
    lines += [
        "## So liest du das",
        "",
        "- **R** ist das Risiko pro Trade (Abstand Einstieg–Stop). +1,5 R heißt: 1,5-mal so viel gewonnen wie riskiert.",
        "- **Ø Ergebnis** über 0 bedeutet: Die Strategie hätte nach Gebühren Geld verdient. Die Trefferquote allein sagt das nicht, "
        "weil Gewinne größer als Verluste sein können.",
        "- **Profit-Faktor** = Summe Gewinne / Summe Verluste. Über 1,2 ist brauchbar, unter 1 verliert Geld.",
        "- Vergangene Ergebnisse sind keine Garantie. Ein Jahr ist eine kurze Zeit, und Märkte ändern sich.",
    ]
    return "\n".join(lines) + "\n"


def stats_for(result: dict | None, strategy: str, tf: str | None = None, score: int | None = None) -> dict | None:
    """Historische Trefferquote für ein Live-Signal."""
    if not result:
        return None
    if strategy == "score" and score is not None:
        for b in result.get("score_buckets", []):
            if b["from"] <= score <= b["to"] and b.get("trades", 0) >= 10:
                return b
    s = result.get("strategies", {}).get(strategy)
    if not s:
        return None
    if tf and s["by_tf"].get(tf, {}).get("trades", 0) >= 10:
        return s["by_tf"][tf]
    return s["all"] if s["all"].get("trades") else None
