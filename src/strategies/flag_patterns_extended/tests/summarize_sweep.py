#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ----------------------------- I/O -------------------------------------------

def load_combined(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    # Normalize column names
    df.columns = [str(c) for c in df.columns]
    return df


def detect_param_columns(df: pd.DataFrame) -> List[str]:
    return [c for c in df.columns if c.startswith("param__")]


# ------------------------- Aggregations --------------------------------------

@dataclass
class Metrics:
    n_signals: int
    n_trades: int
    win_rate: float
    avg_pnl: float
    median_pnl: float
    std_pnl: float
    sharpe_like: float


def compute_group_metrics(group: pd.DataFrame) -> Metrics:
    """Compute metrics for a single param combo group.

    - n_signals: all rows (detections) for this combo
    - n_trades: rows with a realized PnL (non-null pnl_pct)
    - sharpe_like: mean/ std * sqrt(n_trades), with ddof=0
    """
    n_signals = len(group)
    pnl = group["pnl_pct"].dropna().astype(float)
    n_trades = len(pnl)
    if n_trades == 0:
        return Metrics(n_signals, 0, 0.0, 0.0, 0.0, 0.0, 0.0)

    wins = (pnl > 0).sum()
    mean = float(pnl.mean())
    median = float(pnl.median())
    std = float(pnl.std(ddof=0))
    wr = float(wins) / n_trades if n_trades else 0.0
    sharpe_like = (mean / std) * (n_trades ** 0.5) if std > 0 else 0.0
    return Metrics(n_signals, n_trades, wr, mean, median, std, sharpe_like)


def summarize(df: pd.DataFrame, min_trades: int, rank_metric: str) -> pd.DataFrame:
    """Return a summary frame with one row per param combo + metrics."""
    param_cols = detect_param_columns(df)
    if not param_cols:
        raise ValueError("No param__* columns found in the combined CSV.")

    # Group and compute metrics
    recs = []
    for keys, grp in df.groupby(param_cols, dropna=False):
        m = compute_group_metrics(grp)
        row = {pc: (keys[i] if isinstance(keys, tuple) else keys) for i, pc in enumerate(param_cols)}
        row.update({
            "n_signals": m.n_signals,
            "n_trades": m.n_trades,
            "win_rate": m.win_rate,
            "avg_pnl": m.avg_pnl,
            "median_pnl": m.median_pnl,
            "std_pnl": m.std_pnl,
            "sharpe_like": m.sharpe_like,
        })
        recs.append(row)

    summ = pd.DataFrame.from_records(recs)
    # Ensure numeric types where appropriate
    for c in ["n_signals", "n_trades"]:
        summ[c] = summ[c].astype(int)
    for c in ["win_rate", "avg_pnl", "median_pnl", "std_pnl", "sharpe_like"]:
        summ[c] = pd.to_numeric(summ[c], errors="coerce")

    # Filter by min trades
    summ = summ[summ["n_trades"] >= int(min_trades)].copy()
    # Rank
    if rank_metric not in summ.columns:
        raise ValueError(f"rank_metric '{rank_metric}' not found in summary columns: {summ.columns.tolist()}")
    summ = summ.sort_values(by=[rank_metric, "n_trades"], ascending=[False, False]).reset_index(drop=True)
    return summ


# ----------------------------- Plotting --------------------------------------

def _ensure_outdir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def plot_top_bar(summ: pd.DataFrame, rank_metric: str, topn: int, outdir: str) -> str:
    top = summ.head(topn).copy()
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(range(len(top)), top[rank_metric].values)
    ax.set_xticks(range(len(top)))
    ax.set_xticklabels([f"#{i+1}\ntrades={t}" for i, t in enumerate(top["n_trades"].values)], rotation=0)
    ax.set_ylabel(rank_metric)
    ax.set_title(f"Top {topn} combos by {rank_metric}")
    path = os.path.join(outdir, f"top_{rank_metric}_bar.png")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def plot_top_scatter(summ: pd.DataFrame, topn: int, outdir: str) -> str:
    top = summ.head(topn).copy()
    fig, ax = plt.subplots(figsize=(8, 6))
    sc = ax.scatter(top["win_rate"], top["avg_pnl"], s=np.clip(top["n_trades"] * 2.0, 20, 200), alpha=0.8)
    for i, (_, r) in enumerate(top.iterrows(), 1):
        ax.annotate(f"{i}", (r["win_rate"], r["avg_pnl"]), fontsize=8, xytext=(3, 3), textcoords="offset points")
    ax.set_xlabel("Win rate")
    ax.set_ylabel("Avg PnL per trade")
    ax.set_title("Top combos: win-rate vs avg PnL (size ~ n_trades)")
    path = os.path.join(outdir, "top_scatter_winrate_avgpnl.png")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def plot_param_distributions(top: pd.DataFrame, outdir: str) -> str:
    """Histogram each Phase-1 parameter among top combos (to see 'where' winners cluster)."""
    # Only plot param columns
    param_cols = [c for c in top.columns if c.startswith("param__")]
    n = len(param_cols)
    cols = 3
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(4*cols, 2.8*rows))
    axes = np.atleast_1d(axes).ravel()

    for ax, pc in zip(axes, param_cols):
        vals = top[pc]
        if vals.dtype == bool or set(vals.unique()) <= {True, False}:
            counts = vals.value_counts(dropna=False)
            ax.bar(counts.index.astype(str), counts.values)
        else:
            ax.hist(pd.to_numeric(vals, errors="coerce").dropna(), bins=8)
        ax.set_title(pc.replace("param__", ""), fontsize=9)
    for k in range(len(param_cols), len(axes)):
        axes[k].axis("off")

    path = os.path.join(outdir, "top_param_distributions.png")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def _heatmap_from_pivot(pv: pd.DataFrame, title: str, outpath: str) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 6))
    # Keep numeric ordering where possible
    xt = [float(x) if _is_number(x) else x for x in pv.columns]
    yt = [float(y) if _is_number(y) else y for y in pv.index]
    im = ax.imshow(pv.values.astype(float), aspect="auto", origin="lower")
    ax.set_xticks(range(len(pv.columns)))
    ax.set_xticklabels([str(x) for x in xt], rotation=45, ha="right")
    ax.set_yticks(range(len(pv.index)))
    ax.set_yticklabels([str(y) for y in yt])
    ax.set_title(title)
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label(pv.attrs.get("metric", "metric"))
    fig.tight_layout()
    fig.savefig(outpath, dpi=140)
    plt.close(fig)


