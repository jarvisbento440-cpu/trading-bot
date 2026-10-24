"""On-Chain- und Derivate-Daten aus kostenlosen Quellen ohne API-Schlüssel.

- DefiLlama: Stablecoin-Menge (gesamt und je Chain), TVL je Chain, DEX-Umsatz, Ondo-TVL
- mempool.space / Blockchair: Bitcoin-Gebühren, Mempool, Hashrate, größte Transaktion
- Hyperliquid: Funding-Rate und Open Interest je Coin (größte Börse ohne Anmeldung, auch aus Österreich/USA erreichbar)
- Solana-RPC: Transaktionen pro Sekunde

Exchange-Zu-/Abflüsse und echte Wal-Wallets gibt es nur gegen Bezahlung (CryptoQuant, Glassnode, Whale Alert)
und fehlen deshalb. Welche Werte als Signal taugen, steht in docs/news-onchain.md.
"""
from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}
DAY_MS = 86_400_000
HL = "https://api.hyperliquid.xyz/info"
LLAMA = "https://api.llama.fi"
STABLES = "https://stablecoins.llama.fi"
CHAIN = {"ETH": "Ethereum", "SOL": "Solana", "XRP": "XRPL"}
ONDO_SLUGS = ["ondo-yield-assets", "ondo-global-markets"]
HOT_FUNDING = 2 * 0.0000125  # doppelter Standard-Funding von Hyperliquid pro Stunde (≈ 22 % p. a.)

# Gewicht je Merkmal als Signal: 1 = im Test (Entwicklung UND Prüfjahr) hilfreich, 0 = nur Info.
# Ergebnis von scripts/research_context.py, siehe docs/news-onchain.md.
TESTED = {"funding_hot": 0, "funding_negative": 0, "stables_up": 0, "tvl_up": 0, "hash_ribbon": 0}


def _get(url: str, **kw):
    r = requests.get(url, headers=UA, timeout=kw.pop("timeout", 20), **kw)
    r.raise_for_status()
    return r.json()


def _post(url: str, body: dict):
    r = requests.post(url, json=body, headers=UA, timeout=20)
    r.raise_for_status()
    return r.json()


def _change(series: list[tuple[int, float]], days: int) -> float | None:
    """Veränderung des letzten Werts gegenüber dem Wert vor `days` Tagen (als Anteil)."""
    if len(series) < 2:
        return None
    t_last, v_last = series[-1]
    target = t_last - days * DAY_MS
    past = [v for t, v in series if t <= target]
    if not past or not past[-1]:
        return None
    return v_last / past[-1] - 1


def _series_llama_tvl(rows) -> list[tuple[int, float]]:
    return [(int(r["date"]) * 1000, float(r["tvl"])) for r in rows if r.get("tvl") is not None]


def _series_stables(rows) -> list[tuple[int, float]]:
    out = []
    for r in rows:
        v = (r.get("totalCirculatingUSD") or {}).get("peggedUSD")
        if v:
            out.append((int(r["date"]) * 1000, float(v)))
    return out


def stablecoins(chain: str | None = None) -> dict:
    rows = _get(f"{STABLES}/stablecoincharts/{chain or 'all'}")
    s = _series_stables(rows)
    return {"value": s[-1][1], "chg7": _change(s, 7), "chg30": _change(s, 30), "ts": s[-1][0]}


def chain_tvl(chain: str) -> dict:
    s = _series_llama_tvl(_get(f"{LLAMA}/v2/historicalChainTvl/{chain}"))
    return {"value": s[-1][1], "chg7": _change(s, 7), "chg30": _change(s, 30), "ts": s[-1][0]}


def dex_volume(chain: str) -> dict:
    d = _get(f"{LLAMA}/overview/dexs/{chain.lower()}?excludeTotalDataChartBreakdown=true")
    s = [(int(t) * 1000, float(v)) for t, v in d.get("totalDataChart", [])]
    last7 = sum(v for _, v in s[-7:])
    prev7 = sum(v for _, v in s[-14:-7])
    return {"value": last7, "chg7": (last7 / prev7 - 1) if prev7 else None}


