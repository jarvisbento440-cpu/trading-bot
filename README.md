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

## Starten unter Windows (mit Oberfläche)

1. Python installieren: https://www.python.org/downloads/ → bei der Installation **„Add python.exe to PATH“** anhaken.
2. Ordner entpacken, **Doppelklick auf `Start.bat`**.
3. Beim ersten Start werden Pakete installiert und 2 Jahre Kursdaten geladen (einige Minuten). Danach öffnet sich das Fenster.

Das schwarze Konsolenfenster muss offen bleiben, solange der Bot läuft.

### Die Oberfläche

- Alle Coins nebeneinander, oben Zeitebene (1 Std / 4 Std / 1 Tag) wählen.
- Ein- und ausblendbar: Signal-Pfeile mit Score, EMA 20/50/200, Fibonacci-Retracement, Unterstützung/Widerstand, Bollinger-Bänder.
- Aktuelles Signal: Einstieg (blau), Stop (rot), Ziel 1 und 2 (grün) als Linien.
- **Neues Signal:** Die Kachel blinkt gelb, es piept und Windows zeigt eine Benachrichtigung. Klick auf die Kachel öffnet den Coin im Vollbild mit allen Details. Esc schließt.

## Starten (Mac/Linux, Terminal)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # Telegram-Daten eintragen (optional)
python -m signalbot backfill   # einmalig: 2 Jahre Historie laden (dauert ein paar Minuten)
python -m signalbot once       # einmal prüfen, Signale anzeigen
python -m signalbot run        # Dauerbetrieb ohne Oberfläche, prüft alle 5 Minuten
python -m signalbot ui         # Oberfläche im Browser
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

## Strategien und Backtest

8 Strategien (Score-Modell, Donchian, Supertrend, MACD, RSI, Bollinger-Squeeze, Fibonacci Golden Pocket, Liquiditäts-Sweep) mit Erklärung und Quellen: [docs/strategien.md](docs/strategien.md).

- Backtest im Programm: Button **„📊 Backtest“**. Ergebnis mit 1 Jahr echter Kurse: [results/backtest-bericht.md](results/backtest-bericht.md).
- Neu berechnen im Terminal: `python -m signalbot backtest --days 365`
- Auf GitHub: Reiter „Actions“ → „Backtest“ → „Run workflow“ (läuft auf GitHub-Servern mit Coinbase-Kursen und speichert das Ergebnis in `results/`).

## Nächste Schritte

4. Backtest → echte Trefferquoten pro Score
5. Signal-Tracking (Ziel/Stop erreicht) + Wochenbericht
6. News-Modul, 7. On-Chain-Modul, 8. Coin-Scanner
