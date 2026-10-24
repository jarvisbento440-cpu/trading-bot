"""Echte Trefferquoten: Wie oft haben vergleichbare Signale früher ihr Ziel 1 vor dem Stop erreicht?

Grundlage sind alle Signale der 8 Strategien über die lange Kurs-Historie (10 Coins, 1h und 4h,
seit 2021), durchgespielt mit denselben Regeln wie im Backtest und Papier-Test.

Jedes Signal bekommt den Setup-Score (0–100 Punkte aus Trend, Ausbruch, Rücksetzer, RSI, MACD und
Volumen), auch wenn es von einer anderen Strategie kommt. Die Signale werden nach Strategie,
Zeitebene, Richtung und Score-Stufe gruppiert. Pro Gruppe:
- Trefferquote mit 90-%-Spanne (Wilson-Intervall: so genau ist die Zahl bei dieser Menge Trades)
- Gewinnschwelle: Trefferquote, ab der die Gruppe nach Gebühren überhaupt Geld verdient hätte
- Ø Ergebnis in R und dieselben Zahlen nur für das Prüfjahr (Zeit nach SPLIT)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

BUCKETS = [(0, 39), (40, 59), (60, 69), (70, 79), (80, 100)]
MIN_N = 30          # weniger ähnliche Trades: nächst gröbere Gruppe nehmen
Z90 = 1.645
FILE = "trefferquoten.json"


def setup_score(d: pd.DataFrame, i: int, side: str) -> int:
    """Punkte des Score-Modells für eine Kerze, egal welche Strategie das Signal gab."""
    from .strategy import _score
    return _score(d.iloc[i], d.iloc[i - 1], side)[0]


def bucket(score: int) -> str:
    for lo, hi in BUCKETS:
        if lo <= score <= hi:
            return f"{lo}-{hi}"
    return f"{BUCKETS[-1][0]}-{BUCKETS[-1][1]}"


def wilson(k: int, n: int, z: float = Z90) -> tuple[float, float]:
    if not n:
        return 0.0, 1.0
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, mid - half), min(1.0, mid + half)


def summarize(trades: list[dict]) -> dict:
    closed = [t for t in trades if t["result"] in ("win", "loss", "timeout")]
    n = len(closed)
    if not n:
        return {"n": 0}
    wins = [t["r"] for t in closed if t["result"] == "win"]
    rest = [t["r"] for t in closed if t["result"] != "win"]
    lo, hi = wilson(len(wins), n)
    # Gewinnschwelle p: p * Ø Gewinn + (1 - p) * Ø Rest = 0
    be = None
    if wins and rest:
        w, r = sum(wins) / len(wins), sum(rest) / len(rest)
        if w > r:
            be = -r / (w - r)
    return {
        "n": n, "wins": len(wins), "winrate": len(wins) / n, "lo": lo, "hi": hi,
        "t2_rate": sum(bool(t.get("t2")) for t in closed) / n,
        "avg_r": sum(t["r"] for t in closed) / n, "breakeven": be,
    }


def _keys(t: dict) -> list[str]:
    """Gruppen eines Trades, von genau bis grob (gleiche Reihenfolge wie in lookup)."""
    s, tf, side, b = t["strategy"], t["tf"], t["side"], bucket(t["setup"])
    return [f"{s}|{tf}|{side}|{b}", f"{s}|{tf}|{b}", f"{s}|{b}", f"{s}|{tf}|{side}", f"{s}|{tf}", s, f"*|{b}", "*"]


def build(trades: list[dict], split_ms: int, source: str = "", created_at: int = 0) -> dict:
    groups: dict[str, list[dict]] = {}
    for t in trades:
        for k in _keys(t):
            groups.setdefault(k, []).append(t)
    out = {}
    for k, ts in sorted(groups.items()):
        out[k] = {"all": summarize(ts),
                  "dev": summarize([t for t in ts if t["bar_ts"] < split_ms]),
                  "test": summarize([t for t in ts if t["bar_ts"] >= split_ms])}
    first = min((t["bar_ts"] for t in trades), default=0)
    last = max((t["bar_ts"] for t in trades), default=0)
    return {"created_at": created_at, "source": source, "split": split_ms, "from": first, "to": last,
            "buckets": [f"{lo}-{hi}" for lo, hi in BUCKETS], "min_n": MIN_N, "groups": out}


def lookup(table: dict | None, strategy: str, tf: str, side: str, score: int) -> dict | None:
    """Trefferquote der genauesten Gruppe mit genug Trades. Enthält `group` (z. B. 'rsi|4h|long|60-69')."""
    if not table:
        return None
    groups = table.get("groups", {})
    for k in _keys({"strategy": strategy, "tf": tf, "side": side, "setup": score})[:6]:
        g = groups.get(k)
        if g and g["all"].get("n", 0) >= table.get("min_n", MIN_N):
            return {"group": k, **g["all"], "test": g.get("test", {})}
    return None


def load(cfg) -> dict | None:
    """Eigene Neuberechnung (data/) vor mitgelieferter Tabelle (results/trefferquoten/)."""
    for p in (Path(cfg.database).parent / FILE, Path("results") / "trefferquoten" / FILE):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
    return None


def _pct(x) -> str:
    return "–" if x is None else f"{x * 100:.0f} %"


def describe(group: str) -> str:
    """'rsi|4h|long|60-69' -> 'RSI-Rücksetzer, 4h, Long, Score 60–69'"""
    from .strategies import BY_KEY
    parts = group.split("|")
    out = []
    for p in parts:
        if p in BY_KEY:
            out.append(BY_KEY[p].name)
        elif p in ("long", "short"):
            out.append(p.capitalize())
        elif "-" in p:
            out.append("Score " + p.replace("-", "–"))
        elif p != "*":
            out.append(p)
    return ", ".join(out) or "alle Signale"


def verdict(h: dict) -> str:
    """Lag die Gruppe über der Gewinnschwelle, und zwar mehr als der Zufall erklärt?"""
    if h.get("breakeven") is None:
        return ""
    if h["lo"] > h["breakeven"]:
        return "sicher darüber"
    if h["winrate"] > h["breakeven"]:
        return "knapp darüber, kann Zufall sein"
    return "darunter, bisher Verlust"


def format_line(h: dict | None) -> str:
    """Eine Zeile für Telegram und Oberfläche."""
    if not h:
        return "Trefferquote: noch nicht berechnet"
    s = (f"Echte Trefferquote: {_pct(h['winrate'])} (Spanne {_pct(h['lo'])}–{_pct(h['hi'])}, "
         f"{h['n']} ähnliche Signale seit 2021)")
    if h.get("breakeven") is not None:
        s += f"\nGewinnschwelle {_pct(h['breakeven'])}: {verdict(h)} (Ø {h['avg_r']:+.2f} R)"
    t = h.get("test") or {}
    if t.get("n"):
        s += f"\nLetztes Jahr: {_pct(t['winrate'])} aus {t['n']} Signalen"
    return s.replace(".", ",")


def report(table: dict) -> str:
    """Markdown-Bericht: Trefferquote je Score-Stufe für jede Strategie."""
    from datetime import datetime, timezone

    from .strategies import STRATEGIES

    def day(ms):
        return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%d.%m.%Y")

    g = table["groups"]

    def cell(key, part="all"):
        s = g.get(key, {}).get(part, {})
        if not s.get("n"):
            return "–"
        flag = " ✔" if s.get("breakeven") is not None and s["n"] >= MIN_N and s["lo"] > s["breakeven"] else ""
        return f"{_pct(s['winrate'])} ({s['n']}){flag}"

    lines = [
        "# Echte Trefferquoten je Setup-Score",
        "",
        f"Grundlage: {table.get('source', '')}, Signale vom {day(table['from'])} bis {day(table['to'])}. "
        "Treffer = Ziel 1 vor dem Stop, Einstieg zum nächsten Eröffnungskurs, 0,1 % Gebühr pro Seite. "
        f"Prüfjahr = alles ab {day(table['split'])}.",
        "",
        "Jede Zelle: Trefferquote (Zahl der Trades). ✔ = mindestens "
        f"{table.get('min_n', MIN_N)} Trades und auch die vorsichtige Untergrenze der 90-%-Spanne liegt über der Gewinnschwelle.",
        "",
        "## Alle Strategien zusammen",
        "",
        "| Score | Trades | Trefferquote | 90-%-Spanne | Gewinnschwelle | Ø R | Prüfjahr |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for b in [*table["buckets"], None]:
        key = f"*|{b}" if b else "*"
        s, t = g.get(key, {}).get("all", {}), g.get(key, {}).get("test", {})
        if not s.get("n"):
            continue
        lines.append(f"| {b.replace('-', '–') if b else 'alle'} | {s['n']} | {_pct(s['winrate'])} | "
                     f"{_pct(s['lo'])}–{_pct(s['hi'])} | {_pct(s['breakeven'])} | {s['avg_r']:+.2f} | "
                     f"{_pct(t.get('winrate'))} ({t.get('n', 0)}) |".replace(".", ","))
    lines += ["", "## Je Strategie und Score-Stufe", "",
              "| Strategie | " + " | ".join(b.replace("-", "–") for b in table["buckets"]) + " | alle | Gewinnschwelle |",
              "|---|" + "---:|" * (len(table["buckets"]) + 2)]
    for st in STRATEGIES:
        if st.key not in g:
            continue
        be = g[st.key]["all"].get("breakeven")
        lines.append(f"| {st.name} | " + " | ".join(cell(f"{st.key}|{b}") for b in table["buckets"])
                     + f" | {cell(st.key)} | {_pct(be)} |")
    lines += ["", "## Prüfjahr je Strategie und Score-Stufe", "",
              "Dieselbe Tabelle nur für das letzte Jahr. Hält eine Stufe hier nicht, war sie Zufall.", "",
              "| Strategie | " + " | ".join(b.replace("-", "–") for b in table["buckets"]) + " | alle |",
              "|---|" + "---:|" * (len(table["buckets"]) + 1)]
    for st in STRATEGIES:
        if st.key not in g:
            continue
        lines.append(f"| {st.name} | " + " | ".join(cell(f"{st.key}|{b}", "test") for b in table["buckets"])
                     + f" | {cell(st.key, 'test')} |")
    lines += [
        "",
        "## So liest du das",
        "",
        "- **Trefferquote** = Anteil der Signale, die Ziel 1 vor dem Stop erreicht haben.",
        "- **Spanne**: Bei wenigen Trades ist die Zahl ungenau. Die echte Quote liegt mit 90 % Sicherheit in dieser Spanne.",
        "- **Gewinnschwelle**: So hoch muss die Trefferquote mindestens sein, damit nach Gebühren Gewinn bleibt "
        "(hängt vom Chance/Risiko der Strategie ab). Eine Trefferquote von 45 % kann gut sein (Ziel weit weg) "
        "oder schlecht (Ziel nah dran).",
        "- Im Signal steht immer die genaueste Gruppe mit mindestens "
        f"{table.get('min_n', MIN_N)} Trades (Strategie + Zeitebene + Richtung + Score-Stufe, sonst gröber).",
        "- Vergangene Trefferquoten sind keine Garantie für die Zukunft.",
    ]
    return "\n".join(lines) + "\n"


def save(table: dict, folder: str | Path) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / FILE
    p.write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
    (folder / "trefferquoten.md").write_text(report(table), encoding="utf-8")
    return p
