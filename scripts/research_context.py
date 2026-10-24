"""Forschung: Helfen News-Stimmung und On-Chain-/Derivate-Daten beim Timing?

Daten: scripts/fetch_context_history.py (Branch "context-history") + Tageskerzen (Branch "history").
Gleiche Regeln wie research.py: Wert zum Tagesschluss bekannt, Position gilt ab dem nächsten Tag,
0,1 % Gebühr pro Seite, Entwicklung bis 10.10.2025, Prüfjahr 11.10.2025 – 10.10.2026.

Aufruf: python scripts/research_context.py <history-Ordner> <ctxhist-Ordner> [ausgabe.json]
"""
from __future__ import annotations

import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import research as R  # noqa: E402
from signalbot import news  # noqa: E402

FOCUS = R.FOCUS
HL_BASE = 0.0000125  # Standard-Funding bei Hyperliquid pro Stunde (≈ 11 % p. a.)


def _load(folder: Path, name: str):
    p = folder / f"{name}.gz"
    if not p.exists():
        return None
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.loads(f.read())


def _daily(pairs, name) -> pd.Series:
    s = pd.Series({pd.Timestamp(int(t), unit="s", tz="UTC").floor("D"): float(v) for t, v in pairs}, name=name)
    return s[~s.index.duplicated(keep="last")].sort_index()


def load_context(folder: Path) -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    fng = _load(folder, "fng.json")
    if fng:
        out["fng"] = _daily([(x["timestamp"], x["value"]) for x in fng["data"]], "fng")
    for key in ("stables_all", "stables_Ethereum", "stables_Solana"):
        rows = _load(folder, key + ".json")
        if rows:
            out[key] = _daily([(r["date"], (r.get("totalCirculatingUSD") or {}).get("peggedUSD") or np.nan)
                               for r in rows], key)
    for key in ("tvl_Ethereum", "tvl_Solana", "tvl_XRPL"):
        rows = _load(folder, key + ".json")
        if rows:
            out[key] = _daily([(r["date"], r["tvl"]) for r in rows], key)
    for key in ("dex_Solana", "dex_Ethereum"):
        d = _load(folder, key + ".json")
        if d:
            out[key] = _daily(d.get("totalDataChart", []), key)
    for key in ("btc_hashrate", "btc_ntx", "btc_fees"):
        d = _load(folder, key + ".json")
        if d:
            out[key] = _daily([(v["x"], v["y"]) for v in d["values"]], key)
    for c in ["BTC", "ETH", "SOL", "XRP", "ONDO", "DOGE", "ADA", "LINK", "AVAX", "LTC"]:
        rows = _load(folder, f"funding_{c}.json")
        if rows:
            s = pd.Series({pd.Timestamp(r["time"], unit="ms", tz="UTC"): float(r["fundingRate"]) for r in rows})
            out[f"funding_{c}"] = s.groupby(s.index.floor("D")).mean()
    ondo = 0
    for p in folder.glob("protocol_ondo-*.json.gz"):
        d = _load(folder, p.name[:-3])
        tvl = d.get("tvl") or []
        if tvl:
            s = _daily([(x["date"], x["totalLiquidityUSD"]) for x in tvl], p.name)
            ondo = s if isinstance(ondo, int) else ondo.add(s, fill_value=0)
    if not isinstance(ondo, int):
        out["tvl_ONDO"] = ondo
    for c in news.GOOGLE_QUERY:
        pages = _load(folder, f"news_{c}.json")
        if not pages:
            continue
        seen, rows = set(), []
        for xml in pages:
            for it in news.parse_feed(xml, "Google News"):
                k = it["title"].lower()[:80]
                if k in seen:
                    continue
                seen.add(k)
                rows.append((it["ts"], news.score_title(it["title"])))
        if rows:
            df = pd.DataFrame(rows, columns=["ts", "score"])
            df["day"] = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.floor("D")
            g = df.groupby("day")["score"]
            out[f"news_{c}"] = g.mean()
            out[f"newsn_{c}"] = g.count()
    return out


# ---------- Merkmale je Coin (Tageswert, am Tagesschluss bekannt) ----------

