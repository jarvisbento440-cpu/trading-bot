# Lernmodell: aus Fehlsignalen lernen

## Kurz gesagt

Der Bot schätzt jetzt für jedes Signal, wie wahrscheinlich es sein Ziel erreicht, und sortiert schwache Signale aus.
Gelernt hat er das aus **45.324 vergangenen Signalen** seiner eigenen 8 Strategien (10 Coins, 1h und 4h, Januar 2021 bis Oktober 2026),
bei denen jeweils feststeht, ob sie getroffen haben oder nicht.

**Ergebnis im unberührten Prüfjahr (Okt. 2025 bis Okt. 2026):**

| | Signale | Trefferquote | Ø pro Trade | Summe |
|---|---:|---:|---:|---:|
| Alle Signale | 9.767 | 40 % | −0,12 R | −1.124 R |
| Vom Lernfilter durchgelassen | 3.198 | 42 % | **−0,00 R** | −13 R |
| Als schwach aussortiert | 6.569 | 40 % | −0,17 R | −1.111 R |

Nur die 5 Fokus-Coins (BTC, ETH, SOL, XRP, ONDO): alle −0,14 R, durchgelassen −0,02 R, aussortiert −0,20 R.

**Ehrliche Einordnung:** Das Modell erkennt Fehlsignale tatsächlich: Es hat in 10 von 13 Monaten des Prüfjahrs besser abgeschnitten
als „alle Signale nehmen“ und fast den ganzen Verlust vermieden. Aber es macht die Strategien **nicht profitabel**: Auch die
durchgelassenen Signale liegen nach Gebühren ungefähr bei null. Es ist ein Schutz vor schlechten Signalen, keine Gewinnmaschine.
Die Trendampel bleibt die Grundlage.

## Was der Bot sich bei jedem Signal ansieht

Alles ist zum Signalzeitpunkt bekannt, nichts schaut in die Zukunft:

- welche Strategie, Long/Short, 1h/4h, Setup-Score, Chance/Risiko, Stop-Abstand
- Schwankung (ATR in %) und ob sie gerade höher ist als üblich, Bollinger-Breite
- RSI, Abstand zur EMA50/EMA200, Bewegung der letzten 20 Kerzen, Volumen
- Tages-Lage: Trendampel, Abstand zum 50-Tage-Schnitt, Tages-Schwankung, BTC-Ampel
- **wie die Strategie und der Coin zuletzt liefen** (letzte 20 abgeschlossene Trades)

Daraus berechnet ein kleines Lernmodell (logistische Regression mit Bremse gegen Auswendiglernen) die Trefferchance und das
erwartete Ergebnis: `Trefferchance × Chance/Risiko − (1 − Trefferchance) × 1 R − Gebühren`. Ist das unter 0 R, gilt das Signal als schwach.

Was das Modell gelernt hat (wichtigste Merkmale): Signale **mit Abstand über der EMA50** in Signalrichtung, auf **4h** und mit
**hohem Setup-Score** treffen öfter; Signale bei **sehr hoher Schwankung** und mit **sehr weitem Ziel** seltener.
Liquiditäts-Sweep und Score-Modell werden meist aussortiert, Donchian und Supertrend öfter durchgelassen.

## So wurde geprüft (gegen Selbstbetrug)

- **Walk-forward:** Ab Juli 2022 wird jeden Monat neu trainiert, und zwar nur mit Trades, die vor diesem Monat schon abgeschlossen waren.
  Bewertet werden dann die Signale des neuen Monats. So weiß das Modell nie etwas über die Zukunft.
- **Prüfjahr getrennt:** Einstellungen (Bremse, Schwelle) wurden nur nach 2022–2025 beurteilt. Mehrere Varianten lagen alle ähnlich,
  das Ergebnis hängt also nicht an einer glücklichen Einstellung.
- **Vergleich mit einfacher Regel ohne KI** („nur Strategien nehmen, die bisher Gewinn brachten“): Prüfjahr −0,02 R statt −0,00 R,
  in der Entwicklungszeit deutlich schlechter (−0,10 R statt −0,07 R). Die Merkmale bringen also etwas über die reine Strategie-Statistik hinaus.
- **Nur aus den eigenen Trades nachlernen** (Grundmodell + monatlich mit den Trades der 5 Fokus-Coins angepasst): **nicht besser**,
  eher etwas schlechter (−0,04 bis −0,05 R statt −0,02 R). Ein paar hundert eigene Trades sind zu wenig und zu zufällig.
  Deshalb lernt der Bot aus der **ganzen Signal-Historie aller Coins**, die jeden Monat neu von der Börse geladen wird. Das sind dieselben
  Regeln wie live, also genau die Fehler, die der Bot gemacht hätte, nur 100-mal mehr davon.
- Die Ergebnisse sind nicht unabhängig voneinander (mehrere Strategien feuern oft gleichzeitig), und ein Prüfjahr ist kurz.

## Im Programm

- **Telegram:** Jedes Signal bekommt eine Zeile wie
  `Lernmodell: 46 % Trefferchance, erwartet +0,08 R (dafür: 4h-Zeitebene, Abstand zur EMA50; dagegen: Schwankung)`.
  Mit `learn_filter: true` (Standard, in `config.yaml`) werden schwache Signale nicht mehr geschickt.
- **Vollbild:** Bei jedem aktuellen Signal steht „🧠 Lernfilter: durch / schwach“ mit Trefferchance und Begründung.
- **Papier-Test:** Auch aussortierte Signale werden weiter als virtuelle Trades mitgeschrieben. Der Abschnitt „🧠 Lernmodell“
  vergleicht live, ob die durchgelassenen besser laufen als die aussortierten. In der Trade-Liste steht bei jedem abgeschlossenen
  Trade, **was laut Modell dafür (▲) und dagegen (▼) sprach**, also warum ein Fehlsignal ein Fehlsignal war.
  Schalter „Nur Signale, die der Lernfilter durchlässt“.
- **Nachtrainieren:** GitHub → Actions → „Lernmodell“ läuft jeden Monatsersten automatisch (oder per „Run workflow“),
  lädt die neuesten Kurse, prüft alles erneut und speichert `results/lernen/lernmodell.json` und `lern-ergebnis.json`.

## Selbst nachrechnen

```bash
python scripts/learn_research.py <ordner-mit-kurs-historie> results/lernen
```

Die Kurs-Historie liegt im Branch `history` oder wird mit `python scripts/fetch_history.py --out history` geladen.

## Und KI wie ChatGPT/Claude?

Ein Sprachmodell kann Fehlsignale in Worten erklären, sagt aber Kurse nicht besser voraus als dieses Modell und bräuchte einen
kostenpflichtigen API-Schlüssel. Die Begründung „dafür/dagegen“ kommt deshalb direkt aus dem Lernmodell, ohne Schlüssel und ohne Kosten.
