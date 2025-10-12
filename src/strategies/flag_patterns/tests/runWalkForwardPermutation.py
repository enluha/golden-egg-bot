#!/usr/bin/env python
"""Walk-forward permutation validation for Flag Patterns strategy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..analysis import (
    evaluate_orders,
    load_price_data,
    permutation_distribution,
    summarise_patterns,
    walkforward_slices,
)
from ..config import load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Flag Patterns walk-forward permutation validation")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--window", type=str, default="180d")
    parser.add_argument("--step", type=str, default="30d")
    parser.add_argument("--permutations", type=int, default=100)
    parser.add_argument("--data-source", type=str, required=True)
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rng = np.random.default_rng(args.seed)
    config = load_config(args.config)
    data = load_price_data(args.data_source)

    window = pd.Timedelta(args.window)
    step = pd.Timedelta(args.step)
    slices = walkforward_slices(data, window=window, step=step)

    window_results = []
    for idx, window_df in enumerate(slices):
        results = evaluate_orders(
            window_df,
            orders=config.order_scan_range,
            hold_multiplier=config.hold_multiplier,
            use_trendline=config.use_trendline_mode,
        )
        summary = summarise_patterns(results)
        dist = permutation_distribution(
            window_df,
            orders=config.order_scan_range,
            hold_multiplier=config.hold_multiplier,
            permutations=args.permutations,
            use_trendline=config.use_trendline_mode,
            seed=int(rng.integers(0, 2**32 - 1)),
        )
        p_value = float((dist >= summary["total_return"]).sum() / max(1, len(dist)))
        summary.update({
            "window_index": idx,
            "start": window_df.index.min().isoformat(),
            "end": window_df.index.max().isoformat(),
            "permutations": args.permutations,
            "p_value": p_value,
            "distribution_mean": float(dist.mean()) if len(dist) else 0.0,
            "distribution_std": float(dist.std(ddof=1)) if len(dist) > 1 else 0.0,
        })
        window_results.append(summary)

    artifacts_dir = args.artifacts_dir
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "walkforward_permutation.json").write_text(json.dumps(window_results, indent=2))

    overall = {
        "test": "walk_forward_permutation",
        "seed": args.seed,
        "windows": len(window_results),
        "window": args.window,
        "step": args.step,
        "permutations": args.permutations,
    }
    if window_results:
        counts = np.array([item["count"] for item in window_results], dtype=float)
        weights = np.where(counts > 0, counts, 1.0)
        overall.update({
            "count": int(counts.sum()),
            "avg_p_value": float(np.mean([item["p_value"] for item in window_results])),
            "win_rate": float(np.average([item["win_rate"] for item in window_results], weights=weights)),
            "avg_return": float(np.average([item["avg_return"] for item in window_results], weights=weights)),
            "total_return": float(sum(item["total_return"] for item in window_results)),
        })
    else:
        overall.update({"count": 0, "avg_p_value": 1.0, "win_rate": 0.0, "avg_return": 0.0, "total_return": 0.0})

    (artifacts_dir / "summary.json").write_text(json.dumps(overall, indent=2))


if __name__ == "__main__":
    main()