def _pivot_metric(df: pd.DataFrame, x: str, y: str, metric: str, filter_mask: Optional[pd.Series] = None) -> Optional[pd.DataFrame]:
    d = df.copy()
    if filter_mask is not None:
        d = d[filter_mask].copy()
    # pivot_table handles missing combos; average across repeats if any
    try:
        pv = pd.pivot_table(
            d,
            index=f"param__{y}",
            columns=f"param__{x}",
            values=metric,
            aggfunc="mean",
        )
    except KeyError:
        return None
    pv.attrs["metric"] = metric
    return pv


def plot_core_heatmaps(summ: pd.DataFrame, outdir: str, metric: str = "sharpe_like") -> List[str]:
    """Heatmaps for the main Phase-1 pairs."""
    paths: List[str] = []
    pairs = [
        ("pole_lookback_k", "pole_score_min"),
        ("min_consolidation_bars", "max_consolidation_bars"),
        ("parallel_angle_max_deg", "channel_slope_cap_deg"),
        ("width_shrink_ratio_max", "apex_pos_factor_max"),
        ("breakout_buffer_atr", "breakout_requires_close"),  # boolean on Y here
        ("stop_offset_atr", "measured_move_factor"),         # measured_move only
        ("stop_offset_atr", "atr_target_k"),                 # atr_multiple only
    ]

    # measured_move / atr_multiple masks
    mm_mask = (summ.get("param__target_type") == "measured_move") if "param__target_type" in summ.columns else None
    atr_mask = (summ.get("param__target_type") == "atr_multiple") if "param__target_type" in summ.columns else None

    for (x, y) in pairs:
        mask = None
        if y == "measured_move_factor":
            if mm_mask is None:
                continue
            mask = mm_mask
        if y == "atr_target_k":
            if atr_mask is None:
                continue
            mask = atr_mask

        pv = _pivot_metric(summ, x=x, y=y, metric=metric, filter_mask=mask)
        if pv is None or pv.empty:
            continue
        title = f"{metric} heatmap: {y} vs {x}"
        out = os.path.join(outdir, f"heatmap_{metric}_{y}_vs_{x}.png")
        _heatmap_from_pivot(pv, title, out)
        paths.append(out)
    return paths


