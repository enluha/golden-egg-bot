#!/usr/bin/env python
"""Walk-forward validation for Flag Patterns strategy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..analysis import evaluate_orders, load_price_data, summarise_patterns, walkforward_slices
from ..config import load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Flag Patterns walk-forward validation")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--window", type=str, default="180d")
    parser.add_argument("--step", type=str, default="30d")
    parser.add_argument("--data-source", type=str, required=True)
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    np.random.seed(args.seed)
    config = load_config(args.config)
    data = load_price_data(args.data_source)

    window = pd.Timedelta(args.window)
    step = pd.Timedelta(args.step)
    slices = walkforward_slices(data, window=window, step=step)

    window_summaries = []
    detailed_rows = []
    for idx, window_df in enumerate(slices):
        results = evaluate_orders(
            window_df,
            orders=config.order_scan_range,
            hold_multiplier=config.hold_multiplier,
            use_trendline=config.use_trendline_mode,
        )
        summary = summarise_patterns(results)
        summary.update({
            "window_index": idx,
            "start": window_df.index.min().isoformat(),
            "end": window_df.index.max().isoformat(),
        })
        window_summaries.append(summary)
        for row in results:
            detailed = row.__dict__.copy()
            detailed["window_index"] = idx
            detailed_rows.append(detailed)

    artifacts_dir = args.artifacts_dir
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "walkforward_windows.json").write_text(json.dumps(window_summaries, indent=2))
    if detailed_rows:
        pd.DataFrame(detailed_rows).to_csv(artifacts_dir / "patterns.csv", index=False)
    else:
        (artifacts_dir / "patterns.csv").write_text("")

    overall = {
        "test": "walk_forward",
        "seed": args.seed,
        "window": args.window,
        "step": args.step,
        "windows": len(window_summaries),
    }
    if window_summaries:
        counts = np.array([item["count"] for item in window_summaries], dtype=float)
        weights = np.where(counts > 0, counts, 1.0)
        overall.update({
            "count": int(counts.sum()),
            "win_rate": float(np.average([item["win_rate"] for item in window_summaries], weights=weights)),
            "avg_return": float(np.average([item["avg_return"] for item in window_summaries], weights=weights)),
            "total_return": float(sum(item["total_return"] for item in window_summaries)),
        })
    else:
        overall.update({"count": 0, "win_rate": 0.0, "avg_return": 0.0, "total_return": 0.0})

    (artifacts_dir / "summary.json").write_text(json.dumps(overall, indent=2))


if __name__ == "__main__":
    main()
