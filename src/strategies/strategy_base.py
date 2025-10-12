"""Strategy base interfaces for GoldenEggBot.

This module defines lightweight ABCs used by individual strategy packages.
They are intentionally minimal until the wider platform is implemented.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd


@dataclass
class Signal:
    """Standardized trading signal."""

    timestamp: pd.Timestamp
    symbol: str
    side: str
    entry_price: float
    stop_price: float
    target_price: float
    confidence: float
    metadata: Dict[str, Any]


class StrategyBase(ABC):
    """Abstract base class all strategies must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable strategy identifier."""

    @property
    @abstractmethod
    def warmup_bars(self) -> int:
        """Number of bars required before `generate_signal` can emit trades."""

    @abstractmethod
    def generate_signal(self, market_data: pd.DataFrame) -> Optional[Signal]:
        """Produce a signal from the latest market data slice."""

    @abstractmethod
    def optimize_parameters(self, historical: pd.DataFrame) -> Dict[str, Any]:
        """Return tuned parameter values based on historical analysis."""
