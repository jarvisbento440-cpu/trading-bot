# News- und On-Chain-Modul (Stand 24.10.2026)

## Ergebnis in einem Satz

Von allen getesteten News- und On-Chain-Regeln hat nur eine in der Entwicklungs- **und** in der Prüfphase geholfen: **Trendampel pausieren, solange die Schlagzeilen der letzten 3 Tage zu diesem Coin im Schnitt negativ sind** (Wert unter −0,2). Der Vorteil ist klein (Prüfjahr +18 % statt +13 %, Rückgang −16 % statt −18 %) und beruht auf nur zwei Jahren Schlagzeilen. Fear & Greed, Funding, Stablecoins, TVL und Hashrate haben als Regel **nicht** funktioniert und werden nur zur Info angezeigt.

## Was das Programm jetzt macht

| Teil | Quelle (alles kostenlos, ohne Schlüssel) | Wie oft |
|---|---|---|
| Schlagzeilen | RSS von CoinDesk, Cointelegraph, Decrypt, The Block, Bitcoin Magazine, CryptoSlate, crypto.news, U.Today + Google News je Coin | alle 10 Min |
| Markt-Stimmung | Fear & Greed Index (alternative.me) | alle 10 Min |
| Funding und Open Interest | Hyperliquid (größte Börse für Perpetuals ohne Anmeldung) | alle 30 Min |
| Stablecoins, TVL, DEX-Umsatz | DefiLlama | alle 30 Min |
| Bitcoin-Netz | mempool.space (Gebühren, Hashrate), Blockchair (größte Transaktion) | alle 30 Min |
| Solana-Netz | öffentlicher Solana-RPC (Transaktionen pro Sekunde) | alle 30 Min |

**Bewertung der Schlagzeilen:** eine feste Wortliste (`signalbot/news.py`), kein KI-Dienst. „Hack“, „Delisting“, „Crash“ zählen −2, „ETF approved“, „record high“, „surge“ zählen +1,5 bis +2 usw. Verneinungen („denies“, „dodges“) schwächen ab. Eine Schlagzeile zählt nur für einen Coin, wenn er im Titel steht. Das ist grob: Ironie, Gerüchte oder Clickbait erkennt die Liste nicht.

**Wo du es siehst:**

- **Kachel:** Abzeichen 📰 mit dem 3-Tage-Schnitt (grün ab +0,2, rot ab −0,2). Rot hinterlegt = News-Filter aktiv. 🚨 = sehr negative Meldung in den letzten 12 Stunden. Die Trendampel zeigt dann „Grün · News ⚠ pausieren“.
- **Vollbild:** Abschnitt „News (3 Tage)“ mit den letzten Meldungen, Fear & Greed und alle On-Chain-Werte.
- **Knopf „📰 News & On-Chain“:** alle Schlagzeilen der letzten 48 Stunden mit Bewertung, Tabelle je Coin, Filter nach Coin.
- **Telegram:**
  - jedes Signal bekommt die Zeilen „News 3 Tage“, „Fear & Greed“ und „Funding“,
  - bei Gegenwind (negative News bei einem Long, sehr starke Meldung gegen die Richtung) einen Abschnitt „⚠️ Gegenwind“,
  - Meldung, wenn der News-Filter bei grüner Trendampel an- oder ausgeht,
  - sehr starke Meldungen (±2) zu deinen Coins, höchstens eine pro Coin alle 3 Stunden.
- **Papier-Test:** Mit jedem Signal werden News-Wert, On-Chain und Fear & Greed gespeichert (Spalte `ctx`), damit man später auswerten kann, ob Signale mit Gegenwind wirklich schlechter laufen.

**Einstellungen (`config.yaml`):** `news`, `onchain` (an/aus), `news_minutes`, `onchain_minutes`, `news_alerts` (starke Meldungen per Telegram) und `context_filter`:

- `warn` (Standard): Gegenwind steht als Hinweis im Signal,
- `block`: Signale mit Gegenwind werden gespeichert, aber nicht per Telegram geschickt,
- `off`: keine Hinweise.

## Wie getestet wurde

- Gleiche Regeln wie bei der Trendampel: Wert ist zum Tagesschluss bekannt, Position gilt ab dem nächsten Tag, 0,1 % Gebühr pro Seite, gleich gewichtet über BTC, ETH, SOL, XRP, ONDO.
- **Entwicklung:** bis 10.10.2025 (Schlagzeilen gibt es erst ab Oktober 2024, Funding ab Mai 2023). **Prüfjahr:** 11.10.2025 – 10.10.2026.
- **Schlagzeilen-Historie:** Google News, wochenweise je Coin, 2 Jahre (ca. 100 Meldungen pro Woche und Coin), bewertet mit derselben Wortliste wie live. Live kommen die RSS-Feeds dazu.
- Daten: Workflow „News/On-Chain-Historie“ → Branch `context-history`. Skript: `scripts/research_context.py`, alle Zahlen in `results/news-onchain/forschung.json`.

## Ergebnisse (Gesamtrendite / größter Rückgang)

