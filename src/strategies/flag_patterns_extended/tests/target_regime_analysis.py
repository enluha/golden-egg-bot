#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ----------------------------- I/O -------------------------------------------

def _ensure_outdir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def load_combined(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [str(c) for c in df.columns]
    # Find a sensible time column for bucketing
    time_col = None
    for c in ("cons_end_time", "entry_time", "breakout_time"):
        if c in df.columns:
            time_col = c
            break
    if time_col:
        df[time_col] = pd.to_datetime(df[time_col], errors="coerce", utc=True)
        df["bucket_month"] = df[time_col].dt.to_period("M").astype(str)
    else:
        df["bucket_month"] = "UNKNOWN"
    return df


def detect_param_columns(df: pd.DataFrame) -> List[str]:
    return [c for c in df.columns if c.startswith("param__")]


# --------------------------- Metrics & Aggregates -----------------------------

def compute_metrics(s: pd.Series) -> Dict[str, float]:
    x = s.dropna().astype(float)
    n = int(x.shape[0])
    if n == 0:
        return dict(n_trades=0, win_rate=0.0, avg_pnl=0.0, std_pnl=0.0, sharpe_like=0.0)
    win_rate = float((x > 0).mean())
    avg = float(x.mean())
    std = float(x.std(ddof=0))
    sharpe_like = (avg / std) * (n ** 0.5) if std > 0 else 0.0
    return dict(n_trades=n, win_rate=win_rate, avg_pnl=avg, std_pnl=std, sharpe_like=sharpe_like)


def bucket_combo_performance(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate per (bucket_month, target_type, combo_key) where combo_key is the tuple of all param__ columns.
    """
    param_cols = detect_param_columns(df)
    if "param__target_type" not in param_cols:
        raise ValueError("Combined CSV is missing 'param__target_type' in param columns.")
    grp_cols = ["bucket_month"] + param_cols
    agg = df.groupby(grp_cols, dropna=False)["pnl_pct"].apply(compute_metrics).apply(pd.Series).reset_index()
    # bring metric columns to consistent numeric types
    for c in ("n_trades", "win_rate", "avg_pnl", "std_pnl", "sharpe_like"):
        agg[c] = pd.to_numeric(agg[c], errors="coerce")
    return agg


def pick_best_per_regime_per_bucket(agg: pd.DataFrame, metric: str, min_trades: int) -> pd.DataFrame:
    """
    For each (bucket_month, target_type), keep the single combo with the highest metric, subject to min_trades.
    """
    d = agg[agg["n_trades"] >= int(min_trades)].copy()
    if d.empty:
        return d
    # sort so head(1) takes the max metric and, as tie-breaker, more trades
    d = d.sort_values(["bucket_month", "param__target_type", metric, "n_trades"],
                      ascending=[True, True, False, False])
    best = d.groupby(["bucket_month", "param__target_type"], dropna=False).head(1).reset_index(drop=True)
    return best


def compare_regimes_per_bucket(best_per_regime: pd.DataFrame, metric: str) -> pd.DataFrame:
    """
    For each month, pivot best-per-regime metrics and declare a winner.
    """
    pv = best_per_regime.pivot(index="bucket_month", columns="param__target_type", values=metric).reset_index()
    # Normalize column names to expected regimes if needed
    cols = {c: c for c in pv.columns}
    pv = pv.rename(columns=cols)
    # compute delta = measured_move - atr_multiple (positive => measured_move better)
    mm = "measured_move"
    am = "atr_multiple"
    if mm not in pv.columns:
        pv[mm] = np.nan
    if am not in pv.columns:
        pv[am] = np.nan
    pv["delta"] = pv.get(mm) - pv.get(am)
    pv["winner"] = np.where(pv[mm].gt(pv[am]), mm,
                     np.where(pv[am].gt(pv[mm]), am, "tie"))
    return pv


# ------------------------------- Plotting ------------------------------------

def plot_winner_timeline(comp: pd.DataFrame, metric: str, outdir: str) -> str:
    """
    Plot both regimes' best-per-month metric as two lines; annotate winners.
    """
    months = comp["bucket_month"].astype(str).tolist()
    x = np.arange(len(months))
    mm = comp.get("measured_move").to_numpy(dtype=float)
    am = comp.get("atr_multiple").to_numpy(dtype=float)

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(x, mm, marker="o", label="measured_move")
    ax.plot(x, am, marker="o", label="atr_multiple")
    # annotate winners
    for i, w in enumerate(comp["winner"].astype(str).tolist()):
        ax.text(i, max(mm[i] if np.isfinite(mm[i]) else 0, am[i] if np.isfinite(am[i]) else 0),
                f"{w}", fontsize=8, ha="center", va="bottom", rotation=0)
    ax.set_xticks(x)
    ax.set_xticklabels(months, rotation=45, ha="right")
    ax.set_ylabel(metric)
    ax.set_title(f"Best-per-regime {metric} by month (winner annotated)")
    ax.legend()
    fig.tight_layout()
    path = os.path.join(outdir, f"winner_timeline_{metric}.png")
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def plot_win_counts(comp: pd.DataFrame, outdir: str) -> str:
    counts = comp["winner"].value_counts(dropna=False)
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.bar(counts.index.astype(str), counts.values)
    ax.set_title("Regime wins per month")
    ax.set_ylabel("# months won")
    fig.tight_layout()
    path = os.path.join(outdir, "winner_counts.png")
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def plot_delta_bar(comp: pd.DataFrame, metric: str, outdir: str) -> str:
    """
    Bar chart of (measured_move - atr_multiple) per month; >0 means measured_move better.
    """
    months = comp["bucket_month"].astype(str).tolist()
    x = np.arange(len(months))
    delta = comp["delta"].to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(12, 3.8))
    ax.bar(x, delta)
    ax.axhline(0.0, color="k", linewidth=1)
    ax.set_xticks(x)
    ax.set_xticklabels(months, rotation=45, ha="right")
    ax.set_ylabel(f"{metric} Δ (MM − ATR)")
    ax.set_title("Per-month advantage (positive → measured_move)")
    fig.tight_layout()
    path = os.path.join(outdir, f"delta_bar_{metric}.png")
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


# ------------------------------- CLI -----------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Model-free target regime comparison per bucket (measured_move vs atr_multiple).")
    ap.add_argument("--combined", required=True, help="Path to combined CSV from run_sweep.py")
    ap.add_argument("--outdir", default="./target_regime", help="Output directory")
    ap.add_argument("--metric", default="sharpe_like", choices=["sharpe_like", "win_rate", "avg_pnl", "median_pnl"])
    ap.add_argument("--min-trades", type=int, default=20, help="Minimum trades per (bucket, combo) to consider")
    args = ap.parse_args()

    _ensure_outdir(args.outdir)
    df = load_combined(args.combined)

    # 1) Aggregate performance per combo within each regime & month
    agg = bucket_combo_performance(df)
    agg_path = os.path.join(args.outdir, "bucket_combo_performance.csv")
    agg.to_csv(agg_path, index=False)

    # 2) Pick the best combo per regime per bucket (subject to min_trades)
    best = pick_best_per_regime_per_bucket(agg, args.metric, args.min_trades)
    best_path = os.path.join(args.outdir, f"best_per_regime_per_bucket_{args.metric}.csv")
    best.to_csv(best_path, index=False)

    # 3) Compare regimes and choose winners per month
    comp = compare_regimes_per_bucket(best, args.metric)
    comp_path = os.path.join(args.outdir, f"regime_winners_{args.metric}.csv")
    comp.to_csv(comp_path, index=False)

    # 4) Plots
    p1 = plot_winner_timeline(comp, args.metric, args.outdir)
    p2 = plot_win_counts(comp, args.outdir)
    p3 = plot_delta_bar(comp, args.metric, args.outdir)

    print("Wrote:")
    print(" ", agg_path)
    print(" ", best_path)
    print(" ", comp_path)
    print(" ", p1)
    print(" ", p2)
    print(" ", p3)


if __name__ == "__main__":
    main()
