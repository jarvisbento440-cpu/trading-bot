"""Historischer Test des Coin-Scanners (läuft über GitHub Actions, dort ist Coinbase erreichbar).

Frage: Hätte man mit dem Scanner in der Vergangenheit bessere Coins gefunden als mit Zufall?

- Daten: Tageskerzen aller USD-Paare auf Coinbase seit 2022 (heute noch gelistete Coins; Coins,
  die inzwischen verschwunden sind, fehlen -> das Ergebnis ist eher zu gut als zu schlecht).
- Jede Woche (Montag, Tagesschluss): die 100 Coins mit dem höchsten 30-Tage-Volumen zu diesem
  Zeitpunkt nehmen und genau wie live bewerten (signalbot.scanner, ohne Blick in die Zukunft).
- Danach messen, wie sich die Coins in den nächsten 7 und 28 Tagen entwickelt haben (Schluss
  zu Schluss, 0,2 % Gebühr für Kauf + Verkauf).
- Die Score-Gewichte wurden vorher festgelegt und hier nicht angepasst.

Aufruf: python scripts/scanner_test.py --out results/scanner
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from signalbot import scanner  # noqa: E402

DAY = 86_400_000
FEE = 0.2  # Prozent, Kauf + Verkauf
TOP = 100
HORIZONS = (7, 28)


def fetch_all(since: str, cache: Path) -> dict:
    import ccxt
    ex = ccxt.coinbaseexchange({"enableRateLimit": True})
    ex.load_markets()
    syms = sorted(s for s, m in ex.markets.items()
                  if m.get("spot") and m.get("quote") == "USD" and scanner.tradable(m.get("base", "")))
    print(f"{len(syms)} USD-Paare", flush=True)
    start = int(pd.Timestamp(since, tz="UTC").timestamp() * 1000)
    cache.mkdir(parents=True, exist_ok=True)
    out = {}
    for i, s in enumerate(syms):
        f = cache / (s.replace("/", "_") + ".csv")
        if f.exists():
            out[s] = pd.read_csv(f)
            continue
        rows, t = [], start
        while True:
            try:
                r = ex.fetch_ohlcv(s, "1d", since=t, limit=300)
            except Exception as e:
                print(f"  {s}: {e}", flush=True)
                time.sleep(1)
                break
            if not r:
                if t < ex.milliseconds() - 300 * DAY:
                    t += 300 * DAY  # Coin noch nicht gelistet: weiterspringen
                    continue
                break
            rows += r
            nt = r[-1][0] + DAY
            if nt <= t or nt > ex.milliseconds():
                break
            t = nt
        if rows:
            df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]).drop_duplicates("ts")
            df = df.sort_values("ts").reset_index(drop=True)
            df.to_csv(f, index=False)
            out[s] = df
        if i % 25 == 0:
            print(f"  {i}/{len(syms)}", flush=True)
    return out


def panel(data: dict) -> dict:
    """Je Coin die Kennzahlen pro Tag plus spätere Renditen (nur für die Auswertung)."""
    feats = {}
    for s, df in data.items():
        if len(df) < scanner.MIN_DAYS + 30:
            continue
        # Lücken (Tage ohne Handel) auffüllen, damit "30 Tage" wirklich 30 Kalendertage sind
        idx = pd.RangeIndex(int(df["ts"].iloc[0]), int(df["ts"].iloc[-1]) + DAY, DAY)
        d = df.set_index("ts").reindex(idx)
        d["close"] = d["close"].ffill()
        d["volume"] = d["volume"].fillna(0)
        d = d.rename_axis("ts").reset_index()
        f = scanner.features(d).set_index("ts")
        for h in HORIZONS:
            f[f"fwd{h}"] = (d["close"].shift(-h) / d["close"] - 1).values * 100 - FEE
        feats[s] = f
    return feats


def evaluate(feats: dict) -> dict:
    btc = feats["BTC/USD"]
    first = max(btc.index[0] + 90 * DAY, int(pd.Timestamp("2022-06-06", tz="UTC").timestamp() * 1000))
    last = max(f.index[-1] for f in feats.values()) - max(HORIZONS) * DAY
    # Montage (Tagesschluss Sonntag -> Kerze mit Start Montag 00:00 ist abgeschlossen am Dienstag; egal, wöchentlich)
    dates = [t for t in range(first, last + 1, 7 * DAY)]
    recs = []
    for t in dates:
        rows = {s: f.loc[t] for s, f in feats.items() if t in f.index and not np.isnan(f.loc[t, "sma"])}
        if len(rows) < 20:
            continue
        x = pd.DataFrame(rows).T
        x = x[x["qvol30"] > 0].sort_values("qvol30", ascending=False).head(TOP)
        for col in x.columns:
            x[col] = pd.to_numeric(x[col], errors="coerce")
        x["on"] = x["on"].astype(bool)
        bret = float(btc.loc[t, "ret30"]) if t in btc.index else 0.0
        x["score"] = scanner.rank_score(x, bret)
        x["rs30"] = x["ret30"] - bret
        x["date"] = t
        x["rank"] = x["score"].rank(ascending=False, method="first")
        # Gegenprobe "Rücksetzer im Aufwärtstrend": grün, aber nah am 50-Tage-Schnitt und schwächer als BTC
        g = x[x["on"]]
        pull = ((1 - g["distance"].rank(pct=True)) + (1 - g["rs30"].rank(pct=True))) / 2
        x["pull_rank"] = pull.rank(ascending=False, method="first").reindex(x.index)
        x["btc_on"] = bool(btc.loc[t, "on"]) if t in btc.index else False
        recs.append(x.rename_axis("symbol").reset_index())
    r = pd.concat(recs, ignore_index=True)
    r["year"] = pd.to_datetime(r["date"], unit="ms").dt.year
    return r


def stats(x: pd.Series) -> dict:
    x = x.dropna()
    return {"n": int(len(x)), "avg": float(x.mean()) if len(x) else None,
            "median": float(x.median()) if len(x) else None, "hit": float((x > 0).mean()) if len(x) else None}


def weekly_curve(r: pd.DataFrame, mask: pd.Series) -> dict:
    """Jede Woche gleich gewichtet die ausgewählten Coins halten (7 Tage), sonst Bargeld."""
    w = r[mask].groupby("date")["fwd7"].mean()
    w = w.reindex(sorted(r["date"].unique())).fillna(0.0)
    eq = (1 + w / 100).cumprod()
    dd = (eq / eq.cummax() - 1).min() * 100
    return {"total": float((eq.iloc[-1] - 1) * 100), "maxdd": float(dd), "weeks": int(len(w)),
            "weeks_invested": int(r[mask]["date"].nunique())}


def report(r: pd.DataFrame) -> dict:
    groups = {
        "Alle Top-100": r["on"] | ~r["on"],
        "Ampel grün": r["on"],
        "Ampel rot": ~r["on"],
        "Scanner Top 5": r["rank"] <= 5,
        "Scanner Top 10": r["rank"] <= 10,
        "Grün, Score unter 50": r["on"] & (r["score"] < 50),
        "Nur BTC": r["symbol"] == "BTC/USD",
    }
    out = {"weeks": int(r["date"].nunique()), "from": int(r["date"].min()), "to": int(r["date"].max()),
           "coins": int(r["symbol"].nunique()), "groups": {}, "by_year": {}, "buckets": [], "components": {}}
    for name, m in groups.items():
        out["groups"][name] = {f"fwd{h}": stats(r.loc[m, f"fwd{h}"]) for h in HORIZONS}
        out["groups"][name]["curve"] = weekly_curve(r, m)
    for y, ry in r.groupby("year"):
        out["by_year"][int(y)] = {name: stats(ry.loc[m.loc[ry.index], "fwd7"]) for name, m in groups.items()
                                  if name in ("Alle Top-100", "Ampel grün", "Scanner Top 5", "Nur BTC")}
    g = r[r["on"]]
    for lo in range(0, 100, 20):
        m = (g["score"] >= lo) & (g["score"] < lo + 20 if lo < 80 else g["score"] <= 100)
        out["buckets"].append({"from": lo, "to": lo + 20, **{f"fwd{h}": stats(g.loc[m, f"fwd{h}"]) for h in HORIZONS}})
    # Einzelne Bausteine: Rangkorrelation mit der 7-Tage-Rendite (je Woche, dann gemittelt)
    comps = {"rs30": "Stärke vs. BTC", "vol_surge": "Volumen-Schub", "days_on": "Tage grün (weniger = frischer)",
             "distance": "Abstand 50-T.", "score": "Scanner-Score"}
    for col, label in comps.items():
        ics = g.groupby("date").apply(lambda d: d[col].rank().corr(d["fwd7"].rank()) if len(d) > 5 else np.nan)
        ics = ics.dropna()
        out["components"][label] = {"ic": float(ics.mean()), "t": float(ics.mean() / ics.std() * np.sqrt(len(ics))),
                                    "weeks": int(len(ics))}
    # Varianten getrennt nach Entwicklungs- (bis 2024) und Prüfzeitraum (ab 2025)
    split = int(pd.Timestamp("2025-01-01", tz="UTC").timestamp() * 1000)
    variants = {
        "Ampel grün (alle)": r["on"],
        "Scanner Top 5": r["rank"] <= 5,
        "Rücksetzer Top 5": r["pull_rank"] <= 5,
        "Rücksetzer Top 5, nur wenn BTC grün": (r["pull_rank"] <= 5) & r["btc_on"],
        "Nur BTC": r["symbol"] == "BTC/USD",
        "BTC nur wenn Ampel grün": (r["symbol"] == "BTC/USD") & r["btc_on"],
    }
    out["variants"] = {}
    for name, m in variants.items():
        out["variants"][name] = {}
        for per, pm in (("bis 2024", r["date"] < split), ("ab 2025", r["date"] >= split)):
            rp = r[pm]
            out["variants"][name][per] = {"fwd7": stats(rp.loc[m[pm], "fwd7"]), "fwd28": stats(rp.loc[m[pm], "fwd28"]),
                                          "curve": weekly_curve(rp, m[pm])}
    return out


def to_markdown(o: dict) -> str:
    d = lambda ms: pd.to_datetime(ms, unit="ms").strftime("%d.%m.%Y")  # noqa: E731
    p = lambda x: "–" if x is None else f"{x:+.1f} %".replace(".", ",")  # noqa: E731
    q = lambda x: "–" if x is None else f"{x * 100:.0f} %"  # noqa: E731
    lines = [f"# Coin-Scanner: historischer Test",
             "",
             f"{o['weeks']} Wochen vom {d(o['from'])} bis {d(o['to'])}, {o['coins']} Coins (Coinbase, USD), "
             f"jede Woche die {TOP} mit dem höchsten 30-Tage-Volumen. Renditen nach {str(FEE).replace('.', ',')} % Gebühr.",
             "",
             "| Gruppe | Ø 7 Tage | Treffer 7 T. | Ø 28 Tage | Treffer 28 T. | Wöchentlich gehalten | Max. Rückgang |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for name, g in o["groups"].items():
        lines.append(f"| {name} | {p(g['fwd7']['avg'])} | {q(g['fwd7']['hit'])} | {p(g['fwd28']['avg'])} | "
                     f"{q(g['fwd28']['hit'])} | {p(g['curve']['total'])} | {p(g['curve']['maxdd'])} |")
    lines += ["", "## Score-Stufen (nur grüne Coins)", "", "| Score | Fälle | Ø 7 Tage | Treffer | Ø 28 Tage |",
              "|---|---:|---:|---:|---:|"]
    for b in o["buckets"]:
        lines.append(f"| {b['from']}–{b['to']} | {b['fwd7']['n']} | {p(b['fwd7']['avg'])} | {q(b['fwd7']['hit'])} | "
                     f"{p(b['fwd28']['avg'])} |")
    lines += ["", "## Je Jahr (Ø 7 Tage)", "", "| Jahr | " + " | ".join(next(iter(o["by_year"].values()))) + " |",
              "|---|" + "---:|" * len(next(iter(o["by_year"].values())))]
    for y, g in o["by_year"].items():
        lines.append(f"| {y} | " + " | ".join(p(v["avg"]) for v in g.values()) + " |")
    lines += ["", "## Bausteine (Rangkorrelation mit der 7-Tage-Rendite, grüne Coins)", "",
              "| Baustein | Korrelation | t-Wert |", "|---|---:|---:|"]
    for k, v in o["components"].items():
        ic, t = (f"{v['ic']:+.3f}", f"{v['t']:+.1f}")
        lines.append(f"| {k} | {ic.replace('.', ',')} | {t.replace('.', ',')} |")
    lines += ["", "Korrelation über 0 = höherer Wert ging mit besserer Rendite einher. |t| unter 2 ist meist Zufall."]
    if o.get("variants"):
        lines += ["", "## Varianten: Entwicklung (bis 2024) gegen Prüfung (ab 2025)", "",
                  "| Variante | Ø 7 T. bis 2024 | gehalten bis 2024 | Ø 7 T. ab 2025 | gehalten ab 2025 | Max. Rückgang ab 2025 |",
                  "|---|---:|---:|---:|---:|---:|"]
        for name, v in o["variants"].items():
            a, b = v["bis 2024"], v["ab 2025"]
            lines.append(f"| {name} | {p(a['fwd7']['avg'])} | {p(a['curve']['total'])} | {p(b['fwd7']['avg'])} | "
                         f"{p(b['curve']['total'])} | {p(b['curve']['maxdd'])} |")
        lines += ["", "'Gehalten' = jede Woche gleich gewichtet die ausgewählten Coins kaufen und 7 Tage halten, "
                      "in Wochen ohne Auswahl Bargeld."]
    return "\n".join(lines) + "\n"


def summary(o: dict) -> str:
    g = o["groups"]
    s5, al, gr, rd, bt = (g[k] for k in ("Scanner Top 5", "Alle Top-100", "Ampel grün", "Ampel rot", "Nur BTC"))
    f = lambda x: f"{x:+.1f} %".replace(".", ",")  # noqa: E731
    d = lambda ms: pd.to_datetime(ms, unit="ms").strftime("%m/%Y")  # noqa: E731
    return (f"{o['weeks']} Wochen ({d(o['from'])}–{d(o['to'])}), Coinbase, je Woche die Top {TOP} nach Volumen. "
            f"Ø Rendite in den 7 Tagen danach (nach Gebühr): Scanner Top 5 {f(s5['fwd7']['avg'])}, "
            f"alle grünen {f(gr['fwd7']['avg'])}, alle roten {f(rd['fwd7']['avg'])}, alle Coins {f(al['fwd7']['avg'])}, "
            f"BTC {f(bt['fwd7']['avg'])}. Jede Woche die Top 5 halten: {f(s5['curve']['total'])} "
            f"(größter Rückgang {f(s5['curve']['maxdd'])}), BTC jede Woche: {f(bt['curve']['total'])}. "
            f"Coins, die heute nicht mehr gelistet sind, fehlen, das macht das Ergebnis eher zu gut.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2022-01-01")
    ap.add_argument("--cache", default="/tmp/scanner-cache")
    ap.add_argument("--out", default="results/scanner")
    a = ap.parse_args()
    data = fetch_all(a.since, Path(a.cache))
    r = evaluate(panel(data))
    o = report(r)
    o["summary"] = summary(o)
    o["created_at"] = int(time.time() * 1000)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "scanner-test.json").write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "scanner-test.md").write_text(to_markdown(o) + "\n" + o["summary"] + "\n", encoding="utf-8")
    print(to_markdown(o))
    print(o["summary"])


if __name__ == "__main__":
    main()
