from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from .config import Config
from .backtest import run_backtest
from .samplers import latin_hypercube
from .splits import Split


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def run_experiments(
    datasets: List[Tuple[str, str, pd.DataFrame]],
    base_cfg: Config,
    param_grid: Optional[Dict[str, Iterable[Any]]] = None,
    *,
    sampler: Callable[[Dict[str, Iterable[Any]], int, int], List[Dict[str, Any]]] = latin_hypercube,
    n_samples: int = 64,
    seed: int = 42,
    splits: Optional[List[Split]] = None,
    apply_filters: Optional[bool] = None,
    scorer: Optional[Any] = None,
    score_threshold: Optional[float] = None,
    outdir: str = "./orchestrator_outputs",
    tag: str = "exp",
) -> pd.DataFrame:
    """Run parameter experiments across datasets and optional splits."""

    _ensure_dir(outdir)
    grid = param_grid or {}
    combos = sampler(grid, n_samples, seed) if grid else [{}]
    results: List[pd.DataFrame] = []

    for symbol, timeframe, df in datasets:
        split_list = splits if splits is not None else [None]
        for split_idx, split in enumerate(split_list, start=1):
            if split is not None and (len(split.train_idx) == 0 or len(split.test_idx) == 0):
                continue
            train_set = set(split.train_idx.tolist()) if split is not None else set()
            test_set = set(split.test_idx.tolist()) if split is not None else set()

            for sample_idx, overrides in enumerate(combos, start=1):
                cfg_dict = base_cfg.to_dict()
                cfg_dict.update(overrides)
                cfg = Config.from_dict(cfg_dict)
                if scorer is not None and score_threshold is not None:
                    cfg.scorer = scorer
                    cfg.enable_scoring = True
                    cfg.scoring_threshold = score_threshold
                trades = run_backtest(
                    df=df,
                    cfg=cfg,
                    symbol=symbol,
                    timeframe=timeframe,
                    apply_filters=apply_filters,
                )

                if split is not None and "j1" in trades.columns:
                    def _label(j_idx: Any) -> str:
                        try:
                            pos = int(j_idx)
                        except (TypeError, ValueError):
                            return "other"
                        if pos in train_set:
                            return "train"
                        if pos in test_set:
                            return "test"
                        return "other"

                    trades["split_side"] = trades["j1"].map(_label)
                else:
                    trades["split_side"] = "all"

                for key, val in overrides.items():
                    trades[f"param__{key}"] = val

                trades["orchestrator_tag"] = tag
                trades["sample_idx"] = sample_idx
                trades["split_idx"] = split_idx

                cfg_json = json.dumps(cfg.to_dict(), sort_keys=True)
                trades["config_json"] = cfg_json

                fname = f"{tag}_{symbol}_{timeframe}_split{split_idx:02d}_s{sample_idx:03d}.csv"
                trades.to_csv(os.path.join(outdir, fname), index=False)
                results.append(trades)

    return pd.concat(results, axis=0, ignore_index=True) if results else pd.DataFrame()
