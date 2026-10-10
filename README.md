# Krypto-Signal-Bot

Beobachtet BTC, ETH, SOL, XRP und ONDO rund um die Uhr und schickt Einstiegs-Signale per Telegram.
**Der Bot handelt nicht selbst** und braucht keine Börsen-API-Keys: Kursdaten sind öffentlich.

> ⚠️ Der Setup-Score ist keine Gewinnwahrscheinlichkeit und keine Garantie. Echte Trefferquoten kommen erst mit dem Backtest (nächster Schritt). Immer mit Stop handeln, max. 1–2 % Risiko pro Trade.

## Was er macht

1. Lädt Kerzen (15m, 1h, 4h, 1D) von der Börse in `config.yaml` (Standard: Binance) in eine SQLite-Datenbank.
2. Prüft auf 1h und 4h nach jeder abgeschlossenen Kerze:
   - Tages-Trend als Filter (Long nur im Aufwärtstrend, Short nur im Abwärtstrend)
   - EMA 20/50/200, Ausbruch aus 20-Kerzen-Spanne, Rücksetzer an EMA20, RSI, MACD, Volumen
   - daraus ein Score von 0 bis 100
3. Ab Score 65 (einstellbar) kommt ein Signal mit Einstieg, Stop (1,5 × ATR) und zwei Zielen.
4. Jedes Signal wird gespeichert, damit es später ausgewertet werden kann.

## Starten (Mac/Linux)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # Telegram-Daten eintragen (optional)
python -m signalbot backfill   # einmalig: 2 Jahre Historie laden (dauert ein paar Minuten)
python -m signalbot once       # einmal prüfen, Signale anzeigen
python -m signalbot run        # Dauerbetrieb, prüft alle 5 Minuten
```

Ohne Telegram-Daten werden Signale nur im Terminal angezeigt.

## Telegram einrichten

1. In Telegram @BotFather öffnen, `/newbot`, Namen vergeben → Token in `.env` als `TELEGRAM_BOT_TOKEN`.
2. Deinem neuen Bot eine Nachricht schreiben.
3. Chat-ID z. B. über @userinfobot herausfinden → `TELEGRAM_CHAT_ID`.

## 24/7 auf einem Server (z. B. Hetzner)

```bash
docker compose up -d --build
docker compose logs -f
```

## Tests

```bash
pip install pytest && python -m pytest
```

## Nächste Schritte

4. Backtest → echte Trefferquoten pro Score
5. Signal-Tracking (Ziel/Stop erreicht) + Wochenbericht
6. News-Modul, 7. On-Chain-Modul, 8. Coin-Scanner