def ondo_tvl() -> dict:
    total, past7, past30 = 0.0, 0.0, 0.0
    for slug in ONDO_SLUGS:
        try:
            d = _get(f"{LLAMA}/protocol/{slug}", timeout=30)
        except requests.RequestException:
            continue
        s = _series_llama_tvl([{"date": x["date"], "tvl": x.get("totalLiquidityUSD")} for x in d.get("tvl", [])])
        if not s:
            continue
        total += s[-1][1]
        c7, c30 = _change(s, 7), _change(s, 30)
        past7 += s[-1][1] / (1 + c7) if c7 is not None else s[-1][1]
        past30 += s[-1][1] / (1 + c30) if c30 is not None else s[-1][1]
    if not total:
        raise ValueError("keine Ondo-TVL")
    return {"value": total, "chg7": total / past7 - 1 if past7 else None, "chg30": total / past30 - 1 if past30 else None}


def hyperliquid() -> dict[str, dict]:
    """Aktuelle Funding-Rate (pro Stunde) und Open Interest je Coin."""
    meta, ctx = _post(HL, {"type": "metaAndAssetCtxs"})
    out = {}
    for u, c in zip(meta["universe"], ctx):
        try:
            mark = float(c["markPx"])
            out[u["name"]] = {"funding": float(c["funding"]), "oi": float(c["openInterest"]),
                              "oi_usd": float(c["openInterest"]) * mark, "mark": mark,
                              "volume_usd": float(c.get("dayNtlVlm") or 0)}
        except (KeyError, TypeError, ValueError):
            continue
    return out


def funding_avg(coin: str, days: int = 7) -> float | None:
    """Durchschnittliche Funding-Rate pro Stunde der letzten `days` Tage."""
    start = int(time.time() * 1000) - days * DAY_MS
    rows = _post(HL, {"type": "fundingHistory", "coin": coin, "startTime": start})
    vals = [float(r["fundingRate"]) for r in rows]
    return sum(vals) / len(vals) if vals else None


def bitcoin() -> dict:
    out = {}
    fees = _get("https://mempool.space/api/v1/fees/recommended")
    out["fee_fast"] = fees.get("fastestFee")
    out["fee_hour"] = fees.get("hourFee")
    mp = _get("https://mempool.space/api/mempool")
    out["mempool_tx"] = mp.get("count")
    hr = _get("https://mempool.space/api/v1/mining/hashrate/3m").get("hashrates", [])
    vals = [h["avgHashrate"] for h in hr]
    if len(vals) >= 60:
        out["hash_ribbon"] = (sum(vals[-30:]) / 30) / (sum(vals[-60:]) / 60) - 1  # 30-Tage- vs. 60-Tage-Schnitt
        out["hashrate"] = vals[-1]
    try:
        st = _get("https://api.blockchair.com/bitcoin/stats")["data"]
        out["tx_24h"] = st.get("transactions_24h")
        out["largest_tx_usd"] = (st.get("largest_transaction_24h") or {}).get("value_usd")
    except (requests.RequestException, KeyError, ValueError):
        pass
    return out


def solana_tps() -> float | None:
    d = _post("https://api.mainnet-beta.solana.com",
              {"jsonrpc": "2.0", "id": 1, "method": "getRecentPerformanceSamples", "params": [10]})
    rows = d.get("result") or []
    tx = sum(r.get("numNonVoteTransactions", r["numTransactions"]) for r in rows)
    secs = sum(r["samplePeriodSecs"] for r in rows)
    return tx / secs if secs else None


def _try(failed: list[str], name: str, fn, *args):
    try:
        return fn(*args)
    except Exception as e:  # jede Quelle darf einzeln ausfallen
        log.info("On-Chain-Quelle %s nicht erreichbar: %s", name, e)
        failed.append(name)
        return None


