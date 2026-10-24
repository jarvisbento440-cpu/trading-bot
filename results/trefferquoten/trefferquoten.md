# Echte Trefferquoten je Setup-Score

Grundlage: Coinbase, 10 Coins (ADA, AVAX, BTC, DOGE, ETH, LINK, LTC, ONDO, SOL, XRP), 1h + 4h, Signale vom 09.01.2021 bis 15.10.2026. Treffer = Ziel 1 vor dem Stop, Einstieg zum nächsten Eröffnungskurs, 0,1 % Gebühr pro Seite. Prüfjahr = alles ab 11.10.2025.

Jede Zelle: Trefferquote (Zahl der Trades). ✔ = mindestens 30 Trades und auch die vorsichtige Untergrenze der 90-%-Spanne liegt über der Gewinnschwelle.

## Alle Strategien zusammen

| Score | Trades | Trefferquote | 90-%-Spanne | Gewinnschwelle | Ø R | Prüfjahr |
|---|---:|---:|---:|---:|---:|---:|
| 0–39 | 11652 | 38 % | 37 %–39 % | 46 % | -0,19 | 42 % (2543) |
| 40–59 | 5815 | 34 % | 33 %–35 % | 38 % | -0,11 | 36 % (1330) |
| 60–69 | 6275 | 38 % | 37 %–39 % | 40 % | -0,07 | 36 % (1318) |
| 70–79 | 11854 | 37 % | 37 %–38 % | 42 % | -0,10 | 37 % (2548) |
| 80–100 | 9728 | 38 % | 37 %–38 % | 39 % | -0,04 | 36 % (2028) |
| alle | 45324 | 37 % | 37 %–38 % | 42 % | -0,11 | 38 % (9767) |

## Je Strategie und Score-Stufe

| Strategie | 0–39 | 40–59 | 60–69 | 70–79 | 80–100 | alle | Gewinnschwelle |
|---|---:|---:|---:|---:|---:|---:|---:|
| Score-Modell | – | – | 40 % (3666) | 40 % (6867) | 43 % (3808) | 41 % (14341) | 45 % |
| Donchian-Ausbruch | 41 % (58) | 31 % (1789) | 33 % (1368) | 31 % (2210) | 32 % (3294) | 32 % (8719) | 33 % |
| Supertrend-Wechsel | 29 % (709) | 28 % (1239) | 29 % (485) | 28 % (888) | 28 % (1092) | 28 % (4413) | 30 % |
| MACD-Kreuzung | 41 % (2548) | 39 % (1245) | 43 % (246) | 38 % (1002) | 45 % (328) | 40 % (5369) | 45 % |
| RSI-Rücksetzer | 38 % (840) | 25 % (4) | – | 0 % (2) | – | 38 % (846) | 42 % |
| Bollinger-Squeeze | 39 % (347) | 43 % (742) | 41 % (334) | 39 % (698) | 43 % (1127) | 41 % (3248) | 45 % |
| Fibonacci Golden Pocket | 42 % (159) | 42 % (71) | 79 % (14) | 100 % (1) | 100 % (2) | 45 % (247) | 44 % |
| Liquiditäts-Sweep | 38 % (6991) | 36 % (725) | 30 % (162) | 40 % (186) | 27 % (77) | 38 % (8141) | 48 % |

## Prüfjahr je Strategie und Score-Stufe

Dieselbe Tabelle nur für das letzte Jahr. Hält eine Stufe hier nicht, war sie Zufall.

| Strategie | 0–39 | 40–59 | 60–69 | 70–79 | 80–100 | alle |
|---|---:|---:|---:|---:|---:|---:|
| Score-Modell | – | – | 39 % (775) | 40 % (1487) | 40 % (786) | 40 % (3048) |
| Donchian-Ausbruch | 56 % (16) | 35 % (414) | 31 % (259) | 31 % (457) | 31 % (685) | 32 % (1831) |
| Supertrend-Wechsel | 28 % (197) | 29 % (302) | 22 % (104) | 27 % (192) | 31 % (232) | 28 % (1027) |
| MACD-Kreuzung | 44 % (594) | 38 % (276) | 33 % (63) | 38 % (231) | 43 % (61) | 41 % (1225) |
| RSI-Rücksetzer | 44 % (181) | 0 % (1) | – | 0 % (1) | – | 43 % (183) |
| Bollinger-Squeeze | 40 % (85) | 50 % (163) | 40 % (72) | 43 % (143) | 38 % (240) | 42 % (703) |
| Fibonacci Golden Pocket | 43 % (28) | 26 % (19) | 100 % (3) | – | 100 % (1) | 41 % (51) |
| Liquiditäts-Sweep | 42 % (1442) | 37 % (155) | 26 % (42) | 46 % (37) | 48 % (23) | 41 % (1699) |

## So liest du das

- **Trefferquote** = Anteil der Signale, die Ziel 1 vor dem Stop erreicht haben.
- **Spanne**: Bei wenigen Trades ist die Zahl ungenau. Die echte Quote liegt mit 90 % Sicherheit in dieser Spanne.
- **Gewinnschwelle**: So hoch muss die Trefferquote mindestens sein, damit nach Gebühren Gewinn bleibt (hängt vom Chance/Risiko der Strategie ab). Eine Trefferquote von 45 % kann gut sein (Ziel weit weg) oder schlecht (Ziel nah dran).
- Im Signal steht immer die genaueste Gruppe mit mindestens 30 Trades (Strategie + Zeitebene + Richtung + Score-Stufe, sonst gröber).
- Vergangene Trefferquoten sind keine Garantie für die Zukunft.
