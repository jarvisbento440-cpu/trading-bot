"""Echte Trefferquoten je Setup-Score aus der langen Kurs-Historie berechnen.

Alle 8 Strategien laufen über die Historie (Branch "history" bzw. scripts/fetch_history.py,
Coinbase seit 2021, 1h und 4h). Jedes Signal wird wie im Backtest durchgespielt und bekommt den
Setup-Score. Ergebnis: results/trefferquoten/trefferquoten.json (+ .md), das der Bot bei jedem
Signal anzeigt.

Aufruf: python scripts/trefferquoten.py <history-ordner> [ausgabe-ordner]
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from signalbot import hitrates  # noqa: E402
from signalbot.backtest import MAX_BARS, TF_MS, resample, simulate  # noqa: E402
from signalbot.indicators import trend_series  # noqa: E402
from signalbot.strategies import prepare, scan_history  # noqa: E402

SPLIT = pd.Timestamp("2025-10-11", tz="UTC").value // 1_000_000  # wie Trendampel/Lernmodell: letztes Jahr = Prüfjahr


def _read(folder: Path, coin: str, tf: str) -> pd.DataFrame:
    df = pd.read_csv(folder / f"{coin}_{tf}.csv.gz")
    gaps = np.flatnonzero(np.diff(df["ts"].values) > 3 * 86_400_000)  # nur ab der letzten großen Lücke
    return (df.iloc[gaps[-1] + 1:] if len(gaps) else df).reset_index(drop=True)


def coin_trades(args) -> list[dict]:
    folder, coin, tf = args
    h1 = _read(folder, coin, "1h")
    daily = _read(folder, coin, "1d")
    df = h1 if tf == "1h" else resample(h1, TF_MS["4h"])
    d = prepare(df)
    trends = trend_series(daily, TF_MS["1d"], d["ts"])
    busy: dict[str, int] = {}
    out = []
    for s in scan_history(d, trends, min_score=65):
        if s.i <= busy.get(s.strategy, -1):
            continue
        res = simulate(d, s, MAX_BARS[tf])
        if res is None or res["result"] == "open":
            continue
        busy[s.strategy] = res["exit_i"]
        setup = s.score if s.strategy == "score" else hitrates.setup_score(d, s.i, s.side)
        out.append({"strategy": s.strategy, "symbol": coin, "tf": tf, "side": s.side, "bar_ts": s.bar_ts,
                    "setup": int(setup), "result": res["result"], "r": float(res["r"]), "t2": bool(res.get("t2"))})
    print(f"{coin} {tf}: {len(out)} Trades", flush=True)
    return out


def main() -> None:
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "history")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "results/trefferquoten")
    coins = sorted({p.name.split("_")[0] for p in folder.glob("*_1h.csv.gz")})
    jobs = [(folder, c, tf) for c in coins for tf in ("1h", "4h")]
    trades: list[dict] = []
    with ProcessPoolExecutor() as pool:
        for part in pool.map(coin_trades, jobs):
            trades += part
    table = hitrates.build(trades, SPLIT, source=f"Coinbase, {len(coins)} Coins ({', '.join(coins)}), 1h + 4h",
                           created_at=int(time.time() * 1000))
    path = hitrates.save(table, out)
    print(hitrates.report(table))
    print("gespeichert:", path)


if __name__ == "__main__":
    main()
