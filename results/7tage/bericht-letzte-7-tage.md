# Strategien in den letzten 7 Tagen (15.10.–22.10.2026)

Daten: Coinbase (USD), BTC, ETH, SOL, XRP, ONDO, 1h und 4h. Gleiche Regeln wie im 1-Jahres-Backtest: Einstieg zur nächsten Kerze, Treffer = Ziel 1 vor dem Stop, 0,1 % Gebühr pro Seite. R = dein Risiko pro Trade.

| Strategie | Signale | Treffer | Verloren | Ergebnis (abgeschlossen) | Noch offen |
|---|---|---|---|---|---|
| Liquiditäts-Sweep | 2 | 1 | 1 | +0,05 R | – |
| Supertrend-Wechsel | 6 | 1 | 0 (2× Zeitablauf) | −0,09 R | 3 (zusammen −0,81 R) |
| MACD-Kreuzung | 3 | 1 | 2 | −0,79 R | – |
| RSI-Rücksetzer | 2 | 0 | 1 | −1,09 R | 1 (+0,80 R) |
| Score-Modell | 6 | 2 | 4 | −2,00 R | – |
| Bollinger-Squeeze | 3 | 0 | 3 | −3,55 R | – |
| Donchian-Ausbruch | 10 | 0 | 9 | −10,32 R | 1 (−0,09 R) |
| Fibonacci Golden Pocket | 0 | – | – | – | – |
| **Alle** | **32** | **5** | **20** | **−17,8 R** | **5** |

Je Coin (abgeschlossen): BTC −9,6 R, ONDO −8,5 R, XRP −0,9 R. ETH und SOL: kein einziges Signal (Tagestrend passte nicht).

## Alle Signale

| Zeit (UTC) | Strategie | Coin | Zeitebene | Richtung | Ergebnis |
|---|---|---|---|---|---|
| 15.10 15:00 | Score | BTC | 1h | Long | −1,16 R |
| 15.10 15:00 | Donchian | BTC | 1h | Long | −1,12 R |
| 15.10 15:00 | Supertrend | BTC | 1h | Long | Zeitablauf −0,54 R |
| 15.10 15:00 | Score | ONDO | 1h | Long | −1,07 R |
| 15.10 15:00 | Donchian | ONDO | 1h | Long | −1,05 R |
| 15.10 15:00 | Supertrend | ONDO | 1h | Long | Zeitablauf −0,93 R |
| 15.10 16:00 | MACD | ONDO | 4h | Long | −1,04 R |
| 16.10 03:00 | Sweep | BTC | 1h | Long | −1,29 R |
| 16.10 04:00 | MACD | BTC | 4h | Long | −1,11 R |
| 16.10 11:00 | Squeeze | BTC | 1h | Long | −1,24 R |
| 18.10 03:00 | Donchian | BTC | 1h | Long | −1,28 R |
| 18.10 20:00 | MACD | BTC | 4h | Long | **+1,36 R** |
| 18.10 22:00 | Supertrend | BTC | 1h | Long | **+1,38 R** |
| 19.10 00:00 | Donchian | BTC | 1h | Long | −1,23 R |
| 20.10 08:00 | Squeeze | XRP | 1h | Short | −1,20 R |
| 20.10 12:00 | Score | BTC | 4h | Long | **+1,37 R** |
| 20.10 13:00 | Score | BTC | 1h | Long | **+1,22 R** |
| 20.10 14:00 | Donchian | BTC | 1h | Long | −1,18 R |
| 20.10 15:00 | RSI | XRP | 1h | Short | −1,09 R |
| 21.10 04:00 | Supertrend | ONDO | 4h | Long | offen (−0,57 R) |
| 21.10 08:00 | Donchian | BTC | 4h | Long | −1,11 R |
| 21.10 08:00 | Supertrend | BTC | 4h | Long | offen (−0,74 R) |
| 21.10 12:00 | Donchian | ONDO | 1h | Long | −1,09 R |
| 21.10 12:00 | Squeeze | ONDO | 1h | Long | −1,11 R |
| 21.10 12:00 | Donchian | ONDO | 4h | Long | −1,04 R |
| 21.10 13:00 | Donchian | BTC | 1h | Long | −1,22 R |
| 21.10 14:00 | Score | BTC | 1h | Long | −1,26 R |
| 21.10 14:00 | Score | ONDO | 1h | Long | −1,11 R |
| 21.10 18:00 | Sweep | XRP | 1h | Short | **+1,35 R** |
| 21.10 20:00 | RSI | XRP | 4h | Short | offen (+0,80 R) |
| 22.10 01:00 | Supertrend | XRP | 1h | Short | offen (+0,50 R) |
| 22.10 08:00 | Donchian | XRP | 1h | Short | offen (−0,09 R) |

## Einordnung

- 7 Tage mit 27 abgeschlossenen Trades sind statistisch kaum aussagekräftig. Die Woche war seitwärts mit vielen Fehlausbrüchen, genau das Umfeld, in dem Ausbruchs-Strategien (Donchian, Squeeze) verlieren.
- Das passt zum 1-Jahres-Backtest: Donchian und Squeeze lagen dort schon im Minus, und keine Strategie war zuverlässig profitabel.
- Die im Programm standardmäßig eingeschalteten Strategien (RSI-Rücksetzer und Fibonacci) hatten diese Woche nur 2 Signale: ein Verlust (−1,09 R) und ein offener Trade im Plus (+0,80 R).
