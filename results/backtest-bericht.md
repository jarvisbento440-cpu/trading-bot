# Backtest 365 Tage (Stand 11.10.2026)

Daten: coinbaseexchange, BTC/USD, ETH/USD, SOL/USD, XRP/USD, ONDO/USD, Zeitebenen 1h, 4h. Treffer = Ziel 1 vor dem Stop. Einstieg zum nächsten Eröffnungskurs, 0,1 % Gebühr pro Seite.

| Strategie | Trades | Trefferquote | Ø Ergebnis (R) | Summe (R) | Profit-Faktor | Max. Drawdown (R) |
|---|---:|---:|---:|---:|---:|---:|
| RSI-Rücksetzer | 94 | 43 % | 0,04 | 3,7 | 1,07 | 15,3 |
| Fibonacci Golden Pocket | 24 | 46 % | 0,03 | 0,7 | 1,05 | 3,1 |
| Supertrend-Wechsel | 492 | 28 % | -0,03 | -16,3 | 0,94 | 23,4 |
| Donchian-Ausbruch | 871 | 32 % | -0,05 | -45,0 | 0,92 | 71,3 |
| Score-Modell | 734 | 42 % | -0,09 | -65,1 | 0,86 | 70,9 |
| MACD-Kreuzung | 579 | 42 % | -0,10 | -60,5 | 0,84 | 71,5 |
| Bollinger-Squeeze | 334 | 40 % | -0,14 | -45,3 | 0,80 | 47,8 |
| Liquiditäts-Sweep | 847 | 38 % | -0,32 | -268,0 | 0,60 | 270,5 |

**Alle zusammen:** 3975 Trades, Trefferquote 37 %, Ø -0,12 R pro Trade.

## Score-Modell: Trefferquote je Score

| Score | Trades | Trefferquote | Ø R |
|---|---:|---:|---:|
| 50–59 | 1566 | 40 % | -0,14 |
| 60–69 | 422 | 38 % | -0,17 |
| 70–79 | 324 | 41 % | -0,11 |
| 80–100 | 176 | 44 % | -0,04 |

## Je Coin und Zeitebene

**RSI-Rücksetzer:** BTC 37 % (19), ETH 29 % (24), SOL 50 % (16), XRP 52 % (23), ONDO 50 % (12) · 1h 39 % (67), 4h 52 % (27)

**Fibonacci Golden Pocket:** BTC 29 % (7), ETH 50 % (4), SOL 67 % (3), XRP 60 % (5), ONDO 40 % (5) · 1h 47 % (19), 4h 40 % (5)

**Supertrend-Wechsel:** BTC 29 % (105), ETH 33 % (98), SOL 25 % (89), XRP 29 % (101), ONDO 27 % (99) · 1h 29 % (394), 4h 24 % (98)

**Donchian-Ausbruch:** BTC 32 % (182), ETH 34 % (161), SOL 29 % (175), XRP 35 % (170), ONDO 31 % (183) · 1h 34 % (676), 4h 27 % (195)

**Score-Modell:** BTC 44 % (160), ETH 40 % (156), SOL 40 % (143), XRP 43 % (141), ONDO 42 % (134) · 1h 43 % (581), 4h 38 % (153)

**MACD-Kreuzung:** BTC 36 % (109), ETH 39 % (120), SOL 43 % (118), XRP 48 % (122), ONDO 44 % (110) · 1h 40 % (442), 4h 47 % (137)

**Bollinger-Squeeze:** BTC 41 % (63), ETH 41 % (64), SOL 32 % (65), XRP 53 % (77), ONDO 31 % (65) · 1h 42 % (245), 4h 36 % (89)

**Liquiditäts-Sweep:** BTC 33 % (172), ETH 41 % (163), SOL 43 % (184), XRP 35 % (160), ONDO 37 % (168) · 1h 38 % (700), 4h 39 % (147)

## So liest du das

- **R** ist das Risiko pro Trade (Abstand Einstieg–Stop). +1,5 R heißt: 1,5-mal so viel gewonnen wie riskiert.
- **Ø Ergebnis** über 0 bedeutet: Die Strategie hätte nach Gebühren Geld verdient. Die Trefferquote allein sagt das nicht, weil Gewinne größer als Verluste sein können.
- **Profit-Faktor** = Summe Gewinne / Summe Verluste. Über 1,2 ist brauchbar, unter 1 verliert Geld.
- Vergangene Ergebnisse sind keine Garantie. Ein Jahr ist eine kurze Zeit, und Märkte ändern sich.
