"""Prüft, welche kostenlosen News-/On-Chain-Quellen ohne Schlüssel erreichbar sind, und speichert die Rohdaten."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}
GET = {
    "rss_coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "rss_cointelegraph": "https://cointelegraph.com/rss",
    "rss_decrypt": "https://decrypt.co/feed",
    "rss_theblock": "https://www.theblock.co/rss.xml",
    "rss_bitcoinmagazine": "https://bitcoinmagazine.com/.rss/full/",
    "rss_cryptoslate": "https://cryptoslate.com/feed/",
    "rss_cryptonews": "https://crypto.news/feed/",
    "rss_utoday": "https://u.today/rss",
    "rss_google_ondo": "https://news.google.com/rss/search?q=Ondo+Finance&hl=en-US&gl=US&ceid=US:en",
    "rss_google_xrp": "https://news.google.com/rss/search?q=XRP+when:2d&hl=en-US&gl=US&ceid=US:en",
    "fng": "https://api.alternative.me/fng/?limit=0&format=json",
    "llama_stables": "https://stablecoins.llama.fi/stablecoincharts/all",
    "llama_chains": "https://api.llama.fi/v2/chains",
    "llama_tvl_eth": "https://api.llama.fi/v2/historicalChainTvl/Ethereum",
    "llama_tvl_sol": "https://api.llama.fi/v2/historicalChainTvl/Solana",
    "llama_tvl_xrpl": "https://api.llama.fi/v2/historicalChainTvl/XRPL",
    "llama_ondo": "https://api.llama.fi/tvl/ondo-finance",
    "llama_ondo_full": "https://api.llama.fi/protocol/ondo-finance",
    "llama_dex_sol": "https://api.llama.fi/overview/dexs/solana?excludeTotalDataChartBreakdown=true",
    "llama_stables_sol": "https://stablecoins.llama.fi/stablecoincharts/Solana",
    "mempool_fees": "https://mempool.space/api/v1/fees/recommended",
    "mempool": "https://mempool.space/api/mempool",
    "mempool_hashrate": "https://mempool.space/api/v1/mining/hashrate/1y",
    "bc_ntx": "https://api.blockchain.info/charts/n-transactions?timespan=1year&format=json",
    "bc_vol": "https://api.blockchain.info/charts/estimated-transaction-volume-usd?timespan=1year&format=json",
    "blockchair_btc": "https://api.blockchair.com/bitcoin/stats",
    "blockchair_eth": "https://api.blockchair.com/ethereum/stats",
    "blockchair_btc_whales": "https://api.blockchair.com/bitcoin/transactions?q=output_total_usd(10000000..)&s=time(desc)&limit=10",
    "okx_funding": "https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP",
    "okx_oi": "https://www.okx.com/api/v5/public/open-interest?instType=SWAP&instId=BTC-USDT-SWAP",
    "binance_funding": "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT",
    "bybit_tickers": "https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT",
    "kraken_fut": "https://futures.kraken.com/derivatives/api/v3/tickers",
    "coingecko_global": "https://api.coingecko.com/api/v3/global",
}
POST = {
    "hyperliquid": ("https://api.hyperliquid.xyz/info", {"type": "metaAndAssetCtxs"}),
    "hyperliquid_fhist": ("https://api.hyperliquid.xyz/info", {"type": "fundingHistory", "coin": "BTC", "startTime": 1700000000000}),
    "solana_perf": ("https://api.mainnet-beta.solana.com", {"jsonrpc": "2.0", "id": 1, "method": "getRecentPerformanceSamples", "params": [10]}),
    "xrpl_info": ("https://xrplcluster.com/", {"method": "server_info", "params": [{}]}),
    "xrpl_ripple": ("https://s1.ripple.com:51234/", {"method": "server_info", "params": [{}]}),
    "eth_rpc": ("https://ethereum-rpc.publicnode.com", {"jsonrpc": "2.0", "id": 1, "method": "eth_gasPrice", "params": []}),
}


def main(out: str) -> None:
    o = Path(out)
    o.mkdir(parents=True, exist_ok=True)
    summary = {}
    jobs = [(k, "GET", u, None) for k, u in GET.items()] + [(k, "POST", u, b) for k, (u, b) in POST.items()]
    for key, method, url, body in jobs:
        try:
            r = requests.request(method, url, json=body, headers=UA, timeout=25)
            text = r.text
            summary[key] = {"status": r.status_code, "bytes": len(text), "type": r.headers.get("Content-Type", "")}
            # große Antworten kürzen, aber genug für Struktur und Historie behalten
            (o / f"{key}.txt").write_text(text if len(text) < 3_000_000 else text[:3_000_000], encoding="utf-8")
        except Exception as e:
            summary[key] = {"error": str(e)[:300]}
        print(key, summary[key])
    (o / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "context-check")