def snapshot(coins: list[str], prev_oi: list | None = None) -> dict:
    """Holt alle Werte. Fällt eine Quelle aus, fehlt nur dieser Wert."""
    failed: list[str] = []
    now = int(time.time() * 1000)
    snap = {"ts": now, "market": {}, "coins": {c: {} for c in coins}, "failed": failed}
    snap["market"]["stables"] = _try(failed, "DefiLlama Stablecoins", stablecoins)
    hl = _try(failed, "Hyperliquid", hyperliquid) or {}
    for c in coins:
        m = snap["coins"][c]
        if c in hl:
            m["funding"] = hl[c]["funding"]
            m["oi_usd"] = hl[c]["oi_usd"]
            m["funding7"] = _try(failed, f"Funding {c}", funding_avg, c)
        if c in CHAIN:
            m["tvl"] = _try(failed, f"TVL {CHAIN[c]}", chain_tvl, CHAIN[c])
            if c != "XRP":
                m["stables"] = _try(failed, f"Stablecoins {CHAIN[c]}", stablecoins, CHAIN[c])
        if c == "SOL":
            m["dex"] = _try(failed, "DEX Solana", dex_volume, "Solana")
            m["tps"] = _try(failed, "Solana-RPC", solana_tps)
        if c == "ETH":
            m["dex"] = _try(failed, "DEX Ethereum", dex_volume, "Ethereum")
        if c == "BTC":
            m.update(_try(failed, "mempool.space", bitcoin) or {})
        if c == "ONDO":
            m["tvl"] = _try(failed, "Ondo-TVL", ondo_tvl)
    # Open Interest vor ~24 h aus den eigenen Schnappschüssen
    hist = [h for h in (prev_oi or []) if now - h["ts"] <= 3 * DAY_MS]
    hist.append({"ts": now, "oi": {c: snap["coins"][c].get("oi_usd") for c in coins}})
    snap["oi_hist"] = hist[-200:]
    for c in coins:
        old = [h["oi"].get(c) for h in hist if now - h["ts"] >= 20 * 3_600_000 and h["oi"].get(c)]
        cur = snap["coins"][c].get("oi_usd")
        if old and cur:
            snap["coins"][c]["oi_chg24"] = cur / old[-1] - 1
    return snap


def sync(db, coins: list[str]) -> dict:
    prev = db.get_context("onchain") or {}
    snap = snapshot(coins, prev.get("oi_hist"))
    db.set_context("onchain", snap)
    return snap


# ---------- Anzeige und Bewertung ----------

def _pct(x: float | None, digits: int = 1) -> str:
    if x is None:
        return "–"
    return f"{x * 100:+.{digits}f} %".replace(".", ",")


def _usd(x: float | None) -> str:
    if x is None:
        return "–"
    for div, unit in ((1e12, "Bio."), (1e9, "Mrd."), (1e6, "Mio.")):
        if abs(x) >= div:
            return f"{x / div:,.1f} {unit} $".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{x:,.0f} $".replace(",", ".")


def funding_text(rate_h: float | None) -> str:
    if rate_h is None:
        return "–"
    return f"{rate_h * 100:.4f} %/h ({rate_h * 24 * 365 * 100:+.0f} % p. a.)".replace(".", ",")


