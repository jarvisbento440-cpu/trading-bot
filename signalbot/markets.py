"""Frei gewählte Märkte (zusätzliche Kacheln): Krypto von der Börse oder Aktien/Indizes/Rohstoffe von Yahoo."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from . import yahoo
from .config import Config

log = logging.getLogger(__name__)


def _path(cfg: Config) -> Path:
    return Path(cfg.database).parent / "watchlist.json"


def load_extra(cfg: Config) -> list[dict]:
    try:
        data = json.loads(_path(cfg).read_text(encoding="utf-8"))
        return [x for x in data if isinstance(x, dict) and x.get("symbol")]
    except (OSError, ValueError):
        return []


def save_extra(cfg: Config, items: list[dict]) -> None:
    p = _path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def add(cfg: Config, symbol: str, name: str = "", kind: str = "") -> list[dict]:
    items = [x for x in load_extra(cfg) if x["symbol"] != symbol]
    if symbol not in cfg.symbols:
        items.append({"symbol": symbol, "name": name or symbol, "type": kind})
    save_extra(cfg, items)
    return items


def remove(cfg: Config, symbol: str) -> list[dict]:
    items = [x for x in load_extra(cfg) if x["symbol"] != symbol]
    save_extra(cfg, items)
    return items


def all_symbols(cfg: Config) -> list[str]:
    return cfg.symbols + [x["symbol"] for x in load_extra(cfg) if x["symbol"] not in cfg.symbols]


def exchange_for(cfg: Config, symbol: str) -> str:
    return yahoo.EXCHANGE if yahoo.is_yahoo(symbol) else cfg.exchange


def sync_extra(cfg: Config, ex, db) -> None:
    from .data import sync_all
    extra = [x["symbol"] for x in load_extra(cfg) if x["symbol"] not in cfg.symbols]
    crypto = [s for s in extra if not yahoo.is_yahoo(s)]
    if crypto:
        sync_all(ex, db, crypto, cfg.store_timeframes, cfg.backfill_days)
    for s in extra:
        if yahoo.is_yahoo(s):
            try:
                yahoo.sync(db, s)
            except Exception as e:  # Yahoo nicht erreichbar: beim nächsten Durchlauf erneut
                log.error("Yahoo %s: %s", s, e)


def search(cfg: Config, ex, q: str) -> list[dict]:
    q = q.strip()
    out = []
    if not q:
        return [{"symbol": s, "name": n, "type": t, "where": "Yahoo"} for s, n, t in yahoo.POPULAR]
    ql = q.lower()
    out += [{"symbol": s, "name": n, "type": t, "where": "Yahoo"} for s, n, t in yahoo.POPULAR
            if ql in n.lower() or ql in s.lower()]
    # Krypto: alle Paare der eingestellten Börse in der Quote-Währung der Haupt-Coins
    quote = cfg.symbols[0].split("/")[1] if cfg.symbols and "/" in cfg.symbols[0] else "USDT"
    try:
        if ex is not None:
            if not ex.markets:
                ex.load_markets()
            hits = [m for m in ex.markets.values()
                    if m.get("spot") and m.get("quote") == quote and m.get("active", True) is not False
                    and (m["base"].lower().startswith(ql) or ql == m["symbol"].lower())]
            hits.sort(key=lambda m: (m["base"].lower() != ql, len(m["base"])))
            out += [{"symbol": m["symbol"], "name": m["base"], "type": "Krypto", "where": ex.name} for m in hits[:8]]
    except Exception as e:
        log.warning("Börsen-Suche: %s", e)
    try:
        seen = {x["symbol"] for x in out}
        out += [x for x in yahoo.search(q) if x["symbol"] not in seen]
    except Exception as e:
        log.warning("Yahoo-Suche: %s", e)
    return out[:25]
