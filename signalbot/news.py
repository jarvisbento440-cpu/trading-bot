"""News-Modul: Schlagzeilen aus kostenlosen RSS-Feeds (ohne API-Schlüssel) und Stimmungs-Bewertung.

Quellen: CoinDesk, Cointelegraph, Decrypt, The Block, Bitcoin Magazine, CryptoSlate, crypto.news, U.Today
und Google News (je Coin eine Suche, damit auch kleinere Coins wie ONDO Meldungen bekommen).
Dazu der Fear & Greed Index (alternative.me) als Markt-Stimmung.

Bewertung: feste Wortliste (kein KI-Dienst, kein Schlüssel). Jede Schlagzeile bekommt −2 … +2.
Das ist grob: Ironie, Gerüchte oder „Kurs fällt, aber …“ erkennt die Liste nicht.
"""
from __future__ import annotations

import email.utils
import hashlib
import html
import logging
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

import requests

log = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}
HOUR_MS = 3_600_000

FEEDS = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "Cointelegraph": "https://cointelegraph.com/rss",
    "Decrypt": "https://decrypt.co/feed",
    "The Block": "https://www.theblock.co/rss.xml",
    "Bitcoin Magazine": "https://bitcoinmagazine.com/.rss/full/",
    "CryptoSlate": "https://cryptoslate.com/feed/",
    "crypto.news": "https://crypto.news/feed/",
    "U.Today": "https://u.today/rss",
}
GOOGLE = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"

# Woran man erkennt, dass eine Schlagzeile einen Coin betrifft. Kürzel nur in Großbuchstaben (SOL ≠ "sol").
COIN_WORDS = {
    "BTC": (["bitcoin"], ["BTC"]),
    "ETH": (["ethereum", "ether"], ["ETH"]),
    "SOL": (["solana"], ["SOL"]),
    "XRP": (["ripple", "xrp ledger"], ["XRP"]),
    "ONDO": (["ondo finance", "ondo global", "ondo chain", "ondo token"], ["ONDO"]),
    "DOGE": (["dogecoin"], ["DOGE"]),
    "ADA": (["cardano"], ["ADA"]),
    "LINK": (["chainlink"], ["LINK"]),
    "AVAX": (["avalanche"], ["AVAX"]),
    "LTC": (["litecoin"], ["LTC"]),
    "BNB": (["binance coin"], ["BNB"]),
    "SUI": ([], ["SUI"]),
}
GOOGLE_QUERY = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana crypto", "XRP": "XRP", "ONDO": "Ondo Finance"}

