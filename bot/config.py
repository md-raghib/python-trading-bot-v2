"""Load config.yaml into typed settings. Secrets come from environment variables only."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path

import yaml

from .costs import CostModel
from .market_hours import MarketHours
from .risk import RiskConfig
from .strategy import StrategyConfig

log = logging.getLogger("bot.config")


@dataclass
class Config:
    symbols: list[str] = field(default_factory=lambda: ["RELIANCE.NS"])
    interval: str = "5m"
    history_period: str = "5d"
    poll_seconds: int = 30
    starting_cash: float = 100_000.0
    state_dir: str = "state"
    log_dir: str = "logs"
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    costs: CostModel = field(default_factory=CostModel)
    hours: MarketHours = field(default_factory=MarketHours)

    @property
    def kill_file(self) -> Path:
        return Path(self.state_dir) / "KILL"

    def kill_switch_on(self) -> bool:
        return self.kill_file.exists() or os.getenv("KILL_SWITCH", "0") == "1"


def _time(s: str) -> time:
    h, m = str(s).split(":")
    return time(int(h), int(m))


def load_config(path: str | None) -> Config:
    if path is None or not Path(path).exists():
        fallback = Path(__file__).resolve().parent.parent / "config.example.yaml"
        if path:
            log.warning("%s not found, using %s", path, fallback.name)
        path = str(fallback) if fallback.exists() else None
    raw = {}
    if path:
        with open(path) as f:
            raw = yaml.safe_load(f) or {}

    hours_raw = raw.get("market_hours", {})
    hours = MarketHours(
        open=_time(hours_raw.get("open", "09:15")),
        close=_time(hours_raw.get("close", "15:30")),
        last_entry=_time(hours_raw.get("last_entry", "15:00")),
        square_off=_time(hours_raw.get("square_off", "15:15")),
        holidays={date.fromisoformat(str(d)) for d in hours_raw.get("holidays", []) or []},
    )
    return Config(
        symbols=list(raw.get("symbols", ["RELIANCE.NS"])),
        interval=str(raw.get("interval", "5m")),
        history_period=str(raw.get("history_period", "5d")),
        poll_seconds=int(raw.get("poll_seconds", 30)),
        starting_cash=float(raw.get("starting_cash", 100_000)),
        state_dir=str(raw.get("state_dir", "state")),
        log_dir=str(raw.get("log_dir", "logs")),
        strategy=StrategyConfig(**(raw.get("strategy") or {})),
        risk=RiskConfig(**(raw.get("risk") or {})),
        costs=CostModel(**(raw.get("costs") or {})),
        hours=hours,
    )
