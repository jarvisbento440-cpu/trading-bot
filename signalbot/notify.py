from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)

DISCLAIMER = "Signale und Trefferquoten sind keine Gewinngarantie. Immer mit Stop handeln, max. 1–2 % Risiko pro Trade."


def fmt_price(p: float) -> str:
    digits = 2 if p >= 100 else 4 if p >= 1 else 5
    return f"{p:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_signal(symbol: str, timeframe: str, s, strategy_name: str = "Score-Modell", hist: dict | None = None,
                  hitrate: dict | None = None, setup: int | None = None) -> str:
    from .hitrates import format_line
    icon = "🟢" if s.side == "long" else "🔴"
    rr = abs(s.target1 - s.entry) / abs(s.entry - s.stop)
    if hitrate:
        quote = format_line(hitrate)
    elif hist and hist.get("trades"):
        quote = (f"Trefferquote im Backtest: {hist['winrate'] * 100:.0f} % "
                 f"({hist['trades']} Trades, Ø {hist['avg_r']:+.2f} R)").replace(".", ",")
    else:
        quote = "Trefferquote: noch kein Backtest"
    lines = [
        f"{icon} {symbol} {s.side.upper()} ({timeframe}) · {strategy_name}",
        f"Einstieg: ~{fmt_price(s.entry)}",
        f"Stop: {fmt_price(s.stop)}",
        f"Ziel 1: {fmt_price(s.target1)}   Ziel 2: {fmt_price(s.target2)}",
        f"Chance/Risiko (Ziel 1): 1 : {rr:.1f}".replace(".", ","),
        *([f"Setup-Score: {setup if setup is not None else s.score}/100"]
          if (setup if setup is not None else getattr(s, "score", 0)) else []),
        quote,
        "Gründe:",
        *[f"• {r}" for r in s.reasons],
        "",
        DISCLAIMER,
    ]
    return "\n".join(lines)


class Notifier:
    def __init__(self, token: str, chat_id: str):
        self.token, self.chat_id = token, chat_id

    def send(self, text: str) -> None:
        if not (self.token and self.chat_id):
            # Ohne Telegram-Daten nur in der Konsole ausgeben
            print("\n" + text + "\n")
            return
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": text},
                timeout=15,
            )
            r.raise_for_status()
        except requests.RequestException as e:
            log.error("Telegram-Nachricht fehlgeschlagen: %s", e)
            print("\n" + text + "\n")
