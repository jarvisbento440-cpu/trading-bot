"""Forschung: Kann der Bot aus seinen Fehlsignalen lernen?

1. Alle 8 Strategien über die ganze Kurs-Historie (Branch "history", Coinbase 2021–2026,
   1h und 4h) laufen lassen, jedes Signal wie im Backtest durchspielen und mit Merkmalen speichern.
2. Walk-forward: Jeden Monat das Lernmodell nur mit vorher abgeschlossenen Trades trainieren
   und die Signale des Monats bewerten (Filter: nur Signale mit erwartetem Ergebnis > 0 R).
3. Einstellungen werden nur bis SPLIT (Entwicklung) gewählt; das letzte Jahr bleibt Prüfjahr.

Aufruf: python scripts/learn_research.py <history-ordner> [ausgabe-ordner]
"""
from __future__ import annotations

import gzip
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from signalbot import learn  # noqa: E402
from signalbot.backtest import MAX_BARS, TF_MS, resample, simulate  # noqa: E402
from signalbot.indicators import trend_series  # noqa: E402
from signalbot.strategies import prepare, scan_history  # noqa: E402

SPLIT = pd.Timestamp("2025-10-11", tz="UTC").value // 1_000_000
WF_START = pd.Timestamp("2022-07-01", tz="UTC").value // 1_000_000
FOCUS = ["BTC", "ETH", "SOL", "XRP", "ONDO"]


def _read(folder: Path, coin: str, tf: str) -> pd.DataFrame:
    df = pd.read_csv(folder / f"{coin}_{tf}.csv.gz")
    gaps = np.flatnonzero(np.diff(df["ts"].values) > 3 * 86_400_000)
    return (df.iloc[gaps[-1] + 1:] if len(gaps) else df).reset_index(drop=True)


def coin_trades(args) -> list[dict]:
    folder, coin, tf = args
    h1 = _read(folder, coin, "1h")
    daily = _read(folder, coin, "1d")
    btc = _read(folder, "BTC", "1d")
    df = h1 if tf == "1h" else resample(h1, TF_MS["4h"])
    d = prepare(df)
    trends = trend_series(daily, TF_MS["1d"], d["ts"])
    bt = learn.bar_table(d, daily, btc, TF_MS[tf])
    sigs = scan_history(d, trends, min_score=65)
    busy: dict[str, int] = {}
    out = []
    for s in sigs:
        if s.i <= busy.get(s.strategy, -1):
            continue
        res = simulate(d, s, MAX_BARS[tf])
        if res is None or res["result"] == "open":
            continue
        busy[s.strategy] = res["exit_i"]
        entry = float(d["open"].iat[s.i + 1])
        f = learn.signal_features(bt, s.i, s.strategy, s.side, tf, entry, s.stop, s.target1,
                                  float(d["atr"].iat[s.i]), s.score)
        out.append({"strategy": s.strategy, "symbol": coin, "tf": tf, "side": s.side, "bar_ts": s.bar_ts,
                    "exit_ts": int(d["ts"].iat[res["exit_i"]]), "entry": entry, "stop": s.stop,
                    "target1": s.target1, "result": res["result"], "r": res["r"], **f})
    return out


def group_filter(trades: list[dict], start_ms: int, keys=("strategy", "tf", "side"), prior: int = 50,
                 step_ms: int = 30 * learn.DAY_MS) -> list[dict]:
    """Einfacher Vergleich ohne KI: Signal nehmen, wenn diese Gruppe (z. B. Strategie+Zeitebene+Richtung)
    bisher im Schnitt Gewinn gebracht hat (zur Null gezogen mit `prior` Schein-Trades)."""
    trades = sorted(trades, key=lambda t: t["bar_ts"])
    end = trades[-1]["bar_ts"] + 1
    out, t0 = [], start_ms
    while t0 < end:
        t1 = t0 + step_ms
        agg: dict = {}
        for t in trades:
            if t["exit_ts"] < t0:
                a = agg.setdefault(tuple(t[k] for k in keys), [0.0, 0])
                a[0] += t["r"]; a[1] += 1
        for t in trades:
            if t0 <= t["bar_ts"] < t1:
                s, n = agg.get(tuple(t[k] for k in keys), (0.0, 0))
                out.append({**t, "take": s / (n + prior) > 0})
        t0 = t1
    return out