# Wortliste: (Muster, Gewicht). Muster sind reguläre Ausdrücke auf der kleingeschriebenen Schlagzeile.
# Starke Wörter (|Gewicht| = 2) stehen für Ereignisse, die Kurse erfahrungsgemäß sofort bewegen.
LEXICON: list[tuple[str, float]] = [
    # stark negativ
    (r"\bhack(ed|s|ers?)?\b", -2), (r"\bexploit(ed|s)?\b", -2), (r"\bdrain(ed|s)?\b", -2), (r"\bstolen\b", -2),
    (r"\bbankrupt(cy)?\b", -2), (r"\binsolven(t|cy)\b", -2), (r"\bdelist(s|ed|ing)?\b", -2),
    (r"\bsec (sues|charges)\b", -2), (r"\bsued?\b", -1.5), (r"\blawsuit\b", -1), (r"\bfraud\b", -2),
    (r"\bponzi\b", -2), (r"\brug ?pull\b", -2), (r"\bcrash(es|ed|ing)?\b", -2), (r"\bcollapse[sd]?\b", -2),
    (r"\bban(s|ned)?\b", -1.5), (r"\bcrackdown\b", -1.5), (r"\barrest(ed|s)?\b", -1.5),
    # negativ
    (r"\bplunge[sd]?\b", -1.5), (r"\btumble[sd]?\b", -1), (r"\bslump(s|ed)?\b", -1), (r"\bsink(s|ing)?\b", -1),
    (r"\bdrop(s|ped)?\b", -0.7), (r"\bfall(s|ing)?\b", -0.7), (r"\bfell\b", -0.7), (r"\bdip(s|ped)?\b", -0.5),
    (r"\bsell-?off\b", -1.5), (r"\bbleed(s|ing)?\b", -1), (r"\bdump(s|ed|ing)?\b", -1), (r"\bliquidat(ed|ions?)\b", -1),
    (r"\boutflows?\b", -1), (r"\bbearish\b", -1), (r"\bfears?\b", -0.7), (r"\bwarn(s|ing)?\b", -0.7),
    (r"\bprobe\b", -1), (r"\binvestigat(ion|es|ed)\b", -1), (r"\bfine[sd]?\b", -0.7), (r"\breject(s|ed)?\b", -1),
    (r"\bdelay(s|ed)?\b", -0.7), (r"\boutage\b", -1), (r"\bhalt(s|ed)?\b", -1), (r"\bvulnerab(le|ility)\b", -1),
    (r"\bscam\b", -1.5), (r"\blows?\b", -0.5), (r"\bloss(es)?\b", -0.7), (r"\bunlock(s)?\b", -0.5),
    (r"\bcorrection\b", -0.7), (r"\bweak(ness|ens)?\b", -0.5), (r"\bpressure\b", -0.5),
    # positiv
    (r"\betf (approval|approved)\b", 2), (r"\bapprove[sd]?\b", 1), (r"\binflows?\b", 1),
    (r"\b(all-time|record) high\b", 1.5), (r"\bath\b", 1.5), (r"\bsurge[sd]?\b", 1.5), (r"\bsoar(s|ed|ing)?\b", 1.5),
    (r"\brall(y|ies|ied)\b", 1), (r"\bjump(s|ed)?\b", 1), (r"\bclimb(s|ed)?\b", 0.7), (r"\brise[sn]?\b", 0.7),
    (r"\bgain(s|ed)?\b", 0.7), (r"\brebound(s|ed)?\b", 0.7), (r"\brecover(s|y|ed)?\b", 0.5),
    (r"\bbullish\b", 1), (r"\bbreak(s|ing)? out\b", 1), (r"\bbreakout\b", 1),
    (r"\bpartner(s|ship)?\b", 0.7), (r"\badopt(s|ion|ed)?\b", 0.7), (r"\blaunch(es|ed)?\b", 0.5),
    (r"\blist(s|ing)? on\b", 1), (r"\bupgrade[sd]?\b", 0.5), (r"\baccumulat(e|es|ion|ing)\b", 1),
    (r"\b(buys|buying|bought|purchase[sd]?)\b", 0.7), (r"\buptrend\b", 0.7), (r"\bdowntrend\b", -0.7), (r"\breserve\b", 0.7), (r"\bwins?\b", 1), (r"\bvictory\b", 1),
    (r"\bdismiss(es|ed)?\b", 1), (r"\bsettle(s|d|ment)\b", 0.7), (r"\bclarity\b", 0.5), (r"\bboost(s|ed)?\b", 0.7),
]
_LEX = [(re.compile(p), w) for p, w in LEXICON]
NEGATION = re.compile(r"\b(no|not|denies|deny|despite|fails? to|won't|isn't|aren't|dodges?|avoids?|escapes?|survives?)\b")
# „Shorts liquidated“ oder „recovers from hack“ drehen die Richtung um
REVERSE = re.compile(r"\b(shorts? (liquidat|squeez)|recover(s|ed)? from|after (the )?(hack|crash|plunge|sell-?off))")


def score_title(title: str) -> float:
    """−2 (sehr negativ) … +2 (sehr positiv). 0 = neutral oder unklar."""
    t = title.lower()
    s = sum(w for rx, w in _LEX if rx.search(t))
    if s and REVERSE.search(t):
        s = abs(s) * 0.5
    elif s and NEGATION.search(t):
        s *= 0.3
    return max(-2.0, min(2.0, s))


