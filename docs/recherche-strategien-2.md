# Strategie-Recherche, Runde 2 (Stand 22.10.2026)

## Kurz gesagt

Eine Strategie, die Kauf- und Verkaufsbefehle erzeugt **ohne Geld zu verlieren, gibt es nicht** – weder im Netz noch in der Forschung. Wer so etwas verspricht, hat entweder überangepasst, rechnet ohne Gebühren oder verkauft etwas. Seriöse Studien finden bei Krypto nur **eine robuste Familie: Trendfolge** (Kurs über Durchschnitt oder neues Hoch → halten, sonst raus). Sie verliert in Seitwärtsphasen regelmäßig kleine Beträge, vermeidet aber den Großteil der Abstürze.

Neu getestet wurden die vier am besten belegten Kandidaten aus der Recherche. Ergebnis: **Ein Kandidat („MAX“, kaufen am 10/20-Tage-Hoch, 1 Tag halten) sah im Prüfjahr gut aus, ist aber zerbrechlich** und kommt deshalb nur als Beobachtungs-Signal in Frage, nicht als Ersatz für die Trendampel.

## Was die Forschung sagt (mit Quellen)

| Ansatz | Beleg | Einschätzung |
|---|---|---|
| **Trendfolge / Zeitreihen-Momentum** | 100+ Jahre über viele Märkte ([AQR, Hurst/Ooi/Pedersen](https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing)); Bitcoin mit 5–100-Tage-Schnitt ([Detzel u. a., via CXO](https://www.cxoadvisory.com/currency-trading/timing-bitcoin-with-smas/)); Krypto-Faktoren Markt/Größe/Momentum ([Liu/Tsyvinski/Wu](https://alphaarchitect.com/factors-investing-in-cryptocurrency/)) | Bestbelegte Familie. Bei uns: Trendampel (SMA50) hält. |
| **Donchian-Ensemble** (Ausbruch über mehrere Zeiträume, nachgezogener Stopp, Schwankungssteuerung) | [Zarattini/Pagani/Barbon 2025 „Catching Crypto Trends“](https://abarbon.com/papers/catching-crypto-trends): Sharpe > 1,5 nach Gebühren, Top-20-Rotation ([Regeln via CXO](https://www.cxoadvisory.com/technical-trading/crypto-asset-trend-following-strategies/)) | Neu getestet → fällt bei uns im Prüfjahr auf ±0. |
| **MAX/MIN** (kaufen am x-Tage-Hoch bzw. -Tief) | [Quantpedia 2024](https://quantpedia.com/revisiting-trend-following-and-mean-reversion-strategies-in-bitcoin/): MAX hält 2022–2024 außerhalb der Stichprobe, MIN nicht | Neu getestet → MAX 1 Tag positiv, aber empfindlich. |
| **Niedrig-Volatilität** (die ruhigsten Coins halten) | [Kaya/Mostowfi 2022](https://digitalcollection.zhaw.ch/bitstream/11475/23853/3/2022_Kaya-Mostowfi_Low-volatility-strategies-cryptocurrencies_frl.pdf), nur 2017–2021 | Neu getestet → durchgefallen. |
| **Basis-/Funding-Carry** (Spot kaufen + Future/Perp short) | [BIS Working Paper 1087](https://www.bis.org/publ/work1087.pdf): ~10 %/Jahr, Sharpe ~0,6 vor Kosten, aber Liquidations-Risiko; 2025 laut [BitMEX](https://www.bitmex.com/blog/site-announcement/state-of-crypto-perps-2025) weitgehend „abgegrast“ | Einziger Ansatz ohne Kursrichtung, braucht aber Börsenkonto mit Futures, Margin und Überwachung. Nicht mit Kerzendaten testbar. Für dich derzeit nicht passend. |
| **Kalender-Effekte** (Wochentag, Uhrzeit, Monatswechsel) | [Baur u. a. via Quantpedia](https://quantpedia.com/are-there-any-simple-calendar-effects-in-bitcoin-market/): „keine beständigen Muster“; Uhrzeit-Effekt bei uns schon durchgefallen | Nicht weiter verfolgen. |
| **On-Chain (MVRV usw.)** | [K33](https://k33.com/research/archive/articles/using-market-value-to-realized-value-to-estimate-market-tops-and-bottoms): nur 4 Zyklen seit 2013, Schwellen im Nachhinein gewählt | Höchstens als grobes Zyklus-Barometer, kein Signalgeber. |
| **„KI-Strategien“ mit Sharpe 2–3** | z. B. [AdaptiveTrend, arXiv 2026](https://arxiv.org/abs/2602.11708v1) | Unabhängig nicht bestätigt. Laut [Harvey/Liu „Backtesting“](https://www.man.com/insights/backtesting) muss man Backtest-Ergebnisse stark abwerten, je mehr Varianten probiert wurden. |

## Eigener Nachtest (gleiche Methode wie Runde 1)

- Daten: Coinbase-Tageskerzen 2021 bis 10.10.2026 (Branch `history`), 10 Coins bzw. Fokus-5 (BTC, ETH, SOL, XRP, ONDO).
- Entwicklung bis 10.10.2025, Prüfjahr 11.10.2025–10.10.2026. Parameter **nicht optimiert**, sondern aus den Studien übernommen.
- Gebühr 0,1 % und 0,25 % pro Seite. Skript `scripts/research2.py`, Zahlen in `results/research2_results.json`.

### Fokus-5, 0,1 % Gebühr

| Regel | Entwicklung CAGR / Sharpe / MaxDD | Prüfjahr CAGR / Sharpe / MaxDD | Wechsel pro Coin/Jahr |
|---|---|---|---|
| Kaufen & Halten | +30 % / 0,73 / −85 % | −32 % / −0,36 / −59 % | – |
| **Trendampel (SMA50 + Größe)** | +26 % / 0,95 / −44 % | **+13 % / 0,60 / −18 %** | 23 |
| Donchian-Ensemble (Zarattini) | +10 % / 1,05 / −11 % | +1 % / 0,14 / −5 % | 28 |
| **MAX 10 Tage, 1 Tag halten** | +19 % / 0,86 / −27 % | **+24 % / 1,20 / −9 %** | 62 |
| **MAX 20 Tage, 1 Tag halten** | +23 % / 1,13 / −23 % | **+14 % / 0,93 / −7 %** | 42 |
| MAX 10 Tage, 5 Tage halten | +17 % / 0,59 / −62 % | −4 % / −0,01 / −25 % | 32 |
| Niedrig-Vol 3 aus 10 (alle Coins) | +31 % / 0,78 / −66 % | −32 % / −0,52 / −57 % | – |
| Niedrig-Vol + SMA50 (alle Coins) | +20 % / 0,69 / −44 % | +3 % / 0,24 / −22 % | – |

### Jahr für Jahr (Fokus-5, 0,1 %)

| Jahr (11.10.–10.10.) | Trendampel | MAX 10/1 | MAX 20/1 | Kaufen & Halten |
|---|---|---|---|---|
| 2021/22 | −26 % | −13 % | −4 % | −70 % |
| 2022/23 | +13 % | −5 % | −1 % | +14 % |
| 2023/24 | +89 % | +57 % | +58 % | +183 % |
| 2024/25 | +55 % | +39 % | +53 % | +101 % |
| 2025/26 | +13 % | +24 % | +14 % | −32 % |

## Ehrliches Urteil

1. **Trendampel bleibt die Basis.** Sie hält auch in diesem Nachtest, ist simpel und deckt sich mit der Forschung.
2. **MAX (am 20-Tage-Hoch kaufen, am nächsten Tag neu prüfen) ist der einzige neue Kandidat mit Potenzial**, aber mit klaren Warnzeichen:
   - Hält man 5 statt 1 Tag, kippt das Ergebnis ins Minus. Der Vorteil hängt also an einem sehr kurzen Effekt.
   - Bei 0,25 % Gebühr schrumpft die Entwicklungsphase von +19 % auf +4–8 % pro Jahr (alle 10 Coins).
   - 2021/22 und 2022/23 leicht negativ; 40–60 Wechsel pro Coin und Jahr bedeuten viel manuelles Handeln.
   - Ich habe das Prüfjahr jetzt gesehen; es ist damit nicht mehr „unberührt“.
   - Vorschlag: als **zusätzliches Hinweis-Signal** im Programm anzeigen und ein paar Monate mitschreiben, bevor echtes Geld daran hängt. Die 20-Tage-Variante ist ruhiger (weniger Wechsel, kleinerer Rückgang).
3. **Donchian-Ensemble, Niedrig-Volatilität, Kalender, On-Chain-Schwellen:** kein Vorteil bei uns bzw. zu dünn belegt.
4. **Verluste ganz vermeiden geht nicht.** Was realistisch ist: Abstürze begrenzen (Trendampel: −18 % statt −59 % im Prüfjahr), kleine Positionen, günstige Börse, und keinen Hebel.

## Nachtrag: Jengs Liste der „bewährten Ansätze“ (22.10.2026)

| Ansatz | Schon getestet als | Ergebnis |
|---|---|---|
| Trendfolge mit gleitenden Durchschnitten | SMA-Filter 20–200, EMA-Kreuze, Trendampel | Nur SMA50-Trendampel hält. |
| Golden Cross 50/200 | EMA 50/200 (Runde 1), **SMA 50/200 neu** | Durchgefallen (Prüfjahr −7 bis −10 %), nur ~2 Wechsel/Jahr, kommt zu spät. |
| Breakout | Donchian 20/30/50/55 Tage, Donchian-Ensemble, Bollinger-Squeeze | Kein Vorteil nach Gebühren. |
| Breakout mit Retest (Pullback) | **neu** (20 und 50 Tage) | In der Entwicklung gut (+23 %), im Prüfjahr −2 bis −7 %. Durchgefallen. |
| Pullback im Trend | RSI-Rücksetzer, Fib Golden Pocket, Dip-Kauf | Knapp ±0 nach Gebühren. |
| Price Action / Smart Money / Liquidität | Liquiditäts-Sweep, Liquiditätszonen | Sweep war die schlechteste Strategie (−0,32 R pro Trade). |
| Range-Trading | **neu** (unteres Fünftel der 20/30-Tage-Spanne kaufen, oberes verkaufen, nur bei ADX < 20/25) | Entwicklung −2 bis −7 %/Jahr, Prüfjahr +4 bis +12 %. Funktioniert nur, wenn der Markt wirklich seitwärts läuft; die Entwicklungsjahre waren trendig. Nicht verlässlich. |
| Momentum | Momentum-Rotation, Zeitreihen-Momentum 14–90 Tage, MAX | Rotation durchgefallen; MAX (20-Tage-Hoch, 1 Tag) einziger wackeliger Kandidat. |

Neue Zahlen: `scripts/research3.py`, `results/research3_results.json` (Fokus-5 und alle 10 Coins, 0,1 % und 0,25 % Gebühr).

Fazit: Die Liste beschreibt die üblichen Lehrbuch-Ansätze. Getestet auf fünf Jahren Krypto-Tagesdaten hält keiner davon besser als die einfache Trendampel. Verlustfrei ist keiner.

## Nachtrag 2: Smart-Money-Bausteine (Order Blocks, Fair Value Gaps)

Feste Regeln, nur Long, Fokus-5, Tageskerzen und 4h-Kerzen (`scripts/research4.py`, `results/research4_results.json`):

- **Fair Value Gap:** Tief einer Kerze liegt über dem Hoch der vorletzten Kerze → Lücke. Kauf, wenn der Kurs später in die Lücke zurückkommt und nicht darunter schließt.
- **Order Block:** Schluss über dem 10-Kerzen-Hoch (Strukturbruch); die letzte rote Kerze davor ist der Order Block. Kauf beim Rücklauf in diese Zone.
- Stopp: Schluss unter der Zone. Ziel 2 R (eine Variante 3 R), spätestens nach 30 Tages- bzw. 90 4h-Kerzen raus. Varianten mit Trendfilter (nur über dem 50-Tage-Schnitt).

| Regel (0,1 % Gebühr) | Tag: Entwicklung / Prüfjahr | 4h: Entwicklung / Prüfjahr | Trades pro Coin/Jahr (Tag / 4h) |
|---|---|---|---|
| FVG | −8 % / −27 % | +17 % / −36 % | 19 / 103 |
| FVG + Trendfilter | −3 % / −9 % | +17 % / −7 % | 12 / 52 |
| Order Block | −8 % / −6 % | +2 % / −23 % | 10 / 62 |
| Order Block + Trendfilter | −3 % / −4 % | +13 % / −12 % | 7 / 33 |
| Order Block + Trend, Ziel 3 R | −2 % / −2 % | +9 % / −12 % | 6 / 28 |
| Zum Vergleich: Trendampel | +26 % / +13 % | | ~23 Wechsel |

Bei 0,25 % Gebühr wird alles noch deutlich schlechter (4h-FVG im Prüfjahr −52 %).

Fazit: Als feste Regeln verlieren Order Blocks und Fair Value Gaps im Prüfjahr in **jeder** Variante. Auf 4h sahen sie in den Bullenjahren gut aus, aber nur, weil der Markt damals ohnehin stieg; ohne Rückenwind bleiben die Gebühren und Fehlsignale übrig. Nicht ins Programm übernehmen.
