"""Config loading utilities for Flag Patterns strategy/tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

import yaml

from .strategy import FlagPatternsConfig


@dataclass
class FlagPatternsTestConfig:
    strategy: FlagPatternsConfig


def load_config(path: Path | None = None) -> FlagPatternsConfig:
    if path is None:
        path = Path(__file__).with_name("params.yaml")
    data = yaml.safe_load(Path(path).read_text())
    orders = data.get("order_scan_range", [6, 8, 10])
    if isinstance(orders, list):
        order_iter: Iterable[int] = [int(o) for o in orders]
    else:
        order_iter = [int(orders)]
    return FlagPatternsConfig(
        symbol=data.get("symbol", "BTC/USDT"),
        order_scan_range=order_iter,
        hold_multiplier=float(data.get("hold_multiplier", 1.0)),
        use_trendline_mode=bool(data.get("use_trendline_mode", False)),
        per_trade_risk_pct=float(data.get("per_trade_risk_pct", 0.02)),
        max_concurrent_positions=int(data.get("max_concurrent_positions", 2)),
    )

