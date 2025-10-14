# grid/LH runner + results dataframe/csv

from __future__ import annotations

import itertools
import json
import os
from dataclasses import replace
from typing import Dict, Iterable, List, Any, Tuple, Optional

import pandas as pd

from .config import Config
from .backtest import run_backtest


def product_dict(grid: Dict[str, Iterable[Any]]) -> List[Dict[str, Any]]:
    """
    Cartesian product over a dict of lists -> list of param dicts.
    """
    keys = list(grid.keys())
    vals = [list(v) for v in grid.values()]
    combos = []
    for tup in itertools.product(*vals):
        combos.append({k: v for k, v in zip(keys, tup)})
    return combos


def apply_overrides(cfg: Config, overrides: Dict[str, Any]) -> Config:
    """
    Return a shallow copy of cfg with overrides applied.
    """
    kwargs = cfg.to_dict()
    kwargs.update(overrides)
    return Config.from_dict(kwargs)


def run_sweep(
    df: pd.DataFrame,
    base_cfg: Config,
    grid: Dict[str, Iterable[Any]],
    *,
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    output_dir: Optional[str] = None,
    tag: Optional[str] = None,
) -> pd.DataFrame:
    """
    Run a parameter sweep on a single dataframe.
    Returns a concatenated trades dataframe with config metadata columns.
    If output_dir is provided, writes one CSV per combo and a combined CSV.
    """
    combos = product_dict(grid)
    all_rows: List[pd.DataFrame] = []

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    for i, overrides in enumerate(combos, 1):
        cfg = apply_overrides(base_cfg, overrides)
        trades = run_backtest(df, cfg, symbol=symbol, timeframe=timeframe)
        # Attach metadata
        for k, v in overrides.items():
            trades[f"param__{k}"] = v
        trades["sweep_tag"] = tag or ""
        trades["sweep_idx"] = i
        trades["config_json"] = json.dumps(cfg.to_dict(), sort_keys=True)
        all_rows.append(trades)

        if output_dir:
            fname = f"sweep_{tag or 'run'}_{i:04d}.csv"
            trades.to_csv(os.path.join(output_dir, fname), index=False)

    combined = pd.concat(all_rows, axis=0, ignore_index=True) if all_rows else pd.DataFrame()
    if output_dir and not combined.empty:
        combined.to_csv(os.path.join(output_dir, f"sweep_{tag or 'run'}_combined.csv"), index=False)

    return combined


# ---------------- Convenience: quick Phase-1 grid ----------------

def default_phase1_grid() -> Dict[str, List[Any]]:
    """
    Coarse grid for the starter sweep (Phase-1 core parameters).
    """
    return {
        "pole_lookback_k": [3, 5, 8, 13],
        "atr_len": [10, 14, 20],
        "pole_score_min": [2.0, 3.0, 4.0, 5.0],
        "min_consolidation_bars": [5, 8],
        "max_consolidation_bars": [12, 16],
        "max_retrace_ratio": [0.33, 0.4, 0.5],
        "parallel_angle_max_deg": [5, 8, 10],
        "channel_slope_cap_deg": [8, 12, 15],
        "width_shrink_ratio_max": [0.5, 0.6, 0.7],
        "apex_pos_factor_max": [1.0, 2.0, 3.0],
        "breakout_requires_close": [True, False],
        "breakout_buffer_atr": [0.0, 0.05, 0.1],
        "entry_type": ["close", "next_open"],
        "stop_offset_atr": [0.1, 0.25, 0.4],
        "target_type": ["measured_move"],  # keep simple for the first pass
        "measured_move_factor": [0.8, 1.0, 1.2],
    }
