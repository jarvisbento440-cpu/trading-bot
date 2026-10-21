"""Prüft die Yahoo-Anbindung (Suche + Kurse) und speichert Beispieldaten als JSON.

Aufruf: python scripts/check_yahoo.py /tmp/yahoo
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from signalbot import yahoo  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "yahoo")
out.mkdir(parents=True, exist_ok=True)
report = {"search": {}}
for q in ("gold", "s&p 500", "nvidia", "dax"):
    report["search"][q] = yahoo.search(q)[:5]
    print("Suche", q, [x["symbol"] for x in report["search"][q]])
for sym in ("^GSPC", "GC=F", "SI=F", "EURUSD=X"):
    h1 = yahoo.fetch(sym, "60m", "730d")
    d1 = yahoo.fetch(sym, "1d", "10y")
    print(sym, "1h:", len(h1), h1[0][0] if h1 else None, h1[-1] if h1 else None, "| 1d:", len(d1))
    (out / f"{sym.replace('^', '').replace('=', '_')}.json").write_text(json.dumps({"symbol": sym, "1h": h1, "1d": d1}))
(out / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
