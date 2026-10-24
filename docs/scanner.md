# Coin-Scanner

Sucht unter den meistgehandelten Coins der Börse weitere Coins mit grüner Trendampel, also außerhalb
von BTC, ETH, SOL, XRP und ONDO. Ergebnis in der Oberfläche unter **🔍 Scanner** und einmal am Tag per
Telegram.

## So funktioniert er

1. Alle Spot-Paare in USDT holen, Stablecoins (USDC, FDUSD …), Wrapped-Token (WBTC …), Gold-Token
   (PAXG) und Hebel-Token (…UP/…DOWN) aussortieren, die **150 Coins mit dem höchsten 24h-Volumen**
   nehmen (mindestens 2 Mio. USDT am Tag).
2. Für jeden Coin die Tageskerzen laden und die **Trendampel** rechnen: Tagesschluss über dem
   50-Tage-Schnitt = grün. Das ist dieselbe Regel wie bei den Haupt-Coins ([trendampel.md](trendampel.md)).
3. Nur grüne Coins bekommen einen **Score (0–100)**: „Rücksetzer im Aufwärtstrend“, je zur Hälfte
   *nah am 50-Tage-Schnitt* und *in den letzten 30 Tagen nicht schon stärker als BTC gelaufen*.
4. Zusätzlich angezeigt: **Marktbreite** (Anteil der Coins mit grüner Ampel), **BTC-Ampel**, Volumen-Schub,
   „frisch grün“, 20-Tage-Hoch und der Anteil, den die Trendampel nach der Schwankung empfehlen würde.

Neu gescannt wird alle 4 Stunden (Einstellung `scanner:` in `config.yaml`). Mit **＋ Chart** kommt ein
Coin mit einem Klick als Kachel zu den Charts. Im Terminal: `python -m signalbot scanner`.

## Historischer Test

`scripts/scanner_test.py`, gelaufen über GitHub Actions (Workflow „Coin-Scanner-Test“), Ergebnis:
[results/scanner/scanner-test.md](../results/scanner/scanner-test.md).

- Coinbase, alle USD-Paare, 225 Wochen von 06/2022 bis 09/2026, 404 Coins.
- Jede Woche die 100 Coins mit dem höchsten 30-Tage-Volumen *zu diesem Zeitpunkt* bewertet, genau wie
  live und ohne Blick in die Zukunft. Danach gemessen: Rendite der nächsten 7 und 28 Tage nach 0,2 % Gebühr.
- Coins, die heute nicht mehr gelistet sind, fehlen. Das macht alle Altcoin-Ergebnisse eher zu gut.

**Erster Entwurf scheiterte deutlich.** Der ursprüngliche Score (40 % Stärke gegenüber BTC, 30 %
Volumen-Schub, 15 % frisch grün, 15 % nah am Schnitt) wählte genau die falschen Coins: Top 5 im Schnitt
−0,8 % pro Woche, jede Woche gekauft −99 %. Die Bausteine einzeln zeigen warum: Coins, die schon stark
gelaufen waren oder weit über dem 50-Tage-Schnitt standen, fielen danach im Schnitt zurück
(Rangkorrelation −0,13 bzw. −0,16, t-Wert −8,6 bzw. −9,4, also kein Zufall). Volumen-Schub war ebenfalls
eher schlecht (−0,07).

**Deshalb ist der Score umgedreht** („Rücksetzer“). Geprüft wurde die Umkehr getrennt für 2022–2024 und
für 2025–2026:

| Jede Woche gekauft, 7 Tage gehalten | bis 2024 | ab 2025 | Max. Rückgang ab 2025 |
|---|---:|---:|---:|
| Alle Coins mit grüner Ampel | −77 % | −90 % | −94 % |
| Alter Schwung-Score, Top 5 | −88 % | −94 % | −97 % |
| **Scanner Top 5 (Rücksetzer)** | −60 % | −64 % | −84 % |
| **Scanner Top 5, nur wenn BTC-Ampel grün** | −40 % | −5 % | −65 % |
| Nur BTC | +149 % | −32 % | −55 % |
| BTC nur bei grüner Ampel | +51 % | +9 % | −30 % |

## Was das heißt

- Der neue Score ist **besser als der alte und besser als „alle grünen Coins“**, in beiden Zeiträumen.
  Er ist aber **nicht profitabel**: Auch die beste Variante (nur kaufen, wenn die BTC-Ampel grün ist) lag
  unter BTC mit Trendampel und hatte deutlich größere Rückgänge.
- Altcoins außerhalb der großen haben in diesen vier Jahren als Gruppe massiv gegen BTC verloren.
  Wer „vielversprechende Coins“ sucht, kauft im Schnitt Verlierer.
- Der Scanner ist darum eine **Beobachtungsliste**: Er zeigt, welche Coins gerade in einem Aufwärtstrend
  sind und wie breit der Markt mitläuft. Wenn die BTC-Ampel auf RAUS steht, warnt er ausdrücklich.
- Die Marktbreite ist als Stimmungsbild nützlich, wurde aber nicht als eigene Regel getestet.
