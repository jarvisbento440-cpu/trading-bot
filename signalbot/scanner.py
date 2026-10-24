"""Coin-Scanner: sucht unter den meistgehandelten Coins der Börse die auffälligen.

Ablauf (alle paar Stunden):
1. Alle Spot-Paare in der Quote-Währung (z. B. USDT) holen, Stablecoins, Wrapped- und
   Hebel-Token aussortieren, die `top` Coins mit dem höchsten 24h-Volumen nehmen.
2. Für jeden Coin die Tageskerzen laden und dieselbe Trendampel wie bei den Haupt-Coins
   rechnen (Schluss über dem 50-Tage-Schnitt = grün).
3. Nur Coins mit grüner Ampel bekommen einen Scanner-Score (0–100): "Rücksetzer im Aufwärtstrend",
   je zur Hälfte nah am 50-Tage-Schnitt und nicht schon stärker als BTC gelaufen (30 Tage).
   Der erste Entwurf (Stärke gegenüber BTC + Volumen-Schub) hat im historischen Test die
   schlechtesten Coins ausgewählt: wer schon davongelaufen war, fiel danach im Schnitt zurück.
Der Score ist eine Rangliste für die Beobachtung, keine Trefferwahrscheinlichkeit, und schlug im
Test BTC mit Trendampel nicht. Details: scripts/scanner_test.py, docs/scanner.md.
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config
from .regime import DAY_MS, SMA, VOL_LOOK, VOL_TARGET, closed_daily

log = logging.getLogger(__name__)

STABLE = {
    "USDT", "USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "PYUSD", "USDE", "USDS", "USD1", "RLUSD", "BFUSD",
    "XUSD", "AEUR", "EURI", "EUR", "GBP", "TRY", "BRL", "USDD", "GUSD", "FRAX", "LUSD", "SUSD", "UST", "USTC",
    "EURC", "EURT", "USDJ", "PAX", "USD", "USDG", "USDQ", "USDR", "ZUSD", "CUSD",
}
PEGGED = {"WBTC", "WETH", "WBETH", "STETH", "WSTETH", "BETH", "CBETH", "RETH", "BNSOL", "JITOSOL", "MSOL",
          "PAXG", "XAUT", "WBNB", "TBTC", "LBTC", "CBBTC"}
LEVERAGED = re.compile(r".+(UP|DOWN|BULL|BEAR|[235][LS])$")
WEIGHTS = {"calm": 0.5, "lag": 0.5}
MIN_DAYS = SMA + 10


def tradable(base: str) -> bool:
    return base not in STABLE and base not in PEGGED and not LEVERAGED.match(base)


def features(daily: pd.DataFrame) -> pd.DataFrame:
    """Kennzahlen je Tageskerze (nur Daten bis einschließlich dieser Kerze)."""
    c = daily["close"].astype(float)
    qv = c * daily["volume"].astype(float)
    ma = c.rolling(SMA).mean()
    on = (c > ma) & ma.notna()
    # Tage seit dem letzten Wechsel auf grün (0 = heute grün geworden)
    grp = (on != on.shift()).cumsum()
    days_on = on.groupby(grp).cumcount().where(on)
    vol = c.pct_change().rolling(VOL_LOOK).std() * math.sqrt(365)
    vol3 = qv.rolling(3).mean()
    vol30 = qv.shift(3).rolling(30).mean()
    return pd.DataFrame({
        "ts": daily["ts"].values,
        "close": c.values,
        "sma": ma.values,
        "on": on.values,
        "days_on": days_on.values,
        "distance": ((c / ma - 1) * 100).values,
        "ret1": (c.pct_change() * 100).values,
        "ret7": (c.pct_change(7) * 100).values,
        "ret30": (c.pct_change(30) * 100).values,
        "qvol": qv.values,
        "qvol30": qv.rolling(30).mean().values,
        "vol_surge": (vol3 / vol30).values,
        "high20": (c >= c.shift(1).rolling(20).max()).values,
        "size": ((VOL_TARGET / vol).clip(upper=1.0) * on).values,
    })


def rank_score(rows: pd.DataFrame, btc_ret30: float | None) -> pd.Series:
    """Scanner-Score 0–100 für grüne Coins an einem Tag (Querschnitt), sonst NaN."""
    g = rows[rows["on"].astype(bool)]
    out = pd.Series(np.nan, index=rows.index)
    if g.empty:
        return out
    parts = pd.DataFrame(index=g.index)
    parts["calm"] = 1 - g["distance"].rank(pct=True)  # nah am 50-Tage-Schnitt
    parts["lag"] = 1 - (g["ret30"] - (btc_ret30 or 0.0)).rank(pct=True)  # noch nicht davongelaufen
    parts = parts.fillna(0.5)
    s = sum(parts[k] * w for k, w in WEIGHTS.items())
    out.loc[g.index] = (s * 100).round()
    return out


def analyze(dailies: dict, btc_symbol: str | None = None, now_ms: int | None = None) -> pd.DataFrame:
    """Letzte abgeschlossene Tageskerze aller Coins bewerten. dailies: Symbol -> Tageskerzen."""
    now_ms = now_ms or int(time.time() * 1000)
    rows = {}
    for sym, df in dailies.items():
        d = closed_daily(df.reset_index(drop=True), now_ms)
        if len(d) < MIN_DAYS:
            continue
        f = features(d).iloc[-1]
        if d["ts"].iloc[-1] < now_ms - 3 * DAY_MS:
            continue  # nicht mehr gehandelt
        rows[sym] = f
    if not rows:
        return pd.DataFrame()
    t = pd.DataFrame(rows).T
    for col in t.columns:
        if col not in ("on", "high20"):
            t[col] = pd.to_numeric(t[col], errors="coerce")
    t["on"] = t["on"].astype(bool)
    t["high20"] = t["high20"].astype(bool)
    btc = float(t.loc[btc_symbol, "ret30"]) if btc_symbol in t.index else None
    t["rs30"] = t["ret30"] - (btc or 0.0)
    t["score"] = rank_score(t, btc)
    return t.sort_values(["score", "rs30"], ascending=False, na_position="last")


# ---------- Live-Scan an der Börse ----------
def universe(ex, quote: str, top: int, min_volume: float) -> list[dict]:
    """Die meistgehandelten Spot-Paare in `quote` (ohne Stablecoins, Wrapped- und Hebel-Token)."""
    ex.load_markets()
    pairs = {s: m for s, m in ex.markets.items()
             if m.get("spot") and m.get("quote") == quote and m.get("active", True) is not False
             and tradable(m.get("base", ""))}
    tickers = ex.fetch_tickers()
    out = []
    for s, m in pairs.items():
        t = tickers.get(s) or {}
        qv = t.get("quoteVolume")
        if qv is None and t.get("baseVolume") is not None and t.get("last"):
            qv = t["baseVolume"] * t["last"]
        if not qv or qv < min_volume:
            continue
        out.append({"symbol": s, "base": m["base"], "volume24h": float(qv),
                    "last": t.get("last"), "change24h": t.get("percentage")})
    out.sort(key=lambda x: -x["volume24h"])
    return out[:top]


def fetch_daily(ex, symbol: str, days: int = 120) -> pd.DataFrame:
    since = ex.milliseconds() - days * DAY_MS
    rows = ex.fetch_ohlcv(symbol, "1d", since=since, limit=min(days, 300 if ex.id.startswith("coinbase") else 1000))
    return pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])


def run(cfg: Config, ex) -> dict:
    sc = cfg.scanner
    quote = cfg.symbols[0].split("/")[1] if cfg.symbols and "/" in cfg.symbols[0] else "USDT"
    uni = universe(ex, quote, sc.top, sc.min_volume)
    btc = f"BTC/{quote}"
    if btc not in [u["symbol"] for u in uni] and btc in ex.markets:
        uni.append({"symbol": btc, "base": "BTC", "volume24h": None, "last": None, "change24h": None})
    dailies = {}
    for u in uni:
        try:
            dailies[u["symbol"]] = fetch_daily(ex, u["symbol"])
        except Exception as e:  # einzelner Coin kaputt: überspringen
            log.warning("Scanner %s: %s", u["symbol"], e)
    t = analyze(dailies, btc, ex.milliseconds())
    info = {u["symbol"]: u for u in uni}
    from . import markets
    watched = set(markets.all_symbols(cfg))
    coins = []
    for sym, r in t.iterrows():
        u = info.get(sym, {})
        coins.append({
            "symbol": sym, "name": sym.split("/")[0], "price": r["close"], "change24h": u.get("change24h"),
            "volume24h": u.get("volume24h"), "ret7": r["ret7"], "ret30": r["ret30"], "rs30": r["rs30"],
            "vol_surge": r["vol_surge"], "distance": r["distance"], "on": bool(r["on"]),
            "days_on": None if pd.isna(r["days_on"]) else int(r["days_on"]), "high20": bool(r["high20"]),
            "size": r["size"], "score": None if pd.isna(r["score"]) else int(r["score"]),
            "watched": sym in watched, "focus": sym in cfg.symbols,
        })
    green = sum(c["on"] for c in coins)
    return {"created_at": int(time.time() * 1000), "exchange": ex.id, "quote": quote, "scanned": len(coins),
            "green": green, "breadth": green / len(coins) * 100 if coins else None,
            "btc_ret30": float(t.loc[btc, "ret30"]) if btc in t.index else None,
            "btc_on": bool(t.loc[btc, "on"]) if btc in t.index else None, "coins": coins}


def _path(cfg: Config) -> Path:
    return Path(cfg.database).parent / "scanner.json"


def load(cfg: Config) -> dict | None:
    try:
        return json.loads(_path(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save(cfg: Config, result: dict) -> None:
    from .ui import _clean
    p = _path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(_clean(result), ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def test_result() -> dict | None:
    """Mitgeliefertes Ergebnis des historischen Scanner-Tests (scripts/scanner_test.py)."""
    try:
        return json.loads(Path("results/scanner/scanner-test.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def picks(result: dict, n: int) -> list[dict]:
    """Die besten grünen Coins außerhalb der eigenen Liste."""
    return [c for c in result.get("coins", []) if c["on"] and c["score"] is not None and not c["watched"]][:n]


def format_report(result: dict, n: int = 5) -> str:
    from .notify import fmt_price
    lines = [f"🔍 Coin-Scanner · Top {result['scanned']} nach Volumen ({result['exchange']})"]
    if result.get("breadth") is not None:
        lines.append(f"Marktbreite: {result['green']} von {result['scanned']} Coins "
                     f"({result['breadth']:.0f} %) über dem 50-Tage-Schnitt")
    if result.get("btc_on") is False:
        lines.append("⚠️ BTC-Trendampel ist RAUS. In dieser Lage haben im Test auch grüne Altcoins meist verloren.")
    top = picks(result, n)
    if not top:
        lines += ["", "Kein Coin außerhalb deiner Liste hat gerade eine grüne Trendampel."]
    else:
        lines += ["", "Grüne Ampel, nah am 50-Tage-Schnitt (nicht in deiner Liste):"]
        for i, c in enumerate(top, 1):
            extra = []
            if c["days_on"] is not None and c["days_on"] <= 5:
                extra.append("frisch grün" if c["days_on"] else "heute grün geworden")
            if c["high20"]:
                extra.append("20-Tage-Hoch")
            vs = f"{c['vol_surge']:.1f}".replace(".", ",") if c["vol_surge"] is not None else "–"
            lines.append(f"{i}. {c['name']} {fmt_price(c['price'])} · Score {c['score']} · "
                         f"30 T vs. BTC {c['rs30']:+.0f} % · Volumen ×{vs}" + (" · " + ", ".join(extra) if extra else ""))
    lines += ["", "Beobachtungsliste, kein Kaufsignal: Im Test 2022–2026 schlug keine Altcoin-Auswahl BTC mit "
                  "Trendampel. Unter 🔍 Scanner kannst du einen Coin mit einem Klick zu deinen Charts hinzufügen."]
    return "\n".join(lines)


def maybe_run(cfg: Config, ex, db, notifier) -> dict | None:
    """Scan, wenn der letzte älter als `every_hours` ist; einmal am Tag eine Telegram-Übersicht."""
    sc = cfg.scanner
    if not sc.enabled:
        return None
    last = load(cfg)
    if last and time.time() * 1000 - last.get("created_at", 0) < sc.every_hours * 3_600_000:
        return None
    result = run(cfg, ex)
    save(cfg, result)
    log.info("Scanner: %d Coins geprüft, %d grün", result["scanned"], result["green"])
    if sc.telegram_daily and db.insert_scanner_report(int(time.time() * 1000) // DAY_MS):
        notifier.send(format_report(result, sc.telegram_top))
    return result
