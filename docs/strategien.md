# Trading-Strategien im Bot

Stand: Oktober 2026. Alle Strategien handeln nur **in Richtung des Tages-Trends** (Long im Aufwärtstrend, Short im Abwärtstrend). Jede liefert Einstieg, Stop und zwei Ziele. Im Programm schaltest du sie unter **„Strategien ▾“** an und aus; in `config.yaml` (`strategies:`) legst du fest, welche Telegram-Signale schicken.

## Was die Forschung sagt (kurz)

- **Trendfolge/Momentum** ist die am besten belegte Idee bei Krypto: Kurse, die stark steigen, steigen oft eine Weile weiter. Das gilt eher für Tage und Wochen als für Stunden ([Quantpedia](https://quantpedia.com/trend-following-and-mean-reversion-in-bitcoin/), [Vilnius University 2025](https://www.journals.vu.lt/BATP/en/article/view/44540), [tradingstrategy.ai](https://tradingstrategy.ai/docs/learn/trend-following.html)).
- **Mean Reversion** (Rückkehr zum Mittelwert) funktioniert bei Bitcoin vor allem nach starken Abverkäufen, weniger an Hochs ([Quantpedia](https://quantpedia.com/trend-following-and-mean-reversion-in-bitcoin/), [Theseus 2025](https://www.theseus.fi/handle/10024/902903)).
- **Klassische Indikator-Regeln** (RSI, MACD, Bollinger) bringen nach Gebühren oft keinen Vorteil. Ein Test von 13 bekannten Strategien über 6 Jahre fand bei keiner einen stabilen Vorteil ([dev.to](https://dev.to/tessen/we-graded-13-famous-trading-strategies-on-6-years-of-data-all-13-failed-26o4)).
- **Liquiditäts-Konzepte** (Smart Money Concepts): Über Swing-Hochs und unter Swing-Tiefs liegen viele Stop-Orders. Der Kurs läuft oft dorthin („Sweep“) und dreht dann. Gleiche Hochs/Tiefs („Equal Highs/Lows“) gelten als besonders starke Liquidität ([LuxAlgo: Liquidity Sweep](https://www.luxalgo.com/library/concept/liquidity-sweep/), [LuxAlgo: Equal Highs/Lows](https://www.luxalgo.com/library/concept/equal-highs-lows-as-liquidity.md), [CrossTrade](https://crosstrade.io/learn/price-action/liquidity-sweeps)). Wissenschaftlich ist das kaum untersucht.

## Die 8 eingebauten Strategien

| Kürzel | Strategie | Idee | Stop / Ziel |
|---|---|---|---|
| S | Score-Modell | Punkte für Trend, Ausbruch, Rücksetzer an EMA20, RSI, MACD, Volumen (ab Mindest-Score) | 1,5 ATR / 1,5 R und 2,5 R |
| D | Donchian-Ausbruch | Turtle-Regel: Schluss über 20-Kerzen-Hoch (Short: unter 20-Kerzen-Tief) | 2 ATR / 2 R und 3 R |
| T | Supertrend-Wechsel | Supertrend (10, 3) dreht in Trendrichtung | knapp hinter der Supertrend-Linie / 1,5 R und 3 R |
| M | MACD-Kreuzung | MACD kreuzt Signallinie unter der Null-Linie (Ende eines Rücksetzers), Kurs über EMA200 | 1,5 ATR / 1,5 R und 3 R |
| R | RSI-Rücksetzer | RSI kommt aus überverkauft (30) zurück, Kurs über EMA200 (Short spiegelbildlich bei 70) | unter dem Kerzentief / 1,5 R und 2,5 R |
| B | Bollinger-Squeeze | Bänder so eng wie selten (unterste 10 %), dann Schluss außerhalb | Bandmitte / 1,5 R und 3 R |
| F | Fibonacci Golden Pocket | Erster Rücksetzer in 61,8–65 % des letzten Impulses mit Umkehrkerze | unter 78,6 % / altes Hoch und 127,2 %-Extension |
| L | Liquiditäts-Sweep | Kurs sticht unter ein Swing-Tief (Stops werden abgeholt) und schließt wieder darüber | unter dem Docht / 1,5 R und nächstes Swing-Hoch |

**R** = Risiko pro Trade (Abstand Einstieg–Stop). **ATR** = durchschnittliche Kerzengröße.

## Liquiditätszonen im Chart

- **Rot (Buy-Side, BSL):** über Swing-Hochs. Dort liegen Stops von Short-Tradern und Kauf-Orders von Ausbruchs-Tradern.
- **Grün (Sell-Side, SSL):** unter Swing-Tiefs. Dort liegen Stops von Long-Tradern.
- **Kräftiger** = mehrfach berührt („2×“, „3×“, Equal Highs/Lows) und damit stärker.
- **Gestrichelt und blass** = schon abgeholt. Die Fläche endet dort, wo der Kurs durchgelaufen ist.
- In den Kacheln siehst du die zwei nächsten offenen Zonen je Seite, im Vollbild alle.

## Backtest

Der Backtest steht im Programm unter **„📊 Backtest“**. Ein Ergebnis mit einem Jahr echter Kurse (Coinbase) liegt im Ordner `results/` bei. Mit „Mit eigenen Daten neu berechnen“ rechnet das Programm mit deinen Binance-Daten neu (dauert ein paar Minuten).

Regeln: Einstieg zum Eröffnungskurs der nächsten Kerze, Treffer = Ziel 1 vor dem Stop, berühren beide dieselbe Kerze zählt es als Verlust, 0,1 % Gebühr pro Seite, maximal 72 (1h) bzw. 42 (4h) Kerzen pro Trade.