| Regel | 2021–25 | Entwicklung 2024/25 | Prüfjahr 2025/26 | Urteil |
|---|---|---|---|---|
| Kaufen & Halten | +246 % / −85 % | +101 % / −48 % | −32 % / −59 % | Vergleich |
| Trendampel | +197 % / −44 % | +55 % / −16 % | +13 % / −18 % | Basis |
| **Trendampel, raus bei negativen News (< −0,2)** | (News erst ab 10/2024) | **+58 % / −16 %** | **+18 % / −16 %** | **übernommen** |
| Trendampel + News nicht negativ (≥ 0) | – | +53 % / −15 % | +16 % / −15 % | ähnlich, etwas schwächer |
| Nur kaufen bei positiven News | – | +16 % / −28 % | +1 % / −25 % | kein Vorteil |
| Fear & Greed: nur bei Angst (< 30) kaufen | +20 % / −64 % | +4 % / −28 % | −41 % / −48 % | durchgefallen |
| Trendampel, raus bei Gier (> 75) | +152 % / −39 % | +30 % / −16 % | +13 % / −18 % | schlechter |
| Trendampel ODER Angst (< 25) | +79 % / −74 % | +37 % / −28 % | −17 % / −45 % | durchgefallen |
| Stablecoins 30 Tage steigend | +431 % / −59 % | +116 % / −48 % | −29 % / −47 % | im Prüfjahr durchgefallen |
| Trendampel + Stablecoins steigend | +168 % / −35 % | +61 % / −16 % | −12 % / −21 % | im Prüfjahr durchgefallen |
| Trendampel, raus bei hohem Funding (> 2×) | +76 % / −44 % | +32 % / −14 % | +11 % / −18 % | schlechter |
| Kaufen bei negativem Funding | +32 % / −19 % | +15 % / −19 % | −7 % / −26 % | durchgefallen |
| Trendampel ODER negatives Funding | +263 % / −44 % | +74 % / −28 % | +10 % / −29 % | im Prüfjahr schlechter |
| Hash-Ribbon (BTC-Hashrate 30 T > 60 T) | +138 % / −67 % | +64 % / −26 % | −29 % / −37 % | durchgefallen |
| Trendampel + Hash-Ribbon | +118 % / −44 % | +49 % / −16 % | −10 % / −20 % | durchgefallen |
| TVL wächst schneller als der Kurs (ETH, SOL, XRP) | −9 % / −78 % | +0 % / −36 % | −27 % / −40 % | durchgefallen |

**Nachprüfung der News-Regel:**

- **Andere Schwellen:** −0,1 / −0,2 / −0,3 helfen alle in beiden Zeiträumen, −0,5 kaum noch. Die Regel hängt also nicht an genau einer Zahl.
- **Höhere Gebühr (0,25 % pro Seite):** Prüfjahr +15 % statt +9 % ohne Filter, Vorteil bleibt.
- **Je Coin (Sharpe Trendampel → mit Filter, Prüfjahr):** BTC 0,65 → 0,91, ONDO 0,80 → 1,20, SOL −0,19 → −0,08, ETH und XRP unverändert. In der Entwicklung war ETH mit Filter schlechter (1,40 → 1,22).
- **Zufallsvergleich:** Gleich viele Raus-Tage, aber zufällig verteilt (200 Durchläufe), ergeben im Mittel einen *schlechteren* Wert (Sharpe 0,48 statt 0,83 im Prüfjahr). Zufällig gleich gut oder besser: 1,5 % der Durchläufe im Prüfjahr, 8,5 % in der Entwicklung.
- **An den Backtest-Signalen (1h/4h, Prüfjahr):** Long-Signale bei negativen News: Ø −0,61 R (39 Trades) statt −0,14 R. Zu wenige Trades für ein sicheres Urteil, aber gleiche Richtung. Bei Shorts war es umgekehrt (Shorts bei *positiven* News liefen sogar etwas besser, +0,03 R), deshalb gibt es für Shorts keinen News-Filter, nur einen Hinweis bei sehr starken Einzelmeldungen.

**Ehrliche Einordnung:** Zwei Jahre Schlagzeilen sind wenig, der Vorteil ist klein, und Google News liefert für die Vergangenheit nicht genau dieselben Meldungen wie heute. Deshalb steht die Regel standardmäßig auf **Hinweis** (`context_filter: warn`) und schaltet nichts automatisch ab. Ob sie live trägt, zeigt der Papier-Test in einigen Monaten.

## Was fehlt (nur gegen Bezahlung)

- **Exchange-Zu-/Abflüsse** (Coins, die auf Börsen geschickt werden = Verkaufsdruck): CryptoQuant, Glassnode – kostenpflichtig.
- **Wal-Wallets mit Namen:** Whale Alert, Arkham – Schlüssel nötig. Angezeigt wird nur die größte BTC-Transaktion der letzten 24 Stunden, ohne Richtung.
- **KI-Bewertung der Schlagzeilen** (statt Wortliste): ginge mit einem Claude-API-Schlüssel (ca. 5–20 € im Monat). Ob das bessere Ergebnisse bringt, müsste man erst genauso testen.
- **XRP-Ledger und ONDO:** außer Funding, Open Interest und XRPL-TVL gibt es keine brauchbaren freien On-Chain-Werte. Ondo-TVL liefert DefiLlama derzeit leer.