def coins_in(title: str, extra: dict[str, tuple[list[str], list[str]]] | None = None) -> list[str]:
    words = {**COIN_WORDS, **(extra or {})}
    low = title.lower()
    out = []
    for coin, (names, tickers) in words.items():
        if any(re.search(r"\b" + re.escape(n) + r"\b", low) for n in names) or \
           any(re.search(r"(?<![A-Za-z])\$?" + re.escape(t) + r"(?![A-Za-z])", title) for t in tickers):
            out.append(coin)
    return out


def _text(el, *names) -> str:
    for n in names:
        x = el.find(n)
        if x is not None and (x.text or x.get("href")):
            return (x.text or x.get("href") or "").strip()
    return ""


def parse_feed(xml: str, source: str) -> list[dict]:
    """RSS 2.0 und Atom. Gibt [{id, ts, source, title, url}] zurück."""
    try:
        root = ET.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    except ET.ParseError:
        return []
    atom = "{http://www.w3.org/2005/Atom}"
    items = root.findall(".//item") or root.findall(f".//{atom}entry")
    out = []
    for it in items:
        title = html.unescape(_text(it, "title", f"{atom}title"))
        link = _text(it, "link", f"{atom}link")
        when = _text(it, "pubDate", f"{atom}published", f"{atom}updated")
        src = source
        s = it.find("source")
        if s is not None and s.text:  # Google News: eigentliche Quelle steht im <source>-Feld
            src = s.text.strip()
            if title.endswith(" - " + src):
                title = title[: -len(src) - 3]
        ts = _parse_date(when)
        if not title or ts is None:
            continue
        key = hashlib.sha1((link or title).encode("utf-8")).hexdigest()[:16]
        out.append({"id": key, "ts": ts, "source": src, "title": title.strip(), "url": link})
    return out


def _parse_date(s: str) -> int | None:
    if not s:
        return None
    try:
        d = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            from datetime import datetime
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        from datetime import timezone
        d = d.replace(tzinfo=timezone.utc)
    return int(d.timestamp() * 1000)


def feed_urls(coins: list[str]) -> dict[str, str]:
    urls = dict(FEEDS)
    for c in coins:
        q = GOOGLE_QUERY.get(c, f"{c} crypto")
        urls[f"Google News {c}"] = GOOGLE.format(q=quote_plus(q + " when:2d"))
    return urls


def fetch(coins: list[str], timeout: int = 12) -> tuple[list[dict], list[str]]:
    """Holt alle Feeds. Gibt (Meldungen, fehlgeschlagene Quellen) zurück."""
    items, failed = [], []
    for name, url in feed_urls(coins).items():
        try:
            r = requests.get(url, headers=UA, timeout=timeout)
            r.raise_for_status()
            items += parse_feed(r.text, name)
        except requests.RequestException as e:
            log.info("News-Quelle %s nicht erreichbar: %s", name, e)
            failed.append(name)
    return items, failed


def fear_greed(limit: int = 31) -> list[dict]:
    """Fear & Greed Index (0 = extreme Angst, 100 = extreme Gier), neuester zuerst."""
    r = requests.get("https://api.alternative.me/fng/", params={"limit": limit, "format": "json"}, headers=UA, timeout=12)
    r.raise_for_status()
    return [{"ts": int(x["timestamp"]) * 1000, "value": int(x["value"]), "label": x["value_classification"]}
            for x in r.json().get("data", [])]


FNG_DE = {"Extreme Fear": "extreme Angst", "Fear": "Angst", "Neutral": "neutral", "Greed": "Gier",
          "Extreme Greed": "extreme Gier"}


def base(symbol: str) -> str:
    return symbol.split("/")[0].upper()


