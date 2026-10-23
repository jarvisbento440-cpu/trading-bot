"""Lernen aus vergangenen Signalen: Wie wahrscheinlich trifft ein neues Signal sein Ziel?

Jedes Signal wird mit Merkmalen beschrieben, die zum Signalzeitpunkt bekannt sind
(Strategie, Coin-Lage, Trendampel, Schwankung, RSI, Abstand zu Durchschnitten, wie gut die
Strategie zuletzt lief ...). Ein kleines Lernmodell (logistische Regression, nur numpy) lernt
aus abgeschlossenen Trades, welche Merkmale bei Treffern und welche bei Fehlsignalen vorkamen.

Daraus entstehen für jedes neue Signal:
- p_win: geschätzte Wahrscheinlichkeit, dass Ziel 1 vor dem Stop erreicht wird
- exp_r: erwartetes Ergebnis in R nach Gebühren (p_win * Chance - (1 - p_win) * Risiko)

Ehrlichkeit: Ob das Modell wirklich hilft, prüft walk_forward() – trainiert wird immer nur mit
Trades, die vor dem Prüfzeitraum abgeschlossen waren.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .regime import DAY_MS, SMA

STRATS = ["score", "donchian", "supertrend", "macd", "rsi", "squeeze", "fib", "sweep"]
FEE = 0.001
RECENT_N = 20  # wie viele letzte Trades für "lief zuletzt gut/schlecht"

FEATURES = [
    *[f"st_{k}" for k in STRATS],
    "long", "tf_4h", "rr", "risk_atr", "score",
    "atr_pct", "vol_regime", "rsi_s", "ema50_s", "ema200_s", "ret20_s", "vol_z", "bb_rel",
    "light_with", "daily_dist_s", "daily_vol", "btc_with",
    "recent_strat", "recent_coin",
]

# Verständliche Namen für Erklärungen
LABELS = {
    "rr": "Chance/Risiko", "risk_atr": "Stop-Abstand", "score": "Setup-Score",
    "atr_pct": "Schwankung", "vol_regime": "Schwankung höher als üblich", "rsi_s": "RSI in Signalrichtung",
    "ema50_s": "Abstand zur EMA50", "ema200_s": "Abstand zur EMA200", "ret20_s": "Bewegung der letzten 20 Kerzen",
    "vol_z": "Volumen", "bb_rel": "Bollinger-Breite", "light_with": "Trendampel spricht dafür",
    "daily_dist_s": "Abstand zum 50-Tage-Schnitt", "daily_vol": "Tages-Schwankung", "btc_with": "BTC-Ampel spricht dafür",
    "recent_strat": "Strategie lief zuletzt", "recent_coin": "Coin lief zuletzt", "long": "Long-Richtung",
    "tf_4h": "4h-Zeitebene",
}


def _daily_ctx(daily: pd.DataFrame | None) -> pd.DataFrame | None:
    """Tageswerte, gültig ab Ende der Tageskerze (kein Blick in die Zukunft)."""
    if daily is None or len(daily) < SMA + 2:
        return None
    c = daily["close"].astype(float).reset_index(drop=True)
    ma = c.rolling(SMA).mean()
    return pd.DataFrame({
        "avail": (daily["ts"].values + DAY_MS).astype("int64"),
        "on": (c > ma).astype(float).where(ma.notna()).values,
        "dist": (c / ma - 1).values,
        "dvol": (c.pct_change().rolling(30).std() * math.sqrt(365)).values,
    })


def _asof(ts: pd.Series, ctx: pd.DataFrame | None, cols: list[str], bar_ms: int) -> pd.DataFrame:
    """Tageswerte zum Schluss jeder Signal-Kerze (ts + bar_ms)."""
    if ctx is None:
        return pd.DataFrame({c: np.full(len(ts), np.nan) for c in cols})
    left = pd.DataFrame({"t": ts.values.astype("int64") + bar_ms, "order": range(len(ts))})
    m = pd.merge_asof(left.sort_values("t"), ctx.sort_values("avail"), left_on="t", right_on="avail",
                      direction="backward").sort_values("order")
    return m[cols].reset_index(drop=True)


def bar_table(d: pd.DataFrame, daily: pd.DataFrame | None, btc_daily: pd.DataFrame | None, bar_ms: int) -> pd.DataFrame:
    """Merkmale je Kerze (noch ohne Richtung). d muss mit strategies.prepare() vorbereitet sein."""
    c, a = d["close"], d["atr"]
    atr_pct = a / c
    out = pd.DataFrame({
        "atr_pct": atr_pct * 100,
        "vol_regime": atr_pct / atr_pct.rolling(200, min_periods=50).median(),
        "rsi": d["rsi"],
        "ema50": (c - d["ema50"]) / a,
        "ema200": (c - d["ema200"]) / a,
        "ret20": (c - c.shift(20)) / a,
        "vol_z": d["vol_z"].clip(-3, 5),
        "bb_rel": d["bb_width"] / d["bb_width"].rolling(200, min_periods=50).median(),
    }).reset_index(drop=True)
    dc = _asof(d["ts"], _daily_ctx(daily), ["on", "dist", "dvol"], bar_ms)
    bc = _asof(d["ts"], _daily_ctx(btc_daily), ["on"], bar_ms)
    out["d_on"], out["d_dist"], out["d_vol"], out["btc_on"] = dc["on"], dc["dist"], dc["dvol"], bc["on"]
    return out


def signal_features(bt: pd.DataFrame, i: int, strategy: str, side: str, tf: str, entry: float, stop: float,
                    target1: float, atr: float, score: int = 0) -> dict:
    """Merkmale eines einzelnen Signals (ohne die "zuletzt"-Werte, die kommen aus der Trade-Historie)."""
    b = bt.iloc[i]
    s = 1.0 if side == "long" else -1.0
    risk = abs(entry - stop)
    f = {f"st_{k}": float(strategy == k) for k in STRATS}

    def light(on):
        if pd.isna(on):
            return 0.0  # unbekannt
        return 1.0 if (on == 1) == (side == "long") else -1.0

    f.update({
        "long": float(side == "long"), "tf_4h": float(tf == "4h"),
        "rr": abs(target1 - entry) / risk if risk else 0.0,
        "risk_atr": risk / atr if atr else 0.0,
        "score": score / 100,
        "atr_pct": b["atr_pct"], "vol_regime": b["vol_regime"],
        "rsi_s": (b["rsi"] - 50) * s / 50,
        "ema50_s": s * b["ema50"], "ema200_s": s * b["ema200"], "ret20_s": s * b["ret20"],
        "vol_z": b["vol_z"], "bb_rel": b["bb_rel"],
        "light_with": light(b["d_on"]),
        "daily_dist_s": 0.0 if pd.isna(b["d_dist"]) else s * b["d_dist"] * 100,
        "daily_vol": b["d_vol"],
        "btc_with": light(b["btc_on"]),
    })
    return {k: (0.0 if v is None or not np.isfinite(v) else float(v)) for k, v in f.items()}


def add_recent(trades: list[dict]) -> None:
    """Trägt in jeden Trade ein, wie die letzten RECENT_N abgeschlossenen Trades derselben Strategie
    bzw. desselben Coins liefen – nur Trades, die vor dem Signal schon beendet waren."""
    order = sorted(range(len(trades)), key=lambda k: trades[k]["bar_ts"])
    closed = sorted((t for t in trades if t.get("exit_ts") is not None), key=lambda t: t["exit_ts"])
    j = 0
    hist_s: dict[str, list[float]] = {}
    hist_c: dict[str, list[float]] = {}
    for k in order:
        t = trades[k]
        while j < len(closed) and closed[j]["exit_ts"] <= t["bar_ts"]:
            c = closed[j]
            hist_s.setdefault(c["strategy"], []).append(c["r"])
            hist_c.setdefault(c["symbol"], []).append(c["r"])
            j += 1
        t["recent_strat"] = _recent(hist_s.get(t["strategy"], []))
        t["recent_coin"] = _recent(hist_c.get(t["symbol"], []))


def _recent(rs: list[float]) -> float:
    last = rs[-RECENT_N:]
    if not last:
        return 0.0
    # zur Null hin gezogen, damit 2–3 Trades nicht zu viel Gewicht haben
    return float(np.clip(sum(last) / (len(last) + 5), -1.5, 1.5))


def expected_r(p: np.ndarray, rr: np.ndarray, fee_r: np.ndarray | float = 0.0) -> np.ndarray:
    return p * rr - (1 - p) - fee_r


# ---------------- Modell ----------------

class Model:
    """Logistische Regression mit L2-Bremse (gegen Auswendiglernen)."""

    def __init__(self, l2: float = 3.0):
        self.l2 = l2
        self.w: np.ndarray | None = None
        self.mu = self.sd = None
        self.trained_on = 0
        self.base_rate = 0.5

    def _x(self, X: np.ndarray) -> np.ndarray:
        Z = (np.nan_to_num(X) - self.mu) / self.sd
        return np.c_[np.ones(len(Z)), np.clip(Z, -5, 5)]

    def fit(self, X: np.ndarray, y: np.ndarray, weight: np.ndarray | None = None,
            prior: "Model | None" = None) -> "Model":
        """Trainieren. Mit `prior` wird nicht bei null angefangen, sondern beim mitgelieferten Grundmodell:
        die Gewichte werden nur so weit verschoben, wie die neuen Trades es deutlich verlangen."""
        X = np.nan_to_num(np.asarray(X, float))
        y = np.asarray(y, float)
        w8 = np.ones(len(y)) if weight is None else np.asarray(weight, float)
        if prior is not None:
            self.mu, self.sd = prior.mu, prior.sd
        else:
            self.mu = X.mean(0)
            self.sd = X.std(0)
            self.sd[self.sd < 1e-9] = 1.0
        Z = self._x(X)
        w0 = np.zeros(Z.shape[1]) if prior is None else prior.w.copy()
        w = w0.copy()
        reg = np.full(Z.shape[1], self.l2)
        if prior is None:
            reg[0] = 0.0
        for _ in range(50):  # Newton-Verfahren
            p = 1 / (1 + np.exp(-Z @ w))
            g = Z.T @ (w8 * (p - y)) + reg * (w - w0)
            H = (Z * (w8 * p * (1 - p))[:, None]).T @ Z + np.diag(reg + 1e-9)
            step = np.linalg.solve(H, g)
            w -= step
            if np.abs(step).max() < 1e-7:
                break
        self.w = w
        self.trained_on = int(len(y)) + (prior.trained_on if prior is not None else 0)
        self.base_rate = float(np.average(y, weights=w8))
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return 1 / (1 + np.exp(-self._x(np.asarray(X, float)) @ self.w))

    def explain(self, x: np.ndarray, top: int = 3) -> list[tuple[str, float]]:
        """Welche Merkmale haben die Wahrscheinlichkeit am stärksten nach oben/unten gedrückt?"""
        z = self._x(np.asarray(x, float)[None, :])[0, 1:]
        contrib = z * self.w[1:]
        idx = np.argsort(-np.abs(contrib))
        out = []
        for k in idx:
            name = FEATURES[k]
            if name.startswith("st_") or name == "rr" or abs(contrib[k]) < 0.05:  # Chance/Risiko steckt schon in exp_r
                continue
            out.append((LABELS.get(name, name), float(contrib[k])))
            if len(out) >= top:
                break
        return out

    def to_dict(self) -> dict:
        return {"features": FEATURES, "l2": self.l2, "w": self.w.tolist(), "mu": self.mu.tolist(),
                "sd": self.sd.tolist(), "trained_on": self.trained_on, "base_rate": self.base_rate}

    @classmethod
    def from_dict(cls, d: dict) -> "Model | None":
        if d.get("features") != FEATURES:
            return None  # alte Merkmalsliste -> neu trainieren
        m = cls(d.get("l2", 3.0))
        m.w, m.mu, m.sd = np.array(d["w"]), np.array(d["mu"]), np.array(d["sd"])
        m.trained_on, m.base_rate = d.get("trained_on", 0), d.get("base_rate", 0.5)
        return m


def matrix(trades: list[dict]) -> np.ndarray:
    return np.array([[t.get(k, 0.0) for k in FEATURES] for t in trades], float)


def label(trades: list[dict]) -> np.ndarray:
    return np.array([1.0 if t["r"] > 0 else 0.0 for t in trades])


def fee_r(t: dict) -> float:
    risk = abs(t["entry"] - t["stop"])
    return 2 * FEE * t["entry"] / risk if risk else 0.0


def walk_forward(trades: list[dict], start_ms: int, step_ms: int = 30 * DAY_MS, min_train: int = 300,
                 l2: float = 3.0, threshold: float = 0.0) -> list[dict]:
    """Jeden Monat neu trainieren (nur mit Trades, die vorher abgeschlossen waren) und die Trades
    des Monats bewerten. Gibt die bewerteten Trades mit p_win / exp_r zurück."""
    trades = sorted(trades, key=lambda t: t["bar_ts"])
    end = max(t["bar_ts"] for t in trades) + 1
    out = []
    t0 = start_ms
    while t0 < end:
        t1 = t0 + step_ms
        train = [t for t in trades if t["exit_ts"] < t0]
        test = [t for t in trades if t0 <= t["bar_ts"] < t1]
        if len(train) >= min_train and test:
            m = Model(l2).fit(matrix(train), label(train))
            p = m.predict(matrix(test))
            rr = np.array([t["rr"] for t in test])
            fr = np.array([fee_r(t) for t in test])
            ev = expected_r(p, rr, fr)
            for t, pi, ei in zip(test, p, ev):
                out.append({**t, "p_win": float(pi), "exp_r": float(ei), "take": bool(ei > threshold)})
        t0 = t1
    return out


# ---------------- Speichern / Laden ----------------

def save_model(m: Model, path: str | Path, info: dict | None = None) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({**m.to_dict(), **(info or {})}, ensure_ascii=False), encoding="utf-8")


def load_model(path: str | Path) -> tuple[Model | None, dict]:
    p = Path(path)
    if not p.exists():
        return None, {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, {}
    return Model.from_dict(d), d


# ---------------- Live-Betrieb ----------------

MODEL_FILE = Path(__file__).resolve().parents[1] / "results" / "lernen" / "lernmodell.json"

LEARN_SCHEMA = """
CREATE TABLE IF NOT EXISTS signal_learn (
    signal_id INTEGER PRIMARY KEY,
    features  TEXT,   -- Merkmale beim Signal (JSON)
    p_win     REAL,   -- geschätzte Trefferchance
    exp_r     REAL,   -- erwartetes Ergebnis in R
    take      INTEGER -- 1 = Lernfilter lässt durch
);
"""

_cache: dict = {}


def live_model() -> Model | None:
    """Mitgeliefertes Lernmodell (wird per GitHub-Workflow regelmäßig mit neuen Daten nachtrainiert)."""
    try:
        mtime = MODEL_FILE.stat().st_mtime
    except OSError:
        return None
    if _cache.get("mtime") != mtime:
        _cache["model"], _cache["info"] = load_model(MODEL_FILE)
        _cache["mtime"] = mtime
    return _cache["model"]


def model_info() -> dict:
    live_model()
    info = dict(_cache.get("info") or {})
    for k in ("w", "mu", "sd", "features"):
        info.pop(k, None)
    return info


def btc_symbol(symbols: list[str]) -> str | None:
    return next((s for s in symbols if s.split("/")[0] == "BTC"), None)


def recent_values(db, strategy: str, symbol: str, before_ts: int) -> dict:
    """Wie liefen die letzten abgeschlossenen Papier-Trades dieser Strategie / dieses Coins?"""
    try:
        q = ("SELECT r FROM paper_trades WHERE {} = ? AND status IN ('win','loss','timeout') AND exit_ts <= ? "
             "ORDER BY exit_ts DESC LIMIT ?")
        rs = [r for (r,) in db.conn.execute(q.format("strategy"), (strategy, before_ts, RECENT_N))]
        rc = [r for (r,) in db.conn.execute(q.format("symbol"), (symbol, before_ts, RECENT_N))]
    except Exception:  # Tabelle gibt es noch nicht
        rs, rc = [], []
    return {"recent_strat": _recent(rs[::-1]), "recent_coin": _recent(rc[::-1])}


def assess(model: Model, f: dict) -> dict:
    x = np.array([[f.get(k, 0.0) for k in FEATURES]])
    p = float(model.predict(x)[0])
    ev = float(expected_r(np.array([p]), np.array([f.get("rr", 0.0)]), f.get("fee_r", 0.0))[0])
    return {"p_win": p, "exp_r": ev, "take": ev > 0,
            "why": [{"name": n, "effect": e} for n, e in model.explain(x[0])]}


class Assessor:
    """Bewertet Signale eines Charts: einmal Merkmale je Kerze berechnen, dann je Signal nachschlagen."""

    def __init__(self, db, d: pd.DataFrame, daily: pd.DataFrame | None, btc_daily: pd.DataFrame | None,
                 symbol: str, tf: str, bar_ms: int):
        self.model = live_model()
        self.db, self.d, self.symbol, self.tf = db, d, symbol, tf
        self.bt = bar_table(d, daily, btc_daily, bar_ms) if self.model is not None else None

    def __call__(self, sig) -> dict | None:
        if self.model is None:
            return None
        a = float(self.d["atr"].iat[sig.i])
        f = signal_features(self.bt, sig.i, sig.strategy, sig.side, self.tf, sig.entry, sig.stop, sig.target1, a,
                            sig.score)
        f.update(recent_values(self.db, sig.strategy, self.symbol, sig.bar_ts))
        risk = abs(sig.entry - sig.stop)
        f["fee_r"] = 2 * FEE * sig.entry / risk if risk else 0.0
        return {**assess(self.model, f), "features": f}


def store(db, signal_id: int, res: dict) -> None:
    db.conn.executescript(LEARN_SCHEMA)
    db.conn.execute("INSERT OR REPLACE INTO signal_learn (signal_id, features, p_win, exp_r, take) VALUES (?,?,?,?,?)",
                    (signal_id, json.dumps(res["features"]), res["p_win"], res["exp_r"], int(res["take"])))
    db.conn.commit()


def why_text(why: list[dict]) -> str:
    """Kurze Begründung: was sprach dafür, was dagegen."""
    pro = [w["name"] for w in why if w["effect"] > 0]
    con = [w["name"] for w in why if w["effect"] < 0]
    parts = []
    if pro:
        parts.append("dafür: " + ", ".join(pro))
    if con:
        parts.append("dagegen: " + ", ".join(con))
    return "; ".join(parts)


def mistake_analysis(trade: dict) -> list[dict]:
    """Für einen abgeschlossenen Papier-Trade: welche Merkmale sprachen laut Modell dagegen/dafür?"""
    m = live_model()
    if m is None or not trade.get("features"):
        return []
    try:
        f = json.loads(trade["features"])
    except ValueError:
        return []
    x = np.array([f.get(k, 0.0) for k in FEATURES])
    return [{"name": n, "effect": e} for n, e in m.explain(x, top=4)]
