"""Lädt die Historie der kostenlosen News-/On-Chain-Quellen (ohne Schlüssel) für die Forschung.

Speichert nur Rohdaten; ausgewertet wird in scripts/research_context.py.
Läuft über GitHub Actions (Workflow "News/On-Chain-Historie"), weil viele Quellen lokal gesperrt sein können.
"""
from __future__ import annotations

import gzip
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote_plus

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}
GET = {
    "fng": "https://api.alternative.me/fng/?limit=0&format=json",
    "stables_all": "https://stablecoins.llama.fi/stablecoincharts/all",
    "stables_Ethereum": "https://stablecoins.llama.fi/stablecoincharts/Ethereum",
    "stables_Solana": "https://stablecoins.llama.fi/stablecoincharts/Solana",
    "tvl_Ethereum": "https://api.llama.fi/v2/historicalChainTvl/Ethereum",
    "tvl_Solana": "https://api.llama.fi/v2/historicalChainTvl/Solana",
    "tvl_XRPL": "https://api.llama.fi/v2/historicalChainTvl/XRPL",
    "dex_Solana": "https://api.llama.fi/overview/dexs/solana?excludeTotalDataChartBreakdown=true",
    "dex_Ethereum": "https://api.llama.fi/overview/dexs/ethereum?excludeTotalDataChartBreakdown=true",
    "btc_hashrate": "https://api.blockchain.info/charts/hash-rate?timespan=all&sampled=false&format=json",
    "btc_ntx": "https://api.blockchain.info/charts/n-transactions?timespan=all&sampled=false&format=json",
    "btc_fees": "https://api.blockchain.info/charts/transaction-fees-usd?timespan=all&sampled=false&format=json",
}
HL = "https://api.hyperliquid.xyz/info"
HL_COINS = ["BTC", "ETH", "SOL", "XRP", "ONDO", "DOGE", "ADA", "LINK", "AVAX", "LTC"]
NEWS = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana crypto", "XRP": "XRP", "ONDO": "Ondo Finance"}


def get(url, **kw):
    for i in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=40, **kw)
            if r.status_code == 429:
                time.sleep(10 * (i + 1))
                continue
            return r
        except requests.RequestException as e:
            print("Fehler", url, e)
            time.sleep(3)
    return None


def save(o: Path, name: str, text: str) -> None:
    with gzip.open(o / f"{name}.gz", "wt", encoding="utf-8") as f:
        f.write(text)


def main(out: str, weeks: int = 104) -> None:
    o = Path(out)
    o.mkdir(parents=True, exist_ok=True)
    for key, url in GET.items():
        r = get(url)
        print(key, r.status_code if r is not None else "-", len(r.text) if r is not None else 0)
        if r is not None and r.ok:
            save(o, key + ".json", r.text)

    # Ondo-Protokolle finden (TVL der tokenisierten Anleihen)
    r = get("https://api.llama.fi/protocols")
    if r is not None and r.ok:
        ondo = [p for p in r.json() if "ondo" in (p.get("name", "") + p.get("slug", "")).lower()]
        save(o, "ondo_protocols.json", json.dumps(ondo))
        for p in ondo:
            rp = get(f"https://api.llama.fi/protocol/{p['slug']}")
            if rp is not None and rp.ok:
                save(o, f"protocol_{p['slug']}.json", rp.text)
            print("protocol", p["slug"], rp.status_code if rp is not None else "-")

    # Funding-Historie (Hyperliquid, stündlich, seit Mai 2023)
    for coin in HL_COINS:
        start, rows = 1683000000000, []
        while True:
            try:
                r = requests.post(HL, json={"type": "fundingHistory", "coin": coin, "startTime": start}, timeout=30)
                batch = r.json() if r.ok else []
            except (requests.RequestException, ValueError):
                batch = []
            if not batch:
                break
            rows += batch
            start = batch[-1]["time"] + 1
            if len(batch) < 500:
                break
            time.sleep(0.3)
        print("funding", coin, len(rows))
        save(o, f"funding_{coin}.json", json.dumps(rows))

    # Schlagzeilen der letzten Wochen (Google News, wochenweise je Coin)
    end = date.today()
    for coin, q in NEWS.items():
        items = []
        for w in range(weeks):
            d1 = end - timedelta(days=7 * w)
            d0 = d1 - timedelta(days=7)
            url = ("https://news.google.com/rss/search?q=" + quote_plus(f"{q} after:{d0} before:{d1}")
                   + "&hl=en-US&gl=US&ceid=US:en")
            r = get(url)
            if r is not None and r.ok:
                items.append(r.text)
            time.sleep(1.2)
        print("news", coin, len(items))
        save(o, f"news_{coin}.json", json.dumps(items))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "context-history", int(sys.argv[2]) if len(sys.argv) > 2 else 104)