def sync(db, coins: list[str], max_age_days: int = 3) -> dict:
    """Neue Schlagzeilen holen, bewerten und speichern. Gibt {new, failed} zurück."""
    items, failed = fetch(coins)
    cutoff = int(time.time() * 1000) - max_age_days * 24 * HOUR_MS
    rows = []
    for it in items:
        if it["ts"] < cutoff:
            continue
        cs = coins_in(it["title"])  # nur Coins, die im Titel stehen (Google-Suche liefert auch Fremdes)
        rows.append({**it, "coins": ",".join(cs), "score": score_title(it["title"])})
    new = db.save_news(rows)
    try:
        fg = fear_greed()
        db.set_context("fear_greed", fg)
    except (requests.RequestException, ValueError, KeyError) as e:
        log.info("Fear & Greed nicht erreichbar: %s", e)
        failed.append("Fear & Greed")
    db.set_context("news_status", {"ts": int(time.time() * 1000), "failed": failed, "sources": len(feed_urls(coins))})
    return {"new": new, "failed": failed}


# Getestete Regel: Trendampel-Long pausieren, solange der 3-Tage-Schnitt unter −0,2 liegt (docs/news-onchain.md)
FILTER_THRESHOLD = -0.2


def summary(db, symbol: str, hours: int = 72, now: int | None = None) -> dict:
    """Stimmung für einen Coin aus den Schlagzeilen der letzten `hours` Stunden.

    score: jüngere Meldungen zählen mehr (Halbwertszeit 12 h). news3: einfacher Schnitt über 3 Tage (wie im Test).
    Doppelte Schlagzeilen (gleicher Titel bei mehreren Quellen) zählen einmal.
    """
    now = now or int(time.time() * 1000)
    coin = base(symbol)
    rows = db.news_since(now - hours * HOUR_MS, coin)
    seen, used = set(), []
    for r in rows:
        k = re.sub(r"\W+", "", r["title"].lower())[:80]
        if k in seen:
            continue
        seen.add(k)
        used.append(r)
    wsum = ssum = 0.0
    for r in used:
        w = 0.5 ** ((now - r["ts"]) / (12 * HOUR_MS))
        wsum += w
        ssum += w * r["score"]
    avg = ssum / wsum if wsum else 0.0
    # Wert wie im Test (scripts/research_context.py): einfacher Schnitt der letzten 3 Tage
    last3 = [r["score"] for r in used if now - r["ts"] <= 72 * HOUR_MS]
    news3 = sum(last3) / len(last3) if len(last3) >= 3 else None
    strong_neg = [r for r in used if r["score"] <= -2 and now - r["ts"] <= 12 * HOUR_MS]
    strong_pos = [r for r in used if r["score"] >= 2 and now - r["ts"] <= 12 * HOUR_MS]
    return {"coin": coin, "score": round(avg, 2), "count": len(used),
            "news3": round(news3, 2) if news3 is not None else None, "news3_n": len(last3),
            "filter": news3 is not None and news3 < FILTER_THRESHOLD,
            "pos": sum(r["score"] > 0 for r in used), "neg": sum(r["score"] < 0 for r in used),
            "label": label(news3 if news3 is not None else avg, len(last3) if news3 is not None else len(used)), "strong_neg": strong_neg[:3], "strong_pos": strong_pos[:3],
            "latest": used[:8]}


def label(avg: float, n: int) -> str:
    if n < 3:
        return "zu wenig Meldungen"
    if avg >= 0.6:
        return "positiv"
    if avg >= 0.2:
        return "leicht positiv"
    if avg <= -0.6:
        return "negativ"
    if avg <= -0.2:
        return "leicht negativ"
    return "neutral"


def fear_greed_now(db) -> dict | None:
    fg = db.get_context("fear_greed")
    if not fg:
        return None
    cur = fg[0]
    week = [x["value"] for x in fg[:7]]
    return {"value": cur["value"], "label": FNG_DE.get(cur["label"], cur["label"]), "ts": cur["ts"],
            "avg7": round(sum(week) / len(week), 1), "history": [[x["ts"], x["value"]] for x in fg[::-1]]}
