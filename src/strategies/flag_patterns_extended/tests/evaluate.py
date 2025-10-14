#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from ..config import Config
from ..orchestrator import run_experiments
from ..samplers import latin_hypercube, random_samples
from ..scoring import LogisticScorer
from ..splits import Split, anchored_walk_forward, purged_kfold_indices
from ..sweep import product_dict


# --------------------------- Phase-1 grid (exact) ----------------------------

def phase1_grid() -> Dict[str, Iterable[Any]]:
    return {
        "pole_lookback_k": [3, 5, 8, 13],
        "atr_len": [10, 14, 20],
        "pole_score_min": [2.0, 3.0, 4.0, 5.0],
        "min_consolidation_bars": [3, 5, 8],
        "max_consolidation_bars": [12, 16, 20],
        "max_retrace_ratio": [0.33, 0.40, 0.50],
        "parallel_angle_max_deg": [5, 8, 10],
        "channel_slope_cap_deg": [8, 12, 15],
        "width_shrink_ratio_max": [0.5, 0.6, 0.7],
        "apex_pos_factor_max": [1.0, 2.0, 3.0],
        "breakout_requires_close": [True, False],
        "breakout_buffer_atr": [0.0, 0.05, 0.1, 0.2],
        "entry_type": ["close", "next_open"],
        "stop_offset_atr": [0.1, 0.25, 0.4],
        "target_type": ["measured_move", "atr_multiple"],
        "measured_move_factor": [0.8, 1.0, 1.2],
        "atr_target_k": [1.5, 2.0, 3.0],
    }


# ------------------------- Data loading / download ---------------------------

def timeframe_to_seconds(timeframe: str) -> Optional[int]:
    tf_raw = timeframe.strip()
    tf = tf_raw.lower()
    if tf.isdigit():
        return int(tf)
    if tf.endswith("ms") and tf[:-2].isdigit():
        return int(int(tf[:-2]) / 1000)
    if tf.endswith("s") and tf[:-1].isdigit():
        return int(tf[:-1])
    if tf.endswith("m") and tf[:-1].isdigit():
        if tf_raw.endswith("M") and not tf_raw.endswith("m"):
            return int(tf[:-1]) * 2_592_000
        return int(tf[:-1]) * 60
    if tf.endswith("h") and tf[:-1].isdigit():
        return int(tf[:-1]) * 3_600
    if tf.endswith("d") and tf[:-1].isdigit():
        return int(tf[:-1]) * 86_400
    if tf.endswith("w") and tf[:-1].isdigit():
        return int(tf[:-1]) * 604_800
    if tf.endswith("mo") and tf[:-2].isdigit():
        return int(tf[:-2]) * 2_592_000
    return None


def find_csv(
    data_dir: str,
    symbol: str,
    timeframe: str,
    *,
    interval_seconds: Optional[int] = None,
) -> Optional[str]:
    if not os.path.isdir(data_dir):
        return None
    candidates = [fn for fn in os.listdir(data_dir) if fn.lower().endswith(".csv")]
    if not candidates:
        return None

    seconds = interval_seconds if interval_seconds is not None else timeframe_to_seconds(timeframe)
    tokens = [symbol.lower(), timeframe.lower()]
    if seconds is not None:
        tokens.extend([str(seconds), f"{seconds}_"])

    def score(name: str) -> int:
        lower = name.lower()
        return sum(1 for token in tokens if token and token in lower)

    best = max(candidates, key=lambda name: (score(name), -len(name)))
    return os.path.join(data_dir, best)


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "date" in df.columns:
        try:
            df["date"] = pd.to_datetime(df["date"], unit="ms", errors="ignore")
        except Exception:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.set_index("date")
    df.columns = [col.lower() for col in df.columns]
    for col in ("open", "high", "low", "close"):
        if col not in df.columns:
            raise ValueError(f"CSV missing required column '{col}'")
    return df