def monthly_wins(scored: list[dict], lo: int, hi: int) -> str:
    """In wie vielen Monaten war 'genommen' besser als 'alle'?"""
    months: dict = {}
    for t in scored:
        if lo <= t["bar_ts"] < hi:
            months.setdefault(t["bar_ts"] // (30 * learn.DAY_MS), []).append(t)
    better = sum(np.mean([t["r"] for t in m if t["take"]] or [np.mean([t["r"] for t in m])]) > np.mean([t["r"] for t in m])
                 for m in months.values())
    return f"{better}/{len(months)}"


def summary(ts: list[dict]) -> dict:
    if not ts:
        return {"trades": 0}
    r = np.array([t["r"] for t in ts])
    eq = np.cumsum(r)
    dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
    return {"trades": len(ts), "winrate": float((r > 0).mean()), "avg_r": float(r.mean()),
            "total_r": float(r.sum()), "max_dd_r": dd}


def evaluate(scored: list[dict], lo: int, hi: int) -> dict:
    sel = [t for t in scored if lo <= t["bar_ts"] < hi]
    return {"alle": summary(sel), "genommen": summary([t for t in sel if t["take"]]),
            "aussortiert": summary([t for t in sel if not t["take"]])}


def calibration(scored: list[dict], lo: int, hi: int) -> list[dict]:
    sel = [t for t in scored if lo <= t["bar_ts"] < hi]
    out = []
    for a, b in [(0, .3), (.3, .4), (.4, .5), (.5, .6), (.6, 1.01)]:
        g = [t for t in sel if a <= t["p_win"] < b]
        if g:
            out.append({"p_von": a, "p_bis": min(b, 1), "trades": len(g),
                        "p_mittel": float(np.mean([t["p_win"] for t in g])),
                        "trefferquote": float(np.mean([t["r"] > 0 for t in g])),
                        "avg_r": float(np.mean([t["r"] for t in g]))})
    return out


def main() -> None:
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "history")
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "results/lernen")
    out_dir.mkdir(parents=True, exist_ok=True)
    coins = sorted(f.name.split("_")[0] for f in folder.glob("*_1h.csv.gz"))
    cache = out_dir / "lern-trades.json.gz"
    if cache.exists():
        trades = json.loads(gzip.decompress(cache.read_bytes()))
    else:
        jobs = [(folder, c, tf) for c in coins for tf in ("1h", "4h")]
        with ProcessPoolExecutor() as ex:
            trades = [t for part in ex.map(coin_trades, jobs) for t in part]
        learn.add_recent(trades)
        cache.write_bytes(gzip.compress(json.dumps(trades).encode()))
    print(f"{len(trades)} Trades aus {len(coins)} Coins")

    end = max(t["bar_ts"] for t in trades) + 1
    res = {"trades": len(trades), "coins": coins, "split": SPLIT, "wf_start": WF_START, "end": end, "runs": {}}
    # Einstellungen, die verglichen werden (Auswahl nur nach Entwicklungszeitraum!)
    for l2 in (1.0, 3.0, 30.0):
        for thr in (0.0, 0.1):
            key = f"l2={l2:g} schwelle={thr:g}"
            scored = learn.walk_forward(trades, WF_START, l2=l2, threshold=thr)
            res["runs"][key] = {
                "entwicklung": evaluate(scored, WF_START, SPLIT),
                "pruefjahr": evaluate(scored, SPLIT, end),
                "pruefjahr_fokus": evaluate([t for t in scored if t["symbol"] in FOCUS], SPLIT, end),
            }
            print(key, json.dumps({k: {kk: (vv.get("trades"), round(vv.get("avg_r", 0), 3))
                                       for kk, vv in v.items()} for k, v in res["runs"][key].items()}))
            if l2 == 3.0 and thr == 0.0:
                main_scored = scored
    for name, keys in [("regel_strategie", ("strategy", "tf", "side")),
                       ("regel_strategie_ampel", ("strategy", "tf", "side", "light_with")),
                       ("regel_strategie_coin", ("strategy", "tf", "side", "symbol"))]:
        g = group_filter(trades, WF_START, keys)
        res["runs"][name] = {"entwicklung": evaluate(g, WF_START, SPLIT), "pruefjahr": evaluate(g, SPLIT, end),
                             "pruefjahr_fokus": evaluate([t for t in g if t["symbol"] in FOCUS], SPLIT, end),
                             "monate_besser": monthly_wins(g, SPLIT, end)}
        print(name, res["runs"][name]["monate_besser"], json.dumps({k: {kk: (vv.get("trades"), round(vv.get("avg_r", 0), 3))
                                    for kk, vv in v.items()} for k, v in res["runs"][name].items() if k != "monate_besser"}))
    res["runs"]["l2=3 schwelle=0"]["monate_besser"] = monthly_wins(main_scored, SPLIT, end)
    print("KI monate besser", res["runs"]["l2=3 schwelle=0"]["monate_besser"])
    # Lernen aus eigenen Fehlern im Prüfjahr: Grundmodell bis SPLIT eingefroren vs. monatlich nachgelernt
    # (nur mit Trades der 5 Fokus-Coins, wie später im Papier-Test – nicht mit dem ganzen Markt)
    base_train = [t for t in trades if t["exit_ts"] < SPLIT]
    base = learn.Model(3.0).fit(learn.matrix(base_train), learn.label(base_train))
    fokus = sorted((t for t in trades if t["symbol"] in FOCUS and t["bar_ts"] >= SPLIT), key=lambda t: t["bar_ts"])
    res["nachlernen_pruefjahr"] = {}
    for name, strength in [("eingefroren", None), ("nachlernen_stark_gebremst", 300.0),
                           ("nachlernen", 50.0), ("nachlernen_wenig_gebremst", 10.0)]:
        scored, t0 = [], SPLIT
        while t0 < end:
            t1 = t0 + 30 * learn.DAY_MS
            own = [t for t in fokus if t["exit_ts"] < t0]
            m = base if strength is None or len(own) < 20 else \
                learn.Model(strength).fit(learn.matrix(own), learn.label(own), prior=base)
            test = [t for t in fokus if t0 <= t["bar_ts"] < t1]
            if test:
                ev = learn.expected_r(m.predict(learn.matrix(test)), np.array([t["rr"] for t in test]),
                                      np.array([learn.fee_r(t) for t in test]))
                scored += [{**t, "take": bool(e > 0)} for t, e in zip(test, ev)]
            t0 = t1
        res["nachlernen_pruefjahr"][name] = {**evaluate(scored, SPLIT, end), "monate_besser": monthly_wins(scored, SPLIT, end)}
        print(name, res["nachlernen_pruefjahr"][name]["monate_besser"],
              {k: (v.get("trades"), round(v.get("avg_r", 0), 3)) for k, v in res["nachlernen_pruefjahr"][name].items()
               if k != "monate_besser"})
    res["kalibrierung_pruefjahr"] = calibration(main_scored, SPLIT, end)
    # Je Strategie im Prüfjahr: vorher / nachher
    res["strategien_pruefjahr"] = {}
    for st in learn.STRATS:
        sel = [t for t in main_scored if t["strategy"] == st and t["bar_ts"] >= SPLIT]
        res["strategien_pruefjahr"][st] = {"alle": summary(sel), "genommen": summary([t for t in sel if t["take"]])}
    # Was hat das Modell gelernt? (Training bis SPLIT)
    train = [t for t in trades if t["exit_ts"] < SPLIT]
    m = learn.Model(3.0).fit(learn.matrix(train), learn.label(train))
    res["gewichte"] = sorted(((f, float(w)) for f, w in zip(learn.FEATURES, m.w[1:])), key=lambda x: -abs(x[1]))
    # Grundmodell für den Live-Betrieb: mit allen Trades trainiert
    full = learn.Model(3.0).fit(learn.matrix(trades), learn.label(trades))
    learn.save_model(full, out_dir / "lernmodell.json",
                     {"created_at": int(pd.Timestamp.now(tz="UTC").value // 1_000_000), "coins": coins,
                      "data_from": min(t["bar_ts"] for t in trades), "data_to": end})
    (out_dir / "lern-ergebnis.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res["kalibrierung_pruefjahr"], indent=1))
    print(json.dumps(res["strategien_pruefjahr"], indent=1))
    print(res["gewichte"][:12])


if __name__ == "__main__":
    main()
