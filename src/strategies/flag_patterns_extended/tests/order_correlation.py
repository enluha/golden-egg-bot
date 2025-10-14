#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ---------- utils ----------

def _param_cols(df: pd.DataFrame) -> List[str]:
    return [c for c in df.columns if c.startswith("param__")]

def _has(col: str, df: pd.DataFrame) -> bool:
    return col in df.columns and df[col].notna().any()

def _spearman(x: pd.Series, y: pd.Series) -> float:
    xr = x.rank(method="average")
    yr = y.rank(method="average")
    # Pearson of ranks
    xc = (xr - xr.mean()) / xr.std(ddof=0)
    yc = (yr - yr.mean()) / yr.std(ddof=0)
    if np.isfinite(xc).all() and np.isfinite(yc).all() and xc.std(ddof=0) > 0 and yc.std(ddof=0) > 0:
        return float((xc * yc).mean())
    return np.nan

def _mutual_info_continuous_discrete(x: pd.Series, y: pd.Series, bins: int = 10) -> float:
    # Fallback MI via histogram binning; robust enough for scouting
    x = pd.to_numeric(x, errors="coerce").dropna()
    y = pd.to_numeric(y, errors="coerce").dropna()
    n = min(len(x), len(y))
    if n < 50:
        return np.nan
    x = x.iloc[:n].to_numpy()
    y = y.iloc[:n].to_numpy()
    c_xy, _, _ = np.histogram2d(x, y, bins=bins)
    p_xy = c_xy / c_xy.sum()
    p_x = p_xy.sum(axis=1, keepdims=True)
    p_y = p_xy.sum(axis=0, keepdims=True)
    nz = p_xy > 0
    mi = float((p_xy[nz] * (np.log(p_xy[nz]) - np.log(p_x[nz.any(axis=1)][:, 0][:, None]) - np.log(p_y[0, nz.any(axis=0)][None, :])).sum()))
    return mi

def _ensure_outdir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


# ---------- load & bucketing ----------

def load_combined(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    # normalize column names
    df.columns = [str(c) for c in df.columns]
    # pick a time column for bucketing
    time_col = None
    for c in ("cons_end_time", "entry_time", "breakout_time"):
        if c in df.columns and pd.notna(df[c]).any():
            time_col = c
            break
    if time_col:
        df[time_col] = pd.to_datetime(df[time_col], errors="coerce", utc=True)
        df["bucket_month"] = df[time_col].dt.to_period("M").astype(str)
    else:
        df["bucket_month"] = "UNKNOWN"
    return df


# ---------- analysis ----------

def event_level_correlation(df: pd.DataFrame, outdir: str) -> pd.DataFrame:
    """
    Spearman correlation between pip_order and regime features / outcomes at the EVENT level.
    """
    if not _has("param__pip_order", df):
        raise ValueError("param__pip_order not found. Add pip_order to the sweep grid.")

    feats = [c for c in df.columns if c.startswith("feat_regime_")]
    targets = ["pnl_pct"]
    fields = feats + targets

    results = []
    for c in fields:
        rho = _spearman(df["param__pip_order"], df[c])
        mi = _mutual_info_continuous_discrete(df[c], df["param__pip_order"], bins=10)
        results.append({"feature": c, "spearman_rho": rho, "mutual_info": mi})

    res = pd.DataFrame(results).sort_values(by="spearman_rho", ascending=False)
    res.to_csv(os.path.join(outdir, "event_level_corr.csv"), index=False)

    # Bar plot
    fig, ax = plt.subplots(figsize=(10, 6))
    top = res.head(12)
    ax.barh(top["feature"], top["spearman_rho"])
    ax.set_title("Event-level Spearman ρ with pip_order")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "event_level_spearman_top.png"), dpi=140)
    plt.close(fig)

    return res


def bucket_best_order(df: pd.DataFrame, metric: str = "sharpe_like") -> pd.DataFrame:
    """
    For each month bucket, pick the best pip_order by chosen metric.
    """
    if not _has("param__pip_order", df):
        raise ValueError("param__pip_order not found. Add pip_order to the sweep grid.")

    # Aggregate to per-bucket, per-order performance
    grp_cols = ["bucket_month", "param__pip_order"]
    agg = df.groupby(grp_cols, dropna=False).agg(
        n_trades=("pnl_pct", lambda s: s.dropna().shape[0]),
        win_rate=("pnl_pct", lambda s: (s.dropna() > 0).mean() if s.dropna().shape[0] else 0.0),
        avg_pnl=("pnl_pct", "mean"),
        std_pnl=("pnl_pct", "std"),
    ).reset_index()
    agg["sharpe_like"] = agg.apply(lambda r: (r["avg_pnl"] / r["std_pnl"]) * (r["n_trades"] ** 0.5) if pd.notna(r["std_pnl"]) and r["std_pnl"] > 0 and r["n_trades"] > 0 else 0.0, axis=1)

    # Choose best order per bucket
    best = agg.sort_values([ "bucket_month", metric], ascending=[True, False]).groupby("bucket_month").head(1).reset_index(drop=True)
    return best, agg


def bucket_level_correlation(df: pd.DataFrame, outdir: str, metric: str = "sharpe_like") -> pd.DataFrame:
    """
    Spearman correlation between 'best' pip_order per month and average regime features in that month.
    """
    feats = [c for c in df.columns if c.startswith("feat_regime_")]
    # Average regime features by bucket-month
    F = df.groupby("bucket_month")[feats].mean().reset_index()
    best, agg = bucket_best_order(df, metric=metric)

    merged = pd.merge(best[["bucket_month", "param__pip_order"]], F, on="bucket_month", how="left")
    rows = []
    for c in feats:
        rho = _spearman(merged["param__pip_order"], merged[c])
        mi = _mutual_info_continuous_discrete(merged[c], merged["param__pip_order"], bins=8)
        rows.append({"feature": c, "spearman_rho": rho, "mutual_info": mi})
    res = pd.DataFrame(rows).sort_values(by="spearman_rho", ascending=False)
    res.to_csv(os.path.join(outdir, f"bucket_level_corr_{metric}.csv"), index=False)

    # Plot
    fig, ax = plt.subplots(figsize=(10, 6))
    top = res.head(10)
    ax.barh(top["feature"], top["spearman_rho"])
    ax.set_title(f"Bucket-level Spearman ρ with best pip_order (metric={metric})")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, f"bucket_level_spearman_top_{metric}.png"), dpi=140)
    plt.close(fig)

    # Save who won per month (quick eyeballing)
    best.to_csv(os.path.join(outdir, f"bucket_best_order_{metric}.csv"), index=False)
    agg.to_csv(os.path.join(outdir, f"bucket_performance_{metric}.csv"), index=False)

    return res


# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser(description="Order correlation analysis (Spearman & MI) with monthly bucketing.")
    ap.add_argument("--combined", required=True, help="Combined CSV from run_sweep.py including pip_order in param__")
    ap.add_argument("--outdir", default="./order_corr", help="Output directory")
    ap.add_argument("--metric", default="sharpe_like", choices=["sharpe_like", "win_rate", "avg_pnl"])
    args = ap.parse_args()

    _ensure_outdir(args.outdir)
    df = load_combined(args.combined)
    ev = event_level_correlation(df, args.outdir)
    bk = bucket_level_correlation(df, args.outdir, metric=args.metric)
    print("Wrote:", os.path.join(args.outdir, "event_level_corr.csv"))
    print("Wrote:", os.path.join(args.outdir, f"bucket_level_corr_{args.metric}.csv"))


if __name__ == "__main__":
    main()
