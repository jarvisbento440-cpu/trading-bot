# Krypto-Signal-Bot

Beobachtet BTC, ETH, SOL, XRP und ONDO rund um die Uhr und schickt Einstiegs-Signale per Telegram.
**Der Bot handelt nicht selbst** und braucht keine Börsen-API-Keys: Kursdaten sind öffentlich.

> ⚠️ Der Setup-Score ist keine Gewinnwahrscheinlichkeit. Bei jedem Signal steht die echte Trefferquote ähnlicher Signale seit 2021 ([docs/trefferquoten.md](docs/trefferquoten.md)), aber auch das ist keine Garantie. Immer mit Stop handeln, max. 1–2 % Risiko pro Trade.

## Was er macht

1. Lädt Kerzen (15m, 1h, 4h, 1D) von der Börse in `config.yaml` (Standard: Binance) in eine SQLite-Datenbank.
2. Prüft auf 1h und 4h nach jeder abgeschlossenen Kerze:
   - Tages-Trend als Filter (Long nur im Aufwärtstrend, Short nur im Abwärtstrend)
   - EMA 20/50/200, Ausbruch aus 20-Kerzen-Spanne, Rücksetzer an EMA20, RSI, MACD, Volumen
   - daraus ein Score von 0 bis 100
3. Ab Score 65 (einstellbar) kommt ein Signal mit Einstieg, Stop (1,5 × ATR) und zwei Zielen.
4. Zu jedem Signal die echte Trefferquote ähnlicher Signale aus 5 Jahren Kursdaten und die Gewinnschwelle.
5. Jedes Signal läuft als virtueller Trade mit: Telegram-Nachricht, wenn Ziel oder Stop erreicht ist, und jeden Sonntag ein Wochenbericht.

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

**Long/Short-Fenster der Strategien:** Zu jedem Signal zeichnet der Chart ein Fenster wie bei TradingView: grün vom Einstieg bis Ziel 1, rot bis zum Stop, linke Kante in der Farbe der Strategie. Das Fenster zieht sich nach rechts, bis Stop oder Ziel berührt wird (berührt eine Kerze beides, zählt der Stop, wie im Backtest); laufende Fenster reichen bis zur letzten Kerze. Im Vollbild steht am Ende „✓ Ziel“, „✗ Stop“ oder „läuft“, rechts die Zählung. Blendest du eine Strategie aus, verschwinden auch ihre Fenster. Ein- und ausschalten oben mit „Long/Short-Fenster“ oder im Vollbild mit dem ersten Knopf.

**Eigene Einstiege einzeichnen:** Im Vollbild links die Werkzeugleiste: 📈 Long, 📉 Short, ➖ Linie. Werkzeug wählen und in den Chart klicken. Ziel und Stop ziehst du an den Linien, die Fläche verschiebt die ganze Position, der rechte Rand ändert die Länge. Rechts stehen Chance/Risiko, Status (wartet/läuft/Ziel/Stop) und die Positionsgröße für dein Risiko. Entf löscht die ausgewählte Zeichnung. Alles wird pro Coin gespeichert (data/drawings.json).

**Papier-Test:** Button „📝 Papier-Test“. Jedes Signal wird automatisch als virtueller Trade mitgeschrieben (Einstieg zur nächsten Kerze, Stop, Ziel, Ergebnis in R nach Gebühren) und ausgewertet, solange das Programm läuft. Filter „nur mit Trendampel“ und „nur eingeschaltete Strategien“, Umrechnung in Euro über Kapital und Risiko pro Trade. Es wird nichts wirklich gehandelt.

**Echte Trefferquoten, Signal-Tracking, Wochenbericht:** Bei jedem Signal steht, wie oft ähnliche Signale (gleiche Strategie, Zeitebene, Richtung, Score-Stufe) seit 2021 ihr Ziel erreicht haben, mit Spanne und Gewinnschwelle. Erreicht ein Signal Ziel oder Stop, kommt eine Telegram-Nachricht; sonntags um 18 Uhr ein Wochenbericht (einstellbar in `config.yaml`, sofort: `python -m signalbot bericht`). Ergebnis und Details: [docs/trefferquoten.md](docs/trefferquoten.md).

**Eigene Märkte:** Kachel „＋ Markt hinzufügen“ mit Suchfeld. Krypto kommt von der Börse (alle Paare), Aktien, Indizes (S&P 500, DAX …), Rohstoffe (Gold, Silber, Öl) und Devisen kostenlos von Yahoo Finance. ✕ oben rechts entfernt die Kachel. Im Vollbild lassen sich die Strategien oben direkt ein- und ausschalten.

**Börsenzeiten:** oben eine Uhr, welche Börse gerade offen ist (Asien = Tokio/Hongkong, Europa = London/Frankfurt, USA = New York), in deiner Ortszeit mit automatischer Sommer-/Winterzeit. In den 1h- und 4h-Charts zeigen farbige Streifen, wann welche Börse offen war (Schalter „Börsenzeiten“).

**Liquidations-Heatmap:** Buttons „Heatmap: 3 Tage / 1 Woche“ oben. Farbfläche im Chart, wo gehebelte Trader (10x–100x) liquidiert würden (geschätzt aus Kursen und Volumen, ähnlich Coinglass). Gelb = viel Liquidität; wird der Preis erreicht, verschwindet die Zone. Im Vollbild stehen die stärksten Zonen ober- und unterhalb des Kurses.

**Trendampel (empfohlen):** einfacher Tages-Trendfilter, der als einziger Ansatz auch im unberührten Prüfjahr vorne lag (+13 % statt −32 % bei Kaufen & Halten, größter Rückgang −44 % statt −85 %). Details und alle getesteten Regeln: [docs/trendampel.md](docs/trendampel.md).

**Lernmodell (aus Fehlsignalen lernen):** schätzt für jedes Signal die Trefferchance aus 45.000 vergangenen Signalen und meldet schwache Signale nicht mehr per Telegram (`learn_filter` in `config.yaml`). Im Prüfjahr sank der Verlust pro Trade von −0,12 R auf etwa 0 R, profitabel werden die Strategien dadurch aber nicht. Im Papier-Test steht bei jedem Trade, was dafür und dagegen sprach. Details: [docs/lernen.md](docs/lernen.md).

8 Strategien (Score-Modell, Donchian, Supertrend, MACD, RSI, Bollinger-Squeeze, Fibonacci Golden Pocket, Liquiditäts-Sweep) mit Erklärung und Quellen: [docs/strategien.md](docs/strategien.md).

- Backtest im Programm: Button **„📊 Backtest“**. Ergebnis mit 1 Jahr echter Kurse: [results/backtest-bericht.md](results/backtest-bericht.md).
- Neu berechnen im Terminal: `python -m signalbot backtest --days 365`
- Auf GitHub: Reiter „Actions“ → „Backtest“ → „Run workflow“ (läuft auf GitHub-Servern mit Coinbase-Kursen und speichert das Ergebnis in `results/`).

## Nächste Schritte

4. ~~Backtest → echte Trefferquoten pro Score~~ (erledigt)
5. ~~Signal-Tracking (Ziel/Stop erreicht) + Wochenbericht~~ (erledigt)
6. News-Modul, 7. On-Chain-Modul, 8. Coin-Scanner
