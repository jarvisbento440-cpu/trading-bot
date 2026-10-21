"""Kurse für Aktien, Indizes, Rohstoffe und Devisen von Yahoo Finance (kostenlos, ohne API-Key).

Symbole wie bei Yahoo: ^GSPC (S&P 500), GC=F (Gold), SI=F (Silber), EURUSD=X, NVDA ...
"""
from __future__ import annotations

import logging

import pandas as pd
import requests

from .db import Database

log = logging.getLogger(__name__)
EXCHANGE = "yahoo"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}
CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SEARCH = "https://query2.finance.yahoo.com/v1/finance/search"
H_MS, D_MS = 3_600_000, 86_400_000

# Schnellauswahl im Suchfeld
POPULAR = [
    ("^GSPC", "S&P 500", "Index"), ("^NDX", "Nasdaq 100", "Index"), ("^DJI", "Dow Jones", "Index"),
    ("^GDAXI", "DAX", "Index"), ("^ATX", "ATX", "Index"), ("GC=F", "Gold", "Rohstoff"),
    ("SI=F", "Silber", "Rohstoff"), ("CL=F", "Öl (WTI)", "Rohstoff"), ("HG=F", "Kupfer", "Rohstoff"),
    ("EURUSD=X", "EUR/USD", "Devisen"), ("DX-Y.NYB", "US-Dollar-Index", "Index"), ("^VIX", "VIX (Angst-Index)", "Index"),
    ("NVDA", "Nvidia", "Aktie"), ("TSLA", "Tesla", "Aktie"), ("AAPL", "Apple", "Aktie"), ("MSTR", "MicroStrategy", "Aktie"),
    ("COIN", "Coinbase", "Aktie"), ("IBIT", "iShares Bitcoin ETF", "ETF"),
]
TYPES = {"EQUITY": "Aktie", "ETF": "ETF", "INDEX": "Index", "FUTURE": "Rohstoff/Future", "CURRENCY": "Devisen",
         "CRYPTOCURRENCY": "Krypto", "MUTUALFUND": "Fonds"}


def is_yahoo(symbol: str) -> bool:
    return "/" not in symbol


def search(q: str, limit: int = 12) -> list[dict]:
    r = requests.get(SEARCH, params={"q": q, "quotesCount": limit, "newsCount": 0}, headers=HEADERS, timeout=10)
    r.raise_for_status()
    out = []
    for x in r.json().get("quotes", []):
        if not x.get("symbol") or x.get("quoteType") == "CRYPTOCURRENCY":
            continue  # Krypto kommt von der Börse
        out.append({"symbol": x["symbol"], "name": x.get("shortname") or x.get("longname") or x["symbol"],
                    "type": TYPES.get(x.get("quoteType", ""), x.get("quoteType", "")), "where": x.get("exchDisp", "")})
    return out


def fetch(symbol: str, interval: str, rng: str) -> list[list]:
    """[[ts_ms, open, high, low, close, volume], ...]"""
    r = requests.get(CHART.format(symbol=requests.utils.quote(symbol, safe="")),
                     params={"interval": interval, "range": rng, "includePrePost": "false"}, headers=HEADERS, timeout=20)
    r.raise_for_status()
    res = (r.json().get("chart", {}).get("result") or [None])[0]
    if not res or not res.get("timestamp"):
        return []
    q = res["indicators"]["quote"][0]
    rows = []
    for i, t in enumerate(res["timestamp"]):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        rows.append([int(t) * 1000, float(o), float(h), float(l), float(c), float(q["volume"][i] or 0)])
    step = {"60m": H_MS, "15m": 900_000}.get(interval)
    if step and len(rows) > 2:
        # Yahoo hängt den aktuellen Kurs als Extra-Zeile mit "krummer" Zeit an: nur Zeilen im Kerzen-Raster behalten
        mods = pd.Series([r[0] % step for r in rows]).mode()
        rows = [r for r in rows if r[0] % step == mods.iloc[0]]
    return rows


def to_4h(rows: list[list]) -> list[list]:
    if not rows:
        return []
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    g = df.groupby(df["ts"] // (4 * H_MS) * (4 * H_MS))
    out = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                        "close": g["close"].last(), "volume": g["volume"].sum()}).reset_index()
    return out[["ts", "open", "high", "low", "close", "volume"]].values.tolist()


def sync(db: Database, symbol: str) -> int:
    """1h (bis 2 Jahre), 4h (aus 1h gebaut) und 1d (10 Jahre) speichern."""
    total = 0
    first = db.last_ts(EXCHANGE, symbol, "1h") is None
    h1 = fetch(symbol, "60m", "730d" if first else "1mo")
    total += db.save_candles(EXCHANGE, symbol, "1h", h1)
    if h1:
        # 4h immer aus den gespeicherten 1h-Kerzen der letzten Zeit neu bauen
        recent = db.candles(EXCHANGE, symbol, "1h", 24 * 750 if first else 24 * 40)
        db.save_candles(EXCHANGE, symbol, "4h", to_4h(recent[["ts", "open", "high", "low", "close", "volume"]].values.tolist()))
    d1 = fetch(symbol, "1d", "10y" if db.last_ts(EXCHANGE, symbol, "1d") is None else "3mo")
    # Tageskerzen auf 00:00 UTC legen (Yahoo liefert die Eröffnungszeit der Börse)
    d1 = [[r[0] // D_MS * D_MS, *r[1:]] for r in d1]
    total += db.save_candles(EXCHANGE, symbol, "1d", d1)
    log.info("%s (Yahoo): %d Kerzen aktualisiert", symbol, total)
    return total