def _is_number(v) -> bool:
    try:
        float(v)
        return True
    except Exception:
        return False


# ------------------------------ Report ---------------------------------------

def write_markdown_report(
    outdir: str,
    combined_csv_path: str,
    summary_csv_path: str,
    rank_metric: str,
    plots: Dict[str, str],
    top_table: pd.DataFrame,
    topn: int,
    min_trades: int,
) -> str:
    md = []
    md.append(f"# Phase-1 Sweep Summary\n")
    md.append(f"- **Combined CSV:** `{combined_csv_path}`")
    md.append(f"- **Summary CSV:** `{summary_csv_path}`")
    md.append(f"- **Rank metric:** `{rank_metric}`")
    md.append(f"- **Top N:** `{topn}`, **Min trades per combo:** `{min_trades}`\n")

    md.append("## Top results (first rows)\n")
    # Render a compact markdown table for the first few rows
    show_cols = [c for c in top_table.columns if c.startswith("param__")] + ["n_trades", "win_rate", "avg_pnl", "median_pnl", "sharpe_like"]
    md.append(top_table[show_cols].head(min(10, len(top_table))).to_markdown(index=False))
    md.append("\n")

    # Plots
    md.append("## Plots\n")
    for name, path in plots.items():
        if path:
            md.append(f"### {name}\n")
            md.append(f"![{name}]({os.path.basename(path)})\n")

    out_md = os.path.join(outdir, "report.md")
    with open(out_md, "w") as f:
        f.write("\n".join(md))
    return out_md


# ------------------------------ CLI ------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Summarize Phase-1 sweep combined CSV and plot promising regions.")
    ap.add_argument("--combined", required=True, help="Path to combined CSV from run_sweep.py")
    ap.add_argument("--outdir", default="./summary", help="Output directory for summary & plots")
    ap.add_argument("--rank-metric", default="sharpe_like", choices=["sharpe_like", "win_rate", "avg_pnl", "median_pnl"])
    ap.add_argument("--topn", type=int, default=25, help="Number of top combos to display/plot")
    ap.add_argument("--min-trades", type=int, default=30, help="Minimum trades per combo to be considered")
    args = ap.parse_args()

    _ensure_outdir(args.outdir)
    df = load_combined(args.combined)

    # Summarize & rank
    summ = summarize(df, min_trades=args.min_trades, rank_metric=args.rank_metric)
    if summ.empty:
        print("No combos passed the min-trades filter; try lowering --min-trades.")
        return

    # Save summary CSV
    summary_csv_path = os.path.join(args.outdir, "summary_ranked.csv")
    summ.to_csv(summary_csv_path, index=False)

    # Slice top-N
    top = summ.head(args.topn).copy()

    # Plots
    plots: Dict[str, str] = {}
    plots["Top bar"] = plot_top_bar(summ, rank_metric=args.rank_metric, topn=args.topn, outdir=args.outdir)
    plots["Top scatter"] = plot_top_scatter(summ, topn=args.topn, outdir=args.outdir)
    plots["Top param distributions"] = plot_param_distributions(top, outdir=args.outdir)
    # Heatmaps over all combos that passed filters
    for p in plot_core_heatmaps(summ, outdir=args.outdir, metric=args.rank_metric):
        plots[f"Heatmap {os.path.basename(p)}"] = p

    # Report
    report_md = write_markdown_report(
        outdir=args.outdir,
        combined_csv_path=os.path.abspath(args.combined),
        summary_csv_path=summary_csv_path,
        rank_metric=args.rank_metric,
        plots=plots,
        top_table=top,
        topn=args.topn,
        min_trades=args.min_trades,
    )
    print(f"Wrote summary CSV -> {summary_csv_path}")
    print(f"Wrote report -> {report_md}")


if __name__ == "__main__":
    main()
