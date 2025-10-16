from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as _mp

import pandas as pd

from .config import Config
from .backtest import run_backtest
from .samplers import latin_hypercube
from .splits import Split


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _label_split_side(j_idx: Any, train_set: set, test_set: set) -> str:
    try:
        pos = int(j_idx)
    except (TypeError, ValueError):
        return "other"
    if pos in test_set:
        return "test"
    if pos in train_set:
        return "train"
    return "other"


def _run_one_sample(
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
    base_cfg: Dict[str, Any],
    overrides: Dict[str, Any],
    splits: Optional[List[Split]],
    apply_filters: Optional[bool],
    outdir: str,
    tag: str,
    sample_idx: int,
    per_cell_csv: bool,
    total_samples: Optional[int] = None,
) -> pd.DataFrame:
    # Progress: announce sample start (works in both sequential and parallel modes)
    try:
        if total_samples and total_samples > 0:
            print(f"[progress] Sample {sample_idx}/{int(total_samples)} in progress")
    except Exception:
        pass
    cfg_dict = dict(base_cfg)
    cfg_dict.update(overrides)
    cfg = Config.from_dict(cfg_dict)

    split_list = splits if splits is not None else [None]
    rows: List[pd.DataFrame] = []
    for split_idx, split in enumerate(split_list, start=1):
        if split is not None and (len(split.train_idx) == 0 or len(split.test_idx) == 0):
            continue
        trades = run_backtest(
            df=df,
            cfg=cfg,
            symbol=symbol,
            timeframe=timeframe,
            apply_filters=apply_filters,
        )

        if split is not None and "j1" in trades.columns:
            train_set = set(split.train_idx.tolist())
            test_set = set(split.test_idx.tolist())
            trades["split_side"] = trades["j1"].map(lambda j: _label_split_side(j, train_set, test_set))
        else:
            trades["split_side"] = "all"

        for key, val in overrides.items():
            trades[f"param__{key}"] = val
        trades["orchestrator_tag"] = tag
        trades["sample_idx"] = sample_idx
        trades["split_idx"] = split_idx
        trades["config_json"] = json.dumps(cfg.to_dict(), sort_keys=True)

        if per_cell_csv:
            fname = f"{tag}_{symbol}_{timeframe}_split{split_idx:02d}_s{sample_idx:03d}.csv"
            trades.to_csv(os.path.join(outdir, fname), index=False)
        rows.append(trades)

    return pd.concat(rows, axis=0, ignore_index=True) if rows else pd.DataFrame()


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
    n_jobs: int = 1,
    per_cell_csv: bool = True,
) -> pd.DataFrame:
    """Run parameter experiments across datasets and optional splits."""

    _ensure_dir(outdir)
    grid = param_grid or {}
    combos = sampler(grid, n_samples, seed) if grid else [{}]
    total_samples = len(combos)
    try:
        print(f"[progress] Samples planned: {total_samples}")
    except Exception:
        pass
    results: List[pd.DataFrame] = []

    for symbol, timeframe, df in datasets:
        base_cfg_dict = base_cfg.to_dict()
        if scorer is not None and score_threshold is not None:
            # These are used inside worker via config_json; we pass raw dict and let worker set scorer via cfg fields
            base_cfg_dict = dict(base_cfg_dict)
            # Note: scorer itself might not be picklable; run_backtest doesn't use scorer directly.
            # We only pass enable_scoring/threshold in cfg; scorer gating happens before run_backtest in evaluate warmup.
            base_cfg_dict["enable_scoring"] = True
            base_cfg_dict["scoring_threshold"] = float(score_threshold)

        # Parallelize over samples to reduce DF serialization overhead (df copied per worker)
        if n_jobs and n_jobs > 1:
            max_workers = n_jobs if n_jobs > 0 else (_mp.cpu_count() or 1)
            with ProcessPoolExecutor(max_workers=max_workers) as ex:
                futures = []
                for sample_idx, overrides in enumerate(combos, start=1):
                    # Progress: indicate queuing of work for parallel execution
                    try:
                        print(f"[progress] Queued sample {sample_idx}/{total_samples}")
                    except Exception:
                        pass
                    futures.append(
                        ex.submit(
                            _run_one_sample,
                            symbol,
                            timeframe,
                            df,
                            base_cfg_dict,
                            overrides,
                            splits,
                            apply_filters,
                            outdir,
                            tag,
                            sample_idx,
                            per_cell_csv,
                            total_samples,
                        )
                    )
                completed = 0
                for fut in as_completed(futures):
                    part = fut.result()
                    if not part.empty:
                        results.append(part)
                    completed += 1
                    # Progress: completed count
                    try:
                        print(f"[progress] Completed samples: {completed}/{total_samples}")
                    except Exception:
                        pass
        else:
            for sample_idx, overrides in enumerate(combos, start=1):
                # Progress: per-sample start in sequential mode
                try:
                    print(f"[progress] Sample {sample_idx}/{total_samples} in progress")
                except Exception:
                    pass
                part = _run_one_sample(
                    symbol,
                    timeframe,
                    df,
                    base_cfg_dict,
                    overrides,
                    splits,
                    apply_filters,
                    outdir,
                    tag,
                    sample_idx,
                    per_cell_csv,
                    None,  # suppress inner print to avoid duplicate in sequential mode
                )
                if not part.empty:
                    results.append(part)

    return pd.concat(results, axis=0, ignore_index=True) if results else pd.DataFrame()