def features(coin: str, df: pd.DataFrame, ctx: dict[str, pd.Series]) -> pd.DataFrame:
    idx = df.index
    f = pd.DataFrame(index=idx)

    def al(s):  # an Kerzen-Index anpassen, nur Vergangenheit nachtragen
        return s.reindex(idx.union(s.index)).ffill().reindex(idx) if s is not None else pd.Series(np.nan, index=idx)

    if "fng" in ctx:
        fng = al(ctx["fng"])
        f["fng"] = fng
        f["fng7"] = fng.rolling(7).mean()
    if "stables_all" in ctx:
        st = ctx["stables_all"]
        f["stable30"] = al(st / st.shift(30) - 1)
        f["stable7"] = al(st / st.shift(7) - 1)
    chain = {"ETH": "Ethereum", "SOL": "Solana", "XRP": "XRPL", "ONDO": "ONDO"}.get(coin)
    if chain and f"tvl_{chain}" in ctx:
        t = ctx[f"tvl_{chain}"]
        f["tvl30"] = al(t / t.shift(30) - 1)
        # TVL in USD steigt schon mit dem Kurs: Kursanteil herausrechnen
        f["tvl30_rel"] = f["tvl30"] - (df["close"] / df["close"].shift(30) - 1)
    if chain and f"stables_{chain}" in ctx:
        s = ctx[f"stables_{chain}"]
        f["cstable30"] = al(s / s.shift(30) - 1)
    if chain and f"dex_{chain}" in ctx:
        d = ctx[f"dex_{chain}"].rolling(7).sum()
        f["dex7"] = al(d / d.shift(7) - 1)
    if f"funding_{coin}" in ctx:
        fu = ctx[f"funding_{coin}"]
        f["funding7"] = al(fu.rolling(7).mean())
    if coin == "BTC" and "btc_hashrate" in ctx:
        h = ctx["btc_hashrate"]
        f["hash_ribbon"] = al(h.rolling(30).mean() / h.rolling(60).mean() - 1)
    if coin == "BTC" and "btc_ntx" in ctx:
        n = ctx["btc_ntx"]
        f["ntx"] = al(n.rolling(7).mean() / n.rolling(30).mean() - 1)
    if f"news_{coin}" in ctx:
        s, n = ctx[f"news_{coin}"], ctx[f"newsn_{coin}"]
        # Tageswert nur, wenn die Schlagzeile vor Tagesschluss erschien (Gruppierung nach Veröffentlichungstag)
        s = s.reindex(idx)
        n = n.reindex(idx).fillna(0)
        f["news1"] = s
        w = (s.fillna(0) * n).rolling(3).sum() / n.rolling(3).sum().replace(0, np.nan)
        f["news3"] = w
        f["news_n"] = n
    f["ret_fwd7"] = df["close"].shift(-7) / df["close"] - 1
    return f


# ---------- Regeln ----------

def trend(df):
    return R.vol_target(R.sma_filter(df, 50), df, 0.5, 30)


def rules(coin: str, df: pd.DataFrame, f: pd.DataFrame) -> dict[str, pd.Series]:
    T = trend(df)
    one = pd.Series(1.0, index=df.index)
    g = lambda col: f[col] if col in f else pd.Series(np.nan, index=df.index)  # noqa: E731
    out = {"Kaufen & Halten": one, "Trendampel": T}
    # Fear & Greed
    out["F&G: nur bei Angst (<30) kaufen"] = (g("fng7") < 30).astype(float)
    out["Trendampel, raus bei Gier (>75)"] = T * (g("fng7") <= 75)
    out["Trendampel ODER Angst (<25)"] = np.maximum(T, (g("fng7") < 25).astype(float))
    # Stablecoins
    out["Stablecoins 30 T steigend"] = (g("stable30") > 0).astype(float)
    out["Trendampel + Stablecoins steigend"] = T * (g("stable30") > 0)
    # Chain-TVL (nur ETH/SOL/XRP/ONDO)
    if "tvl30_rel" in f:
        out["TVL wächst schneller als Kurs"] = (g("tvl30_rel") > 0).astype(float)
        out["Trendampel + TVL > Kurs"] = T * (g("tvl30_rel") > 0)
    # Funding
    if "funding7" in f and f["funding7"].notna().any():
        out["Trendampel, raus bei hohem Funding (>2×)"] = T * ~(g("funding7") > 2 * HL_BASE)
        out["Kaufen bei negativem Funding"] = (g("funding7") < 0).astype(float)
        out["Trendampel ODER negatives Funding"] = np.maximum(T, (g("funding7") < 0).astype(float))
    if "hash_ribbon" in f:
        out["Hash-Ribbon (30 T > 60 T)"] = (g("hash_ribbon") > 0).astype(float)
        out["Trendampel + Hash-Ribbon"] = T * (g("hash_ribbon") > 0)
    if "news3" in f:
        out["News 3 T positiv (> +0,2)"] = (g("news3") > 0.2).astype(float)
        out["Trendampel, raus bei negativen News (< −0,2)"] = T * ~(g("news3") < -0.2)
        out["Trendampel + News nicht negativ (≥ 0)"] = T * (g("news3").fillna(0) >= 0)
    return {k: pd.Series(v, index=df.index).fillna(0).astype(float) for k, v in out.items()}


