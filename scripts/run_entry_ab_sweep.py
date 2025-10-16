#!/usr/bin/env python3
import argparse
import os
import sys
import pandas as pd
from typing import Any, Dict, List

# Ensure repository root is on sys.path when running as a standalone script
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.strategies.flag_patterns_extended.config import Config
from src.strategies.flag_patterns_extended.orchestrator import run_experiments
from src.strategies.flag_patterns_extended.tests.evaluate import find_csv, load_csv, build_splits


def make_base_cfg_from_row(row: pd.Series) -> Config:
    cfg = Config()
    # Map param__* columns to Config fields when present
    mapping = {
        "param__pole_lookback_k": "pole_lookback_k",
        "param__atr_len": "atr_len",
        "param__pole_score_min": "pole_score_min",
        "param__min_consolidation_bars": "min_consolidation_bars",
        "param__max_consolidation_bars": "max_consolidation_bars",
        "param__max_retrace_ratio": "max_retrace_ratio",
        "param__parallel_angle_max_deg": "parallel_angle_max_deg",
        "param__channel_slope_cap_deg": "channel_slope_cap_deg",
        "param__width_shrink_ratio_max": "width_shrink_ratio_max",
        "param__apex_pos_factor_max": "apex_pos_factor_max",
        "param__breakout_requires_close": "breakout_requires_close",
        "param__breakout_buffer_atr": "breakout_buffer_atr",
        # entry_type handled via overrides grid
        "param__stop_offset_atr": "stop_offset_atr",
        "param__target_type": "target_type",
        "param__measured_move_factor": "measured_move_factor",
        "param__atr_target_k": "atr_target_k",
    }
    for src, dest in mapping.items():
        if src in row and pd.notna(row[src]):
            val = row[src]
            # Convert True/False strings if needed
            if isinstance(val, str) and val.lower() in ("true", "false"):
                val = val.lower() == "true"
            setattr(cfg, dest, val)
    # Disable scoring for a clean A/B on entry timing
    cfg.enable_scoring = False
    return cfg


def constant_sampler(grid: Dict[str, List[Any]], n_samples: int, seed: int) -> List[Dict[str, Any]]:
    # Return exact combinations for entry_type only
    vals = grid.get("entry_type", ["close", "next_open"])  # default both
    return [{"entry_type": v} for v in vals]


def main():
    ap = argparse.ArgumentParser(description="Run targeted A/B sweep for entry timing using top params.")
    ap.add_argument("--summary", required=True, help="Path to a summary_ranked.csv to pick top row")
    ap.add_argument("--outdir", default="./phase1_outputs", help="Output directory for combined trades")
    ap.add_argument("--tag", default="entry_ab_test", help="Tag prefix for outputs")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--timeframe", default="1h")
    ap.add_argument("--min-train", type=int, default=1000)
    ap.add_argument("--test-size", type=int, default=500)
    ap.add_argument("--step", type=int, default=250)
    ap.add_argument("--apply-filters", action="store_true")
    args = ap.parse_args()

    summ = pd.read_csv(args.summary)
    if summ.empty:
        raise SystemExit("summary is empty; cannot pick top row")
    top = summ.iloc[0]
    base_cfg = make_base_cfg_from_row(top)

    # Load dataset (auto find)
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "strategies", "flag_patterns_extended", "data_samples"))
    csv_path = find_csv(data_dir, args.symbol, args.timeframe)
    if not csv_path:
        raise SystemExit(f"No CSV found in {data_dir}")
    df = load_csv(csv_path)

    # Splits (anchored defaults)
    splits = build_splits(len(df), argparse.Namespace(
        splits="anchored",
        kfold=5,
        purge=10,
        embargo=10,
        test_size=args.test_size,
        step=args.step,
        min_train=args.min_train,
    ))

    # 2-combo grid: entry close vs next_open
    grid = {"entry_type": ["close", "next_open"]}
    tag = args.tag
    res = run_experiments(
        datasets=[(args.symbol, args.timeframe, df)],
        base_cfg=base_cfg,
        param_grid=grid,
        sampler=constant_sampler,
        n_samples=2,
        seed=42,
        splits=splits,
        apply_filters=args.apply_filters,
        scorer=None,
        score_threshold=None,
        outdir=args.outdir,
        tag=tag,
        n_jobs=1,
        per_cell_csv=False,
    )

    combined_path = os.path.join(args.outdir, f"{tag}_combined.csv")
    res.to_csv(combined_path, index=False)
    print(f"Wrote combined -> {combined_path}")


if __name__ == "__main__":
    main()