def view(snap: dict | None, symbol: str) -> dict:
    """Zeilen für Oberfläche/Telegram: [{name, value, signal (+1/0/−1), note}] und eine Gesamt-Einschätzung.

    signal: +1 spricht eher für Long, −1 eher dagegen, 0 = nur Info.
    Welche Werte überhaupt ein Signal geben dürfen, steht in TESTED (Ergebnis von scripts/research_context.py).
    """
    coin = symbol.split("/")[0].upper()
    if not snap:
        return {"coin": coin, "rows": [], "score": 0, "label": "keine Daten", "ts": None}
    m = snap.get("coins", {}).get(coin, {})
    mk = snap.get("market", {})
    rows = []

    f7 = m.get("funding7")
    if f7 is not None or m.get("funding") is not None:
        sig, note = 0, "normal"
        if f7 is not None and f7 > HOT_FUNDING:
            sig, note = TESTED["funding_hot"], "überhitzt: viele gehebelte Longs"
        elif f7 is not None and f7 < 0:
            sig, note = TESTED["funding_negative"], "negativ: Shorts zahlen, Markt pessimistisch"
        rows.append({"name": "Funding (Ø 7 Tage)", "value": funding_text(f7 if f7 is not None else m.get("funding")),
                     "signal": sig, "note": note})
    if m.get("oi_usd"):
        rows.append({"name": "Open Interest", "value": _usd(m["oi_usd"]) +
                     (f" ({_pct(m['oi_chg24'])} in 24 h)" if m.get("oi_chg24") is not None else ""),
                     "signal": 0, "note": "offene gehebelte Positionen (Hyperliquid)"})
    st = mk.get("stables")
    if st:
        sig = TESTED["stables_up"] if (st.get("chg30") or 0) > 0 else -TESTED["stables_up"]
        rows.append({"name": "Stablecoins (alle Chains)", "value": f"{_usd(st['value'])} · 30 T {_pct(st.get('chg30'))}",
                     "signal": sig, "note": "wächst = frisches Geld wartet im Markt" if sig >= 0 else "schrumpft = Geld fließt ab"})
    tvl = m.get("tvl")
    if tvl:
        rows.append({"name": "TVL Ondo-Produkte" if coin == "ONDO" else f"TVL {CHAIN.get(coin, coin)}",
                     "value": f"{_usd(tvl['value'])} · 30 T {_pct(tvl.get('chg30'))}",
                     "signal": TESTED["tvl_up"] * (1 if (tvl.get("chg30") or 0) > 0 else -1),
                     "note": "in DeFi gebundenes Kapital"})
    cs = m.get("stables")
    if cs:
        rows.append({"name": f"Stablecoins auf {CHAIN.get(coin, coin)}", "value": f"{_usd(cs['value'])} · 30 T {_pct(cs.get('chg30'))}",
                     "signal": 0, "note": "Liquidität auf dieser Chain"})
    dex = m.get("dex")
    if dex:
        rows.append({"name": "DEX-Umsatz 7 Tage", "value": f"{_usd(dex['value'])} ({_pct(dex.get('chg7'))} zur Vorwoche)",
                     "signal": 0, "note": "Handel auf dezentralen Börsen"})
    if m.get("tps"):
        rows.append({"name": "Transaktionen/s", "value": f"{m['tps']:,.0f}".replace(",", "."), "signal": 0, "note": "ohne Validator-Votes"})
    if m.get("hash_ribbon") is not None:
        sig = TESTED["hash_ribbon"] * (1 if m["hash_ribbon"] > 0 else -1)
        rows.append({"name": "Hashrate 30 T vs. 60 T", "value": _pct(m["hash_ribbon"]), "signal": sig,
                     "note": "Miner bauen aus" if m["hash_ribbon"] > 0 else "Miner schalten ab (Hash-Ribbon)"})
    if m.get("fee_fast") is not None:
        rows.append({"name": "Gebühr (schnell)", "value": f"{m['fee_fast']} sat/vB · {m.get('mempool_tx') or 0:,} wartend".replace(",", "."),
                     "signal": 0, "note": "hohe Gebühren = viel Andrang"})
    if m.get("largest_tx_usd"):
        rows.append({"name": "Größte Transaktion 24 h", "value": _usd(m["largest_tx_usd"]), "signal": 0,
                     "note": "Wal-Bewegung (Richtung unbekannt)"})
    score = sum(r["signal"] for r in rows)
    lab = "Rückenwind" if score >= 2 else "leicht positiv" if score == 1 else "Gegenwind" if score <= -2 else \
        "leicht negativ" if score == -1 else "neutral"
    return {"coin": coin, "rows": rows, "score": score, "label": lab, "ts": snap.get("ts"),
            "failed": snap.get("failed", [])}
