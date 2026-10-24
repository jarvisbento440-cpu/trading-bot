# Echte Trefferquoten und Signal-Tracking

## Was der Bot jetzt bei jedem Signal zeigt

```
Echte Trefferquote: 33 % (Spanne 27 %–39 %, 173 ähnliche Signale seit 2021)
Gewinnschwelle 28 %: knapp darüber, kann Zufall sein (Ø +0,09 R)
Letztes Jahr: 27 % aus 15 Signalen
Setup-Score: 65/100
```

- **Ähnliche Signale** = gleiche Strategie, Zeitebene, Richtung und Score-Stufe (0–39, 40–59, 60–69, 70–79, 80–100).
  Gibt es davon weniger als 30, nimmt der Bot die nächst gröbere Gruppe (ohne Richtung, ohne Zeitebene …).
- **Setup-Score**: Punkte des Score-Modells (Trend, Ausbruch, Rücksetzer, RSI, MACD, Volumen). Jetzt bekommt
  jedes Signal diesen Score, auch wenn es von einer anderen Strategie kommt.
- **Spanne**: Mit 90 % Sicherheit liegt die echte Quote in diesem Bereich. Wenige Trades = breite Spanne.
- **Gewinnschwelle**: Ab dieser Trefferquote bleibt nach Gebühren Gewinn. Sie hängt davon ab, wie weit Ziel und Stop
  entfernt sind. „Sicher darüber“ heißt: auch die Untergrenze der Spanne liegt darüber.

Grundlage: alle 8 Strategien über 10 Coins (BTC, ETH, SOL, XRP, ONDO, ADA, AVAX, LINK, DOGE, LTC), 1h und 4h,
Januar 2021 bis Oktober 2026, rund 45.000 Signale. Gleiche Regeln wie Backtest und Papier-Test (Einstieg zur nächsten
Kerze, Stop vor Ziel, 0,1 % Gebühr pro Seite). Volle Tabelle: [results/trefferquoten/trefferquoten.md](../results/trefferquoten/trefferquoten.md).
Im Programm: Button „📊 Backtest“, ganz unten.

## Was dabei herauskam (ehrlich)

**Der Setup-Score sagt fast nichts über die Trefferquote.** Über alle Strategien liegt sie in jeder Score-Stufe
bei 34–38 %. Beim Score-Modell selbst steigt sie von 40 % (Score 65–79) auf 43 % (80–100), im Prüfjahr aber nicht
mehr (40 % in allen Stufen). Ein hoher Score ist also kein Grund, größer einzusteigen.

| Score | Trades | Trefferquote | Gewinnschwelle | Ø R | Prüfjahr |
|---|---:|---:|---:|---:|---:|
| 0–39 | 11.652 | 38 % | 46 % | −0,19 | 42 % |
| 40–59 | 5.815 | 34 % | 38 % | −0,11 | 36 % |
| 60–69 | 6.275 | 38 % | 40 % | −0,07 | 36 % |
| 70–79 | 11.854 | 37 % | 42 % | −0,10 | 37 % |
| 80–100 | 9.728 | 38 % | 39 % | −0,04 | 36 % |

**Keine Gruppe liegt verlässlich über der Gewinnschwelle.** Von 247 Gruppen mit genug Trades lagen in den Jahren
2021–2025 neun „sicher darüber“. Das ist ungefähr so viel, wie man durch reinen Zufall erwarten würde. Im Prüfjahr
(ab 11.10.2025) hielten davon nur zwei: Supertrend-Wechsel 4h Short (+0,09 R pro Trade) und Supertrend 4h mit
Score 80–100 (+0,39 R, aber nur 43 Trades). Das sind Beobachtungskandidaten, keine Empfehlung.

Das passt zu den früheren Tests: Die Einzelsignale verdienen nach Gebühren kein Geld. Was hilft, ist der
Tages-Trendfilter ([Trendampel](trendampel.md)). Die Trefferquoten sind trotzdem nützlich, weil du bei jedem Signal
siehst, was realistisch zu erwarten ist, statt einer geschätzten Punktzahl.

## Signal-Tracking

Jedes verschickte Signal läuft im Papier-Test als virtueller Trade mit. Sobald es Ziel 1 oder den Stop erreicht
(oder nach 72 Stunden bei 1h bzw. 7 Tagen bei 4h die Zeit abläuft), kommt eine Telegram-Nachricht, zum Beispiel:

```
✅ BTC/USDT LONG (4h) · RSI-Rücksetzer: Ziel 1 erreicht
Einstieg 81.712,43 → 84.498,93, Ergebnis +1,42 R nach Gebühren, nach 28 Std.
Laut Historie treffen solche Signale in 38 % der Fälle.
```

Ergebnisse, die älter als 2 Tage sind (z. B. weil der Rechner aus war), werden nicht mehr einzeln gemeldet,
landen aber im Wochenbericht.

## Wochenbericht

Einmal pro Woche (Standard: Sonntag 18 Uhr, Ortszeit des Rechners) per Telegram und als Datei in `data/berichte/`:

- neue, abgeschlossene und offene Signale der letzten 7 Tage
- Treffer, Ergebnis in R, Ø pro Trade, und was laut Historie zu erwarten war
- nur die Trades, für die die Trendampel sprach
- je Strategie, bester und schlechtester Trade, offene Trades mit Zwischenstand
- Stand seit Beginn und aktuelle Trendampel je Coin

Auch im Programm unter „📝 Papier-Test“ ganz unten. Sofort erzeugen: `python -m signalbot bericht`.

Einstellungen in `config.yaml`:

```yaml
track_results: true   # Nachricht bei Ziel/Stop
weekly_report: true
report_weekday: 6     # 0 = Montag ... 6 = Sonntag
report_hour: 18
```

Läuft nur, solange das Programm läuft (Oberfläche oder `python -m signalbot run`).

## Neu berechnen

Auf GitHub: Reiter „Actions“ → „Trefferquoten“ → „Run workflow“. Läuft außerdem automatisch am Monatsersten,
lädt die neuesten Coinbase-Kurse und speichert das Ergebnis in `results/trefferquoten/`.
Lokal: `python scripts/trefferquoten.py <history-ordner>`.
