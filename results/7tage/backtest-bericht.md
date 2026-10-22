# Backtest 7 Tage (Stand 22.10.2026)

Daten: coinbaseexchange, BTC/USD, ETH/USD, SOL/USD, XRP/USD, ONDO/USD, Zeitebenen 1h, 4h. Treffer = Ziel 1 vor dem Stop. Einstieg zum nächsten Eröffnungskurs, 0,1 % Gebühr pro Seite.

| Strategie | Trades | Trefferquote | Ø Ergebnis (R) | Summe (R) | Profit-Faktor | Max. Drawdown (R) |
|---|---:|---:|---:|---:|---:|---:|
| Liquiditäts-Sweep | 2 | 50 % | 0,03 | 0,1 | 1,04 | 1,3 |
| Supertrend-Wechsel | 3 | 33 % | -0,03 | -0,1 | 0,94 | 0,9 |
| MACD-Kreuzung | 3 | 33 % | -0,26 | -0,8 | 0,63 | 1,1 |
| Score-Modell | 6 | 33 % | -0,33 | -2,0 | 0,56 | 2,2 |
| RSI-Rücksetzer | 1 | 0 % | -1,09 | -1,1 | 0,00 | 1,1 |
| Donchian-Ausbruch | 9 | 0 % | -1,15 | -10,3 | 0,00 | 10,3 |
| Bollinger-Squeeze | 3 | 0 % | -1,18 | -3,6 | 0,00 | 3,6 |
| Fibonacci Golden Pocket | 0 | – | – | – | – | – |

**Alle zusammen:** 27 Trades, Trefferquote 19 %, Ø -0,66 R pro Trade.

## Score-Modell: Trefferquote je Score

| Score | Trades | Trefferquote | Ø R |
|---|---:|---:|---:|
| 50–59 | 7 | 29 % | -0,51 |
| 60–69 | 6 | 17 % | -0,76 |
| 70–79 | 3 | 67 % | 0,50 |
| 80–100 | 0 | – | – |

## Je Coin und Zeitebene

**Liquiditäts-Sweep:** BTC 0 % (1), ETH – (0), SOL – (0), XRP 100 % (1), ONDO – (0) · 1h 50 % (2), 4h – (0)

**Supertrend-Wechsel:** BTC 50 % (2), ETH – (0), SOL – (0), XRP – (0), ONDO 0 % (1) · 1h 33 % (3), 4h – (0)

**MACD-Kreuzung:** BTC 50 % (2), ETH – (0), SOL – (0), XRP – (0), ONDO 0 % (1) · 1h – (0), 4h 33 % (3)

**Score-Modell:** BTC 50 % (4), ETH – (0), SOL – (0), XRP – (0), ONDO 0 % (2) · 1h 20 % (5), 4h 100 % (1)

**RSI-Rücksetzer:** BTC – (0), ETH – (0), SOL – (0), XRP 0 % (1), ONDO – (0) · 1h 0 % (1), 4h – (0)

**Donchian-Ausbruch:** BTC 0 % (6), ETH – (0), SOL – (0), XRP – (0), ONDO 0 % (3) · 1h 0 % (7), 4h 0 % (2)

**Bollinger-Squeeze:** BTC 0 % (1), ETH – (0), SOL – (0), XRP 0 % (1), ONDO 0 % (1) · 1h 0 % (3), 4h – (0)

**Fibonacci Golden Pocket:** BTC – (0), ETH – (0), SOL – (0), XRP – (0), ONDO – (0) · 1h – (0), 4h – (0)

## So liest du das

- **R** ist das Risiko pro Trade (Abstand Einstieg–Stop). +1,5 R heißt: 1,5-mal so viel gewonnen wie riskiert.
- **Ø Ergebnis** über 0 bedeutet: Die Strategie hätte nach Gebühren Geld verdient. Die Trefferquote allein sagt das nicht, weil Gewinne größer als Verluste sein können.
- **Profit-Faktor** = Summe Gewinne / Summe Verluste. Über 1,2 ist brauchbar, unter 1 verliert Geld.
- Vergangene Ergebnisse sind keine Garantie. Ein Jahr ist eine kurze Zeit, und Märkte ändern sich.
