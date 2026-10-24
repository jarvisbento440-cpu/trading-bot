from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass
class Risk:
    stop_atr: float = 1.5
    target1_r: float = 1.5
    target2_r: float = 2.5
    cooldown_bars: int = 6


@dataclass
class Config:
    exchange: str = "binance"
    symbols: list[str] = field(default_factory=lambda: ["BTC/USDT"])
    signal_timeframes: list[str] = field(default_factory=lambda: ["1h", "4h"])
    trend_timeframe: str = "1d"
    store_timeframes: list[str] = field(default_factory=lambda: ["15m", "1h", "4h", "1d"])
    backfill_days: int = 730
    poll_minutes: int = 5
    min_score: int = 65
    risk: Risk = field(default_factory=Risk)
    database: str = "data/signalbot.db"
    strategies: list[str] = field(default_factory=lambda: [
        "score", "donchian", "supertrend", "macd", "rsi", "squeeze", "fib", "sweep"])
    trend_light: bool = True  # Trendampel (Tages-Trendfilter) anzeigen und melden
    learn_filter: bool = True  # Lernmodell: schwache Signale nicht per Telegram melden (Papier-Test zeichnet sie trotzdem auf)
    track_results: bool = True  # Telegram, wenn ein Signal Ziel oder Stop erreicht
    weekly_report: bool = True  # Wochenbericht per Telegram
    report_weekday: int = 6     # 0 = Montag … 6 = Sonntag
    report_hour: int = 18       # Ortszeit
    telegram_token: str = ""
    telegram_chat_id: str = ""


def load_config(path: str | Path = "config.yaml") -> Config:
    load_dotenv()
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    risk = Risk(**raw.pop("risk", {}))
    cfg = Config(**raw, risk=risk)
    cfg.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    cfg.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    # Trend-Zeitebene und Signal-Zeitebenen müssen gespeichert werden
    for tf in [*cfg.signal_timeframes, cfg.trend_timeframe]:
        if tf not in cfg.store_timeframes:
            cfg.store_timeframes.append(tf)
    return cfg
