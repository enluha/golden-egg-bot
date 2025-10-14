# kicks off parameter sweeps

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from typing import Dict, Iterable, Any, List

import pandas as pd

from ..config import Config
from ..backtest import run_backtest
from ..sweep import product_dict


def phase1_grid() -> Dict[str, Iterable[Any]]:
    """Phase-1 core parameter grid (as requested)."""
    return {
        "pole_lookback_k": [3, 5, 8, 13],
        "atr_len": [10, 14, 20],
        "pole_score_min": [2.0, 3.0, 4.0, 5.0],
        "pivot_method": ["PIP"],
        "pip_order": [4, 6, 8, 10, 12, 16],
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
        "enable_filters": [False, True],
    }


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Accept common schemas; normalize if we see a 'date' column
    if "date" in df.columns:
        try:
            df["date"] = pd.to_datetime(df["date"], unit="ms", errors="ignore")
        except Exception:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.set_index("date")
    # Ensure required columns exist
    required = {"open", "high", "low", "close"}
    missing = required - set(c.lower() for c in df.columns)
    if missing:
        raise ValueError(f"CSV missing required OHLC columns: {missing}")
    # Normalize column names to lower-case
    df.columns = [c.lower() for c in df.columns]
    return df


def metrics_from_trades(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"n_trades": 0, "win_rate": 0.0, "avg_pnl": 0.0, "median_pnl": 0.0, "sharpe_like": 0.0}
    vals = trades["pnl_pct"].dropna()
    n = len(vals)
    wins = (vals > 0).sum()
    mean = float(vals.mean()) if n else 0.0
    median = float(vals.median()) if n else 0.0
    std = float(vals.std(ddof=0)) if n else 0.0
    sharpe_like = (mean / std) * (n**0.5) if std > 0 else 0.0
    return {"n_trades": int(n), "win_rate": float(wins) / n if n else 0.0, "avg_pnl": mean, "median_pnl": median, "sharpe_like": sharpe_like}


def main():
    ap = argparse.ArgumentParser(description="Phase-1 parameter sweep runner")
    ap.add_argument("--csv", required=True, help="Path to OHLCV CSV (e.g., /src/strategies/data_samples/BTCUSDT_1h.csv)")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--timeframe", default="1h")
    ap.add_argument("--outdir", default="./outputs", help="Directory for per-combo CSVs and combined outputs")
    ap.add_argument("--tag", default=None, help="Run tag for filenames")
    ap.add_argument("--max-combos", type=int, default=None, help="Optionally cap number of combos for quick runs")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    df = load_csv(args.csv)

    base_cfg = Config()  # starter defaults
    grid = phase1_grid()
    combos = product_dict(grid)
    if args.max_combos is not None:
        combos = combos[: args.max_combos]

    combined_rows: List[pd.DataFrame] = []
    skipped = 0
    for i, ov in enumerate(combos, 1):
        cfg_dict = base_cfg.to_dict()
        cfg_dict.update(ov)
        cfg = Config.from_dict(cfg_dict)

        # Skip mutually inconsistent combos (e.g., measured_move_factor is irrelevant when target_type=atr_multiple)
        if cfg.target_type == "atr_multiple" and cfg.atr_target_k is None:
            continue

        try:
            trades = run_backtest(df, cfg, symbol=args.symbol, timeframe=args.timeframe)
        except Exception as e:
            print(f"[ERR  {i:04d}] {e} | overrides={ov}")
            continue

        # Attach meta
        for k, v in ov.items():
            trades[f"param__{k}"] = v
        trades["sweep_idx"] = i
        trades["symbol"] = args.symbol
        trades["timeframe"] = args.timeframe
        trades["config_json"] = json.dumps(cfg.to_dict(), sort_keys=True)

        # Save per-combo file
        tag = args.tag or datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        out_csv = os.path.join(args.outdir, f"phase1_{tag}_{i:04d}.csv")
        trades.to_csv(out_csv, index=False)

        # Summaries
        summ = metrics_from_trades(trades)
        with open(os.path.join(args.outdir, f"phase1_{tag}_{i:04d}_metrics.json"), "w") as f:
            json.dump(summ, f, indent=2)

        combined_rows.append(trades)

    combined = pd.concat(combined_rows, axis=0, ignore_index=True) if combined_rows else pd.DataFrame()
    tag = args.tag or datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    combined_path = os.path.join(args.outdir, f"phase1_{tag}_combined.csv")
    combined.to_csv(combined_path, index=False)
    print(f"Saved combined trades -> {combined_path}; combos={len(combos)}, skipped={skipped}, rows={len(combined)}")


if __name__ == "__main__":
    main()