def try_download_data(
    data_dir: str,
    symbol: str,
    timeframe: str,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    interval_seconds: Optional[int] = None,
) -> Optional[str]:
    rel_path = os.path.join(os.path.dirname(__file__), "..", "data_samples", "download_data_sample.py")
    dl_path = os.path.abspath(rel_path)
    if not os.path.exists(dl_path):
        return None

    spec = importlib.util.spec_from_file_location("download_data_sample", dl_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[arg-type]

    seconds = interval_seconds if interval_seconds is not None else timeframe_to_seconds(timeframe)
    cli_args: List[str] = ["--symbol", symbol]
    if seconds is not None:
        cli_args.extend(["--interval", str(seconds)])
    if start_date:
        cli_args.extend(["--start", start_date])
    if end_date:
        cli_args.extend(["--end", end_date])
    cli_args.extend(["--output-dir", os.path.abspath(data_dir)])

    for func_name in ("main", "download_data", "run"):
        if hasattr(module, func_name):
            try:
                print(f"[download] invoking {func_name} for {symbol} {timeframe}")
                func = getattr(module, func_name)
                if func_name == "main":
                    func(cli_args)
                else:
                    func()
                break
            except SystemExit:
                break
            except Exception as exc:
                print(f"[download] {func_name} failed: {exc}")
    return find_csv(data_dir, symbol, timeframe, interval_seconds=seconds)


# ----------------------------- Splits builder --------------------------------

def build_splits(n: int, args: argparse.Namespace) -> Optional[List[Split]]:
    if args.splits == "none":
        return None
    if args.splits == "purged":
        return purged_kfold_indices(
            n=n,
            n_splits=args.kfold,
            purge=args.purge,
            embargo=args.embargo,
        )
    if args.splits == "anchored":
        return anchored_walk_forward(
            n=n,
            test_size=args.test_size,
            step=args.step,
            min_train=args.min_train,
            purge=args.purge,
            embargo=args.embargo,
        )
    raise ValueError(f"Unknown splits mode: {args.splits}")


# ------------------------------- Main runner ---------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Phase-1 Core: geometry & pole research driver (BTCUSDT).")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--csv", default=None, help="Path to an OHLCV CSV (overrides auto-discovery).")
    parser.add_argument(
        "--data-dir",
        default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data_samples")),
    )
    parser.add_argument("--download", action="store_true", help="Attempt to download data if missing.")
    parser.add_argument("--start-date", default=None, help="Optional start date (YYYY-MM-DD) for download.")
    parser.add_argument("--end-date", default=None, help="Optional end date (YYYY-MM-DD) for download.")
    parser.add_argument("--interval-seconds", type=int, default=None, help="Explicit interval seconds override for downloader lookups.")

    parser.add_argument("--splits", choices=["none", "purged", "anchored"], default="anchored")
    parser.add_argument("--kfold", type=int, default=5)
    parser.add_argument("--purge", type=int, default=10)
    parser.add_argument("--embargo", type=int, default=10)
    parser.add_argument("--test-size", type=int, default=500)
    parser.add_argument("--step", type=int, default=250)
    parser.add_argument("--min-train", type=int, default=1000)

    parser.add_argument("--sampler", choices=["grid", "lhs", "random"], default="grid")
    parser.add_argument("--samples", type=int, default=128)
    parser.add_argument("--seed", type=int, default=42)

    parser.add_argument("--apply-filters", action="store_true")
    parser.add_argument("--train-scorer", action="store_true")
    parser.add_argument("--score-threshold", type=float, default=0.55)

    parser.add_argument("--archive", action="store_true")
    parser.add_argument("--archive-dir", default="./archive_phase1")
    parser.add_argument("--archive-prob", type=float, default=0.05)

    parser.add_argument("--outdir", default="./phase1_outputs")
    parser.add_argument("--tag", default="phase1_btc1h")

    args = parser.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    overall_start = time.perf_counter()

    steps: List[str] = [
        "Locate or download dataset",
        "Load dataset into DataFrame",
        "Build evaluation splits",
    ]
    if args.train_scorer:
        steps.extend([
            "Run warmup sweep (no scoring)",
            "Train logistic scorer",
        ])
    steps.extend([
        "Run main experiments",
        "Persist combined CSV output",
    ])

    total_steps = len(steps)
    step_counter = 0
    current_desc = ""
    current_start = 0.0

    def step_start(description: str) -> None:
        nonlocal step_counter, current_desc, current_start
        step_counter += 1
        current_desc = description
        current_start = time.perf_counter()
        print(f"[progress] Step {step_counter}/{total_steps} started: {description}")

    def step_end(message: Optional[str] = None) -> None:
        nonlocal current_desc, current_start
        elapsed = time.perf_counter() - current_start if current_start else 0.0
        final_desc = message or current_desc
        print(f"[progress] Step {step_counter}/{total_steps} completed in {elapsed:.2f}s: {final_desc}")

    interval_seconds = args.interval_seconds or timeframe_to_seconds(args.timeframe)

    step_start("Locate or download dataset")
    csv_path = args.csv or find_csv(
        args.data_dir,
        args.symbol,
        args.timeframe,
        interval_seconds=interval_seconds,
    )
    if not csv_path and args.download:
        csv_path = try_download_data(
            args.data_dir,
            args.symbol,
            args.timeframe,
            start_date=args.start_date,
            end_date=args.end_date,
            interval_seconds=interval_seconds,
        )
        if not csv_path:
            csv_path = find_csv(
                args.data_dir,
                args.symbol,
                args.timeframe,
                interval_seconds=interval_seconds,
            )
    if not csv_path:
        step_end("Failed to locate dataset")
        raise SystemExit(f"No CSV found in {args.data_dir}. Provide --csv or use --download.")
    step_end(f"Dataset ready at {csv_path}")

    step_start("Load dataset into DataFrame")
    df = load_csv(csv_path)
    step_end(f"Loaded {len(df)} rows with columns {', '.join(df.columns)}")

    step_start("Build evaluation splits")
    splits = build_splits(len(df), args)
    split_count = 0 if splits is None else len(splits)
    step_end(f"Mode={args.splits}; windows={split_count}")

    base_cfg = Config()
    base_cfg.enable_filters = bool(args.apply_filters)
    if args.archive:
        base_cfg.archive_dir = args.archive_dir
        base_cfg.archive_prob = args.archive_prob

    grid = phase1_grid()
    grid_combos = product_dict(grid)
    if args.sampler == "grid":
        def grid_sampler(_: Dict[str, Iterable[Any]], __: int, ___: int) -> List[Dict[str, Any]]:
            return grid_combos

        sampler = grid_sampler
        n_samples = len(grid_combos)
    elif args.sampler == "lhs":
        sampler = latin_hypercube
        n_samples = int(args.samples)
    else:
        sampler = random_samples
        n_samples = int(args.samples)

    datasets = [(args.symbol, args.timeframe, df)]

    scorer = None
    if args.train_scorer:
        step_start("Run warmup sweep (no scoring)")
        warm_tag = args.tag + "_warmup"
        warm_df = run_experiments(
            datasets=datasets,
            base_cfg=base_cfg,
            param_grid=grid,
            sampler=sampler,
            n_samples=n_samples,
            seed=args.seed,
            splits=splits,
            apply_filters=args.apply_filters,
            outdir=args.outdir,
            tag=warm_tag,
        )
        step_end(f"Warmup sweep stored {len(warm_df)} trades (tag {warm_tag})")

        step_start("Train logistic scorer")
        feat_cols = [col for col in warm_df.columns if col.startswith(("geom_", "theta_", "width_", "retrace_", "atr_frac_price", "pole_"))]
        train_frame = LogisticScorer.make_training_frame(
            warm_df[warm_df.get("split_side", "all").isin(["train", "all"])],
            feat_cols,
        )
        if len(train_frame) >= 100:
            scorer = LogisticScorer(feature_cols=feat_cols, l2=1e-2, max_iter=600, lr=0.05)
            scorer.fit(train_frame, label_col="label")
            step_end(f"Trained logistic scorer on {len(train_frame)} labeled rows")
        else:
            step_end(f"Skipped logistic scorer training; only {len(train_frame)} labeled rows available")

    main_tag = args.tag + ("_scored" if scorer is not None else "")
    if scorer is not None:
        base_cfg.scorer = scorer
        base_cfg.enable_scoring = True
        base_cfg.scoring_threshold = args.score_threshold

    step_start("Run main experiments")
    all_rows = run_experiments(
        datasets=datasets,
        base_cfg=base_cfg,
        param_grid=grid,
        sampler=sampler,
        n_samples=n_samples,
        seed=args.seed,
        splits=splits,
        apply_filters=args.apply_filters,
        outdir=args.outdir,
        tag=main_tag,
    )
    step_end(f"Main experiments generated {len(all_rows)} trades (tag {main_tag})")

    step_start("Persist combined CSV output")
    combined_path = os.path.join(args.outdir, f"{main_tag}_combined.csv")
    all_rows.to_csv(combined_path, index=False)
    step_end(f"Combined trades saved to {combined_path}")

    total_elapsed = time.perf_counter() - overall_start
    print(f"[progress] Phase-1 workflow completed in {total_elapsed:.2f}s")

    print("\nNext steps:")
    print("  - Summaries  : python -m src.strategies.flag_patterns_extended.tests.summarize_sweep --combined", combined_path, "--outdir ./summary")
    print("  - Order corr : python -m src.strategies.flag_patterns_extended.tests.order_correlation --combined", combined_path, "--outdir ./order_corr")
    print("  - Target HH  : python -m src.strategies.flag_patterns_extended.tests.target_regime_analysis --combined", combined_path, "--outdir ./target_regime")
    print("  - Plots (gallery): integrate plots.plot_gallery() on filtered subsets for QC")
    return 0


if __name__ == "__main__":
    sys.exit(main())
