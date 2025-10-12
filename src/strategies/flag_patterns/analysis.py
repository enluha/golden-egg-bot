"""Shared analysis utilities for the Flag Patterns strategy.

These helpers wrap the upstream TechnicalAnalysisAutomation modules while exposing
metrics and artifacts in a deterministic, reproducible way for GoldenEggBot tests.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

import numpy as np
import pandas as pd

from .upstream.flags_pennants import FlagPattern, find_flags_pennants_pips, find_flags_pennants_trendline
from .upstream.bar_permute import get_permutation


@dataclass
class PatternReturns:
    order: int
    side: str
    count: int
    win_rate: float
    average_return: float
    total_return: float


def load_price_data(source: str) -> pd.DataFrame:
    """Load OHLC data from a CSV or raise NotImplementedError for unsupported sources."""

    if source.startswith("csv:"):
        path = Path(source.split(":", 1)[1]).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        df = pd.read_csv(path)
    else:
        raise NotImplementedError("Only csv:<path> data sources are supported in this phase")

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
        df = df.set_index("date")
    elif "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, unit="s", errors="coerce")
        df = df.set_index("timestamp")

    required_cols = {"open", "high", "low", "close"}
    missing = required_cols.difference(df.columns)
    if missing:
        raise ValueError(f"Data source missing columns: {sorted(missing)}")

    df = df.sort_index().astype(float)
    df = df[~df.index.duplicated(keep="last")]
    return df


def _evaluate_flag_set(patterns: Iterable[FlagPattern], data: np.ndarray, hold_multiplier: float, side: str) -> Tuple[int, float, float, float]:
    count = 0
    wins = 0
    returns: List[float] = []

    for pattern in patterns:
        hold_period = max(1, int(pattern.flag_width * hold_multiplier))
        exit_index = min(len(data) - 1, pattern.conf_x + hold_period)
        if side == "LONG":
            entry = data[pattern.conf_x]
            exit_price = data[exit_index]
            ret = exit_price - entry
        else:
            entry = data[pattern.conf_x]
            exit_price = data[exit_index]
            ret = entry - exit_price

        count += 1
        returns.append(ret)
        if ret > 0:
            wins += 1

    if count == 0:
        return 0, 0.0, 0.0, 0.0

    returns_arr = np.array(returns, dtype=float)
    win_rate = wins / count
    average = float(returns_arr.mean())
    total = float(returns_arr.sum())
    return count, win_rate, average, total


def evaluate_orders(
    df: pd.DataFrame,
    orders: Iterable[int],
    hold_multiplier: float,
    use_trendline: bool = False,
) -> List[PatternReturns]:
    """Aggregate performance metrics for each order setting."""

    log_prices = np.log(df["close"].to_numpy(dtype=float))
    results: List[PatternReturns] = []

    for order in orders:
        if use_trendline:
            bull_flags, bear_flags, bull_pennants, bear_pennants = find_flags_pennants_trendline(log_prices, order)
        else:
            bull_flags, bear_flags, bull_pennants, bear_pennants = find_flags_pennants_pips(log_prices, order)

        bull_count, bull_wr, bull_avg, bull_total = _evaluate_flag_set(bull_flags, log_prices, hold_multiplier, "LONG")
        bear_count, bear_wr, bear_avg, bear_total = _evaluate_flag_set(bear_flags, log_prices, hold_multiplier, "SHORT")

        results.append(PatternReturns(order=order, side="BULL_FLAG", count=bull_count, win_rate=bull_wr, average_return=bull_avg, total_return=bull_total))
        results.append(PatternReturns(order=order, side="BEAR_FLAG", count=bear_count, win_rate=bear_wr, average_return=bear_avg, total_return=bear_total))

    return results


def summarise_patterns(patterns: List[PatternReturns]) -> dict:
    if not patterns:
        return {"count": 0, "win_rate": 0.0, "avg_return": 0.0, "total_return": 0.0}

    df = pd.DataFrame([p.__dict__ for p in patterns])
    total_count = df["count"].sum()
    win_rate = float((df["win_rate"] * df["count"]).sum() / max(1, total_count))
    avg_return = float((df["average_return"] * df["count"]).sum() / max(1, total_count))
    total_return = float(df["total_return"].sum())
    return {
        "count": int(total_count),
        "win_rate": win_rate,
        "avg_return": avg_return,
        "total_return": total_return,
    }


def save_metrics(path: Path, summary: dict, detailed: List[PatternReturns]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "metrics.json").write_text(json.dumps(summary, indent=2))
    df = pd.DataFrame([p.__dict__ for p in detailed])
    df.to_csv(path / "patterns.csv", index=False)


def permutation_distribution(
    df: pd.DataFrame,
    orders: Iterable[int],
    hold_multiplier: float,
    permutations: int,
    use_trendline: bool = False,
    seed: int = 0,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base_df = df[["open", "high", "low", "close"]]
    totals: List[float] = []
    for i in range(permutations):
        perm_seed = int(rng.integers(0, 2**32 - 1))
        permuted = get_permutation(base_df, seed=perm_seed)
        results = evaluate_orders(permuted, orders, hold_multiplier, use_trendline)
        totals.append(summarise_patterns(results)["total_return"])
    return np.array(totals, dtype=float)


def walkforward_slices(df: pd.DataFrame, window: pd.Timedelta, step: pd.Timedelta) -> List[pd.DataFrame]:
    if len(df) == 0:
        return []

    slices: List[pd.DataFrame] = []
    start = df.index.min()
    end = df.index.max()
    current_start = start
    while current_start + window <= end:
        current_end = current_start + window
        window_df = df.loc[current_start:current_end]
        if len(window_df) > 0:
            slices.append(window_df)
        current_start += step
    return slices

