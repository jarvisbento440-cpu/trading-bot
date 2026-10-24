"""Bringt News und On-Chain zusammen: Hinweise für Signale, Telegram und Oberfläche."""
from __future__ import annotations

import logging
import time

from . import news, onchain

log = logging.getLogger(__name__)


class Updater:
    """Holt News und On-Chain-Daten höchstens alle n Minuten (wird im Kurs-Durchlauf aufgerufen)."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.next_news = 0.0
        self.next_onchain = 0.0

    def run(self, db, notifier=None) -> None:
        coins = sorted({news.base(s) for s in _crypto_symbols(self.cfg)})
        now = time.time()
        if self.cfg.news and now >= self.next_news:
            self.next_news = now + self.cfg.news_minutes * 60
            try:
                news.sync(db, coins)
                db.prune_news(int((now - 14 * 86400) * 1000))
                if notifier and self.cfg.news_alerts:
                    alert_strong_news(db, coins, notifier)
            except Exception:
                log.exception("News-Abruf fehlgeschlagen")
        if self.cfg.onchain and now >= self.next_onchain:
            self.next_onchain = now + self.cfg.onchain_minutes * 60
            try:
                onchain.sync(db, coins)
            except Exception:
                log.exception("On-Chain-Abruf fehlgeschlagen")


def _crypto_symbols(cfg) -> list[str]:
    from .markets import all_symbols
    return [s for s in all_symbols(cfg) if "/" in s]


def coin_context(db, cfg, symbol: str) -> dict:
    out = {"symbol": symbol}
    if cfg.news:
        out["news"] = news.summary(db, symbol)
        out["fear_greed"] = news.fear_greed_now(db)
    if cfg.onchain:
        out["onchain"] = onchain.view(db.get_context("onchain"), symbol)
    return out


def headwind(ctx: dict, side: str) -> list[str]:
    """Gründe, die gegen das Signal sprechen (leer = kein starker Gegenwind).

    Getestet ist nur die News-Regel für Long (docs/news-onchain.md); starke Einzelmeldungen sind ein Hinweis.
    """
    out = []
    n = ctx.get("news") or {}
    long = side == "long"
    if long and n.get("filter"):
        out.append(f"News der letzten 3 Tage negativ ({n['news3']:+.2f}, {n['news3_n']} Meldungen)".replace(".", ","))
    for r in (n.get("strong_neg" if long else "strong_pos") or [])[:2]:
        out.append(f"Starke {'negative' if long else 'positive'} Meldung: „{r['title']}“ ({r['source']})")
    return out


def reason_lines(ctx: dict) -> list[str]:
    """Kurze Zeilen für Telegram/Signal-Gründe."""
    lines = []
    n = ctx.get("news")
    if n:
        lines.append(f"News 3 Tage: {n['label']}" + (f" ({n['news3']:+.2f}, {n['news3_n']} Meldungen)".replace(".", ",")
                                                     if n.get("news3") is not None else ""))
    fg = ctx.get("fear_greed")
    if fg:
        lines.append(f"Fear & Greed: {fg['value']} ({fg['label']})")
    oc = ctx.get("onchain")
    if oc and oc.get("rows"):
        f = next((r for r in oc["rows"] if r["name"].startswith("Funding")), None)
        if f:
            lines.append(f"Funding: {f['value']} – {f['note']}")
    return lines


def snapshot(ctx: dict) -> dict:
    """Kleiner Auszug, der mit jedem Signal gespeichert wird (für die spätere Auswertung im Papier-Test)."""
    n, oc, fg = ctx.get("news") or {}, ctx.get("onchain") or {}, ctx.get("fear_greed") or {}
    return {"news": n.get("news3"), "news_n": n.get("news3_n"), "news_filter": bool(n.get("filter")), "strong_neg": len(n.get("strong_neg") or []),
            "strong_pos": len(n.get("strong_pos") or []), "onchain": oc.get("score"), "fng": fg.get("value")}


def alert_strong_news(db, coins: list[str], notifier, hours: int = 6, cooldown_h: float = 3) -> int:
    """Schickt sehr starke Meldungen (±2) zu beobachteten Coins per Telegram: jede einmal, je Coin höchstens alle 3 h."""
    now = time.time()
    since = int((now - hours * 3600) * 1000)
    sent = 0
    for r in db.news_since(since):
        cs = [c for c in (r["coins"] or "").split(",") if c in coins]
        if not cs or abs(r["score"]) < 2 or r["alerted"]:
            continue
        last = max((db.get_context(f"news_alert_{c}") or 0) for c in cs)
        if now - last < cooldown_h * 3600 or not db.mark_news_alerted(r["id"]):
            continue
        for c in cs:
            db.set_context(f"news_alert_{c}", now)
        icon = "🚨" if r["score"] < 0 else "📈"
        notifier.send(f"{icon} News zu {', '.join(cs)} ({'stark negativ' if r['score'] < 0 else 'stark positiv'})\n"
                      f"{r['title']}\n{r['source']} · {r['url'] or ''}\n\n"
                      "Automatische Bewertung per Wortliste – bitte selbst lesen, bevor du handelst.")
        sent += 1
        if sent >= 3:  # nicht fluten
            break
    return sent
