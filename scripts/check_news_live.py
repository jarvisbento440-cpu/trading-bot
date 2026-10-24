"""Probelauf des News- und On-Chain-Moduls mit echten Daten (für GitHub Actions)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from signalbot import context, news, onchain  # noqa: E402
from signalbot.config import Config  # noqa: E402
from signalbot.db import Database  # noqa: E402

COINS = ["BTC", "ETH", "SOL", "XRP", "ONDO"]


def main(out: str) -> None:
    o = Path(out)
    o.mkdir(parents=True, exist_ok=True)
    cfg = Config(database=str(o / "live.db"), symbols=[c + "/USDT" for c in COINS])
    db = Database(cfg.database)
    res = {"news_sync": news.sync(db, COINS), "onchain_failed": onchain.sync(db, COINS)["failed"], "coins": {}}
    for c in COINS:
        ctx = context.coin_context(db, cfg, c + "/USDT")
        res["coins"][c] = {"lines": context.reason_lines(ctx), "headwind_long": context.headwind(ctx, "long"),
                           "news": {k: v for k, v in ctx["news"].items() if k != "latest"},
                           "latest": [(r["score"], r["source"], r["title"]) for r in ctx["news"]["latest"]],
                           "onchain": ctx["onchain"]}
    res["fear_greed"] = news.fear_greed_now(db)
    res["news_total"] = db.conn.execute("SELECT COUNT(*), SUM(coins != ''), AVG(score) FROM news").fetchone()
    text = json.dumps(res, indent=1, ensure_ascii=False, default=str)
    (o / "live.json").write_text(text, encoding="utf-8")
    print(text[:20000])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "live-check")
