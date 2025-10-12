#!/usr/bin/env python
"""In-sample permutation significance test for Flag Patterns strategy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from ..analysis import evaluate_orders, load_price_data, permutation_distribution, save_metrics, summarise_patterns
from ..config import load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Flag Patterns in-sample permutation test")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--permutations", type=int, default=250)
    parser.add_argument("--data-source", type=str, required=True)
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    data = load_price_data(args.data_source)

    results = evaluate_orders(
        data,
        orders=config.order_scan_range,
        hold_multiplier=config.hold_multiplier,
        use_trendline=config.use_trendline_mode,
    )
    summary = summarise_patterns(results)

    dist = permutation_distribution(
        data,
        orders=config.order_scan_range,
        hold_multiplier=config.hold_multiplier,
        permutations=args.permutations,
        use_trendline=config.use_trendline_mode,
        seed=args.seed,
    )
    observed = summary["total_return"]
    p_value = float((dist >= observed).sum() / max(1, len(dist)))

    summary.update({
        "test": "in_sample_permutation",
        "seed": args.seed,
        "permutations": args.permutations,
        "p_value": p_value,
        "distribution_mean": float(dist.mean()) if len(dist) else 0.0,
        "distribution_std": float(dist.std(ddof=1)) if len(dist) > 1 else 0.0,
    })

    save_metrics(args.artifacts_dir, summary, results)
    (args.artifacts_dir / "permutation_stats.json").write_text(json.dumps({
        "values": dist.tolist(),
        "p_value": p_value,
        "observed": observed,
    }, indent=2))


if __name__ == "__main__":
    main()
