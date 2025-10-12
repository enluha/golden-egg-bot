#!/usr/bin/env python
"""Baseline in-sample excellence test for Flag Patterns strategy.

Evaluates historical performance using vendored TechnicalAnalysisAutomation logic
and writes deterministic artifacts for auditability.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from ..analysis import evaluate_orders, load_price_data, save_metrics, summarise_patterns
from ..config import load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Flag Patterns in-sample excellence test")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--data-source", type=str, required=True, help="Data source string, e.g. csv:/path/to/file.csv")
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=None, help="Optional YAML config override")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    np.random.seed(args.seed)
    config = load_config(args.config)
    data = load_price_data(args.data_source)

    results = evaluate_orders(
        data,
        orders=config.order_scan_range,
        hold_multiplier=config.hold_multiplier,
        use_trendline=config.use_trendline_mode,
    )
    summary = summarise_patterns(results)
    summary.update({
        "test": "in_sample_excellence",
        "seed": args.seed,
        "data_source": args.data_source,
    })
    save_metrics(args.artifacts_dir, summary, results)
    (args.artifacts_dir / "summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
