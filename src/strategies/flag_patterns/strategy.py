"""Flag Patterns strategy integration for GoldenEggBot.

The core detection logic is sourced from TechnicalAnalysisAutomation (MIT license).
We wrap the upstream modules to expose the StrategyBase interface while keeping
behavior consistent with the original implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

import numpy as np
import pandas as pd

from ..strategy_base import Signal, StrategyBase
from .analysis import PatternReturns, evaluate_orders, summarise_patterns
from .upstream.flags_pennants import FlagPattern, find_flags_pennants_pips


@dataclass
class FlagPatternsConfig:
    symbol: str
    order_scan_range: Iterable[int]
    hold_multiplier: float = 1.0
    use_trendline_mode: bool = False
    per_trade_risk_pct: float = 0.02
    max_concurrent_positions: int = 2


class FlagPatternsStrategy(StrategyBase):
    """Concrete strategy wrapping upstream flag detection logic."""

    def __init__(self, config: FlagPatternsConfig):
        self._config = config

    @property
    def name(self) -> str:  # pragma: no cover - simple constant
        return "flag_patterns_trendline"

    @property
    def warmup_bars(self) -> int:
        max_order = max(self._config.order_scan_range)
        return int(max_order * 3)

    def generate_signal(self, market_data: pd.DataFrame) -> Optional[Signal]:
        df = market_data.sort_index()
        closes = df["close"].to_numpy(dtype=float)
        log_prices = np.log(closes)
        latest_patterns = self._detect_latest_pattern(log_prices)
        if latest_patterns is None:
            return None
        pattern, side = latest_patterns
        entry_price = float(closes[-1])
        stop_price, target_price = self._risk_params(pattern, closes, side)
        metadata = {
            "flag_width": pattern.flag_width,
            "flag_height": pattern.flag_height,
            "pole_width": pattern.pole_width,
            "pole_height": pattern.pole_height,
            "support_slope": pattern.support_slope,
            "resist_slope": pattern.resist_slope,
            "side": side,
        }
        return Signal(
            timestamp=df.index[-1],
            symbol=self._config.symbol,
            side=side,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            confidence=self._confidence(pattern),
            metadata=metadata,
        )

    def optimize_parameters(self, historical: pd.DataFrame) -> Dict[str, float]:
        results = evaluate_orders(
            historical,
            orders=self._config.order_scan_range,
            hold_multiplier=self._config.hold_multiplier,
            use_trendline=self._config.use_trendline_mode,
        )
        summary = summarise_patterns(results)
        return {
            "recommended_hold_multiplier": self._config.hold_multiplier,
            "historical_win_rate": summary["win_rate"],
            "historical_avg_return": summary["avg_return"],
        }

    # ------------------------------------------------------------------
    def _detect_latest_pattern(self, log_prices: np.ndarray) -> Optional[tuple[FlagPattern, str]]:
        detector = find_flags_pennants_pips
        if self._config.use_trendline_mode:
            from .upstream.flags_pennants import find_flags_pennants_trendline as detector  # lazy import to avoid circular alias

        for order in sorted(self._config.order_scan_range, reverse=True):
            bull_flags, bear_flags, _, _ = detector(log_prices, order)
            for pattern in reversed(bull_flags):
                if pattern.conf_x == len(log_prices) - 1:
                    return pattern, "LONG"
            for pattern in reversed(bear_flags):
                if pattern.conf_x == len(log_prices) - 1:
                    return pattern, "SHORT"
        return None

    def _risk_params(self, pattern: FlagPattern, closes: np.ndarray, side: str) -> tuple[float, float]:
        tip_slice = closes[max(0, pattern.tip_x): pattern.conf_x + 1]
        if len(tip_slice) == 0:
            stop_price = closes[-1]
        elif side == "LONG":
            stop_price = float(tip_slice.min())
        else:
            stop_price = float(tip_slice.max())

        entry_price = float(closes[pattern.conf_x])
        rr = 2.0
        if side == "LONG":
            target_price = entry_price + (entry_price - stop_price) * rr
        else:
            target_price = entry_price - (stop_price - entry_price) * rr
        return stop_price, target_price

    def _confidence(self, pattern: FlagPattern) -> float:
        width_score = np.clip(pattern.flag_width / max(1, pattern.pole_width), 0.0, 1.0)
        height_score = np.clip(pattern.flag_height / max(1e-6, pattern.pole_height), 0.0, 1.0)
        confidence = max(0.05, 1.0 - (width_score + height_score) / 2)
        return float(confidence)