def window_metrics(r: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    return R.metrics(r[(r.index >= start) & (r.index < end)])


def ic(f: pd.DataFrame, col: str, start, end) -> tuple[float | None, int]:
    """Rang-Korrelation zwischen Merkmal und Rendite der nächsten 7 Tage."""
    x = f[(f.index >= start) & (f.index < end)][[col, "ret_fwd7"]].dropna()
    if len(x) < 60:
        return None, len(x)
    return float(x[col].rank().corr(x["ret_fwd7"].rank())), len(x)


def main(hist: str, ctxdir: str, out: str | None = None) -> dict:
    daily = R.load_daily(Path(hist))
    ctx = load_context(Path(ctxdir))
    periods = {
        "Entwicklung 2021–25": (pd.Timestamp("2021-01-01", tz="UTC"), R.SPLIT),
        "Entwicklung 2024/25": (pd.Timestamp("2024-10-11", tz="UTC"), R.SPLIT),
        "Prüfjahr 2025/26": (R.SPLIT, R.END),
    }
    feats = {c: features(c, daily[c], ctx) for c in daily}
    # Merkmal-Vorhersagekraft (IC), gepoolt über Fokus-Coins
    ic_rows = defaultdict(dict)
    cols = sorted({c for f in feats.values() for c in f.columns if c not in ("ret_fwd7", "news_n")})
    for col in cols:
        for pname, (a, b) in periods.items():
            vals, ns = [], 0
            for c in FOCUS:
                if c in feats and col in feats[c]:
                    v, n = ic(feats[c], col, a, b)
                    if v is not None:
                        vals.append(v)
                        ns += n
            ic_rows[col][pname] = {"ic": float(np.mean(vals)) if vals else None, "n": ns, "coins": len(vals)}

    # Regeln als Portfolio über die Fokus-Coins (gleich gewichtet)
    per_coin = {c: rules(c, daily[c], feats[c]) for c in FOCUS if c in daily}
    names = list(dict.fromkeys(k for r in per_coin.values() for k in r))
    results = {}
    for name in names:
        rets = {}
        for c, rs in per_coin.items():
            if name in rs:
                rets[c] = R.coin_returns(daily[c], rs[name])
        m = pd.DataFrame(rets)
        started = pd.DataFrame({c: daily[c]["close"].rolling(200).count() >= 200 for c in rets}).reindex(m.index).fillna(False)
        port = m.where(started).mean(axis=1).fillna(0)
        results[name] = {"coins": sorted(rets), **{p: window_metrics(port, a, b) for p, (a, b) in periods.items()}}

    res = {"ic": ic_rows, "rules": results,
           "coverage": {k: [str(v.index.min().date()), str(v.index.max().date()), int(v.notna().sum())] for k, v in ctx.items()}}
    if out:
        Path(out).write_text(json.dumps(res, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    return res


def report(res: dict) -> str:
    lines = ["Vorhersagekraft (Rang-Korrelation mit Rendite der nächsten 7 Tage, Mittel über Fokus-Coins):"]
    for col, ps in res["ic"].items():
        lines.append(f"  {col:12s} " + "  ".join(
            f"{p}: {v['ic']:+.3f} (n={v['n']})" if v["ic"] is not None else f"{p}: –" for p, v in ps.items()))
    lines.append("\nRegeln (Fokus-Coins, gleich gewichtet, 0,1 % Gebühr):")
    for name, r in res["rules"].items():
        cells = []
        for p in ("Entwicklung 2021–25", "Entwicklung 2024/25", "Prüfjahr 2025/26"):
            m = r.get(p) or {}
            cells.append(f"{p}: {m['total']*100:+6.1f}% Sh {m['sharpe']:+.2f} DD {m['maxdd']*100:5.1f}%" if m else f"{p}: –")
        lines.append(f"  {name:45s} " + " | ".join(cells))
    return "\n".join(lines)


if __name__ == "__main__":
    r = main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    print(report(r))
    print(json.dumps(r["coverage"], indent=1))
