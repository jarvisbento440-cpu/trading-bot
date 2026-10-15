"""Lädt lange Kurs-Historie (1h und 1d) und speichert sie als CSV.gz für Forschung/Backtests.

Aufruf: python scripts/fetch_history.py --exchange coinbaseexchange --quote USD --since 2021-01-01 --out history
"""
import argparse
import gzip
import time
from pathlib import Path

import ccxt

COINS = ["BTC", "ETH", "SOL", "XRP", "ONDO", "ADA", "AVAX", "LINK", "DOGE", "LTC"]


def fetch(ex, symbol, tf, since_ms):
    tf_ms = ex.parse_timeframe(tf) * 1000
    limit = 300 if ex.id.startswith("coinbase") else 1000
    rows, since = [], since_ms
    while since < ex.milliseconds():
        try:
            part = ex.fetch_ohlcv(symbol, tf, since=since, limit=limit)
        except ccxt.BaseError as e:
            print("Fehler", symbol, tf, e)
            time.sleep(3)
            continue
        if not part:
            since += limit * tf_ms  # Lücke (z. B. vor Listing) überspringen
            continue
        rows += part
        since = part[-1][0] + tf_ms
    seen, out = set(), []
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0])
            out.append(r)
    return sorted(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--exchange", default="coinbaseexchange")
    p.add_argument("--quote", default="USD")
    p.add_argument("--since", default="2021-01-01")
    p.add_argument("--out", default="history")
    a = p.parse_args()
    ex = getattr(ccxt, a.exchange)({"enableRateLimit": True})
    ex.load_markets()
    since = ex.parse8601(a.since + "T00:00:00Z")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for coin in COINS:
        sym = f"{coin}/{a.quote}"
        if sym not in ex.markets:
            print("fehlt:", sym)
            continue
        for tf in ("1h", "1d"):
            rows = fetch(ex, sym, tf, since)
            with gzip.open(out / f"{coin}_{tf}.csv.gz", "wt") as f:
                f.write("ts,open,high,low,close,volume\n")
                for r in rows:
                    f.write(",".join(str(x) for x in r[:6]) + "\n")
            print(sym, tf, len(rows))


if __name__ == "__main__":
    main()
