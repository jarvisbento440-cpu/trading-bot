# Trendampel und Strategie-Forschung (Stand 15.10.2026)

## Ergebnis in einem Satz

Von über 50 getesteten Regeln hat nur eine Familie in der Entwicklungs- **und** in der Prüfphase vorne gelegen: ein einfacher **Tages-Trendfilter** (Schlusskurs über dem 50-Tage-Schnitt = halten, darunter = raus). Er verdient nicht jedes Jahr mehr als Kaufen & Halten, aber er vermeidet den Großteil der Abstürze. Eine Strategie, die zuverlässig Gewinn macht, wurde **nicht** gefunden.

## Vorgehen

- Daten: Coinbase-Tageskerzen und Stundenkerzen ab 01.01.2021 für BTC, ETH, SOL, XRP, ONDO, ADA, AVAX, LINK, DOGE, LTC (geladen mit dem Workflow „Kurs-Historie“, Branch `history`). XRP erst ab 13.07.2023 (vorher bei Coinbase nicht handelbar).
- **Entwicklung (In-Sample):** 2021 bis 10.10.2025. Nur hier wurden Regeln und Parameter ausgewählt.
- **Prüfung (Out-of-Sample):** 11.10.2025 bis 10.10.2026, vorher nicht angeschaut.
- Position wird zum Tagesschluss festgelegt und gilt ab dem nächsten Tag. 0,1 % Gebühr pro Seite.
- Portfolio: gleich gewichtet über alle Coins mit mindestens 200 Tagen Historie.
- Skript: `scripts/research.py`, alle Zahlen in `results/research_results.json`.

## Was getestet wurde (alle 10 Coins)

| Regel | Entwicklung CAGR / Sharpe | Prüfjahr CAGR / Sharpe | Urteil |
|---|---|---|---|
| Kaufen & Halten | +13 % / 0,52, MaxDD −84 % | −39 % / −0,52 | Vergleichsmaßstab |
| **50-Tage-Trendfilter + Größe nach Schwankung** | **+16 % / 0,71**, MaxDD −37 % | **+6 % / 0,37**, MaxDD −22 % | **übernommen** |
| 50-Tage-Trendfilter (ohne Größe) | +18 % / 0,60 | +2 % / 0,21 | gut, etwas wilder |
| 20-Tage-Trendfilter, 14/30-Tage-Momentum | +20…24 % / 0,65…0,74 | −14…−17 % | fällt im Prüfjahr durch |
| Momentum-Rotation (beste Coins halten) | +29…74 % / bis 1,10 | −3…−55 % | klassisch überangepasst, durchgefallen |
| Long/Short-Trendfilter | −27…0 % | −9…+67 % | in der Entwicklung negativ, nicht verlässlich |
| Donchian-Ausbruch Tag | −0…+10 % | −15…+8 % | kein Vorteil |
| Dip-Kauf im Aufwärtstrend | −1…−6 % | +1…+8 % | in der Entwicklung negativ |
| Uhrzeit-Effekt BTC 21–23 Uhr UTC | −40 % | −45 % | Gebühren fressen den Effekt komplett |
| Puffer-Zonen um den 50-Tage-Schnitt (1–5 %) | ähnlich | schlechter | kein Gewinn |

## Trendampel, Jahr für Jahr (BTC, ETH, SOL, XRP, ONDO)

| Jahr (11.10.–10.10.) | Trendampel | Kaufen & Halten |
|---|---|---|
| 2021/22 | −26 % | −70 % |
| 2022/23 | +13 % | +14 % |
| 2023/24 | +89 % | +183 % |
| 2024/25 | +55 % | +101 % |
| 2025/26 (Prüfjahr) | +13 % | −32 % |
| Größter Rückgang | −44 % | −85 % |

Im Prüfjahr je Coin: BTC +14 % (statt −27 %), ETH +21 % (−35 %), SOL −10 % (−42 %), XRP +2 % (−41 %), ONDO +28 % (−33 %).

## Ehrliche Grenzen

- Etwa 20 Wechsel pro Coin und Jahr (also ~10 Käufe und ~10 Verkäufe). Viele kleine Fehlsignale in Seitwärtsphasen.
- Bei 0,5 % Kosten pro Seite (Spread, schlechte Börse) bleibt im Prüfjahr nur noch etwa ±0 übrig. Günstige Börse nutzen.
- Ein Prüfjahr ist wenig. Die Regel ist alt und bekannt (Faber 2007, Moskowitz/Ooi/Pedersen 2012, für Krypto z. B. Liu/Tsyvinski 2021); dass sie hier auch hält, passt zur Literatur, ist aber keine Garantie.
- Keine Short-Positionen: Long/Short war in der Entwicklung klar negativ.

## Im Programm

- Kachel-Abzeichen „🚦 Halten · 62 %“ oder „🚦 Raus“. Prozent = empfohlener Anteil des Budgets für diesen Coin (Ziel-Schwankung 50 % pro Jahr, höchstens 100 %).
- Grün/graue dicke Linie im Chart = 50-Tage-Schnitt (Schalter „Trendampel“).
- Vollbild: Abschnitt „Trendampel“ mit Datum des letzten Wechsels.
- Bei einem Wechsel blinkt die Kachel und es kommt eine Telegram-Nachricht (einmal pro Tag und Coin, nach Tagesschluss 00:00 UTC = 02:00 deutscher Sommerzeit).
- Abschalten: `trend_light: false` in `config.yaml`.
