#!/usr/bin/env python3
import argparse
import pandas as pd
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--combined", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    df = pd.read_csv(args.combined)
    # Normalize column names
    df.columns = [str(c) for c in df.columns]
    # Keep only rows with realized pnl
    if "pnl_pct" not in df.columns:
        raise SystemExit("combined has no 'pnl_pct' column")
    d = df.dropna(subset=["pnl_pct"]).copy()
    d["pnl_pct"] = d["pnl_pct"].astype(float)

    # Identify parameter columns
    param_cols = [c for c in d.columns if c.startswith("param__")]
    if "param__entry_type" not in param_cols:
        raise SystemExit("combined missing param__entry_type column")

    # Compute per-combo metrics grouped by entry_type
    # Base grouping keys are param__*; but if only entry_type varies, we also include
    # some stable identifiers to allow inner-join later (symbol/timeframe/split_side).
    base_keys = [c for c in param_cols if c != "param__entry_type"]
    extras = [c for c in ["symbol", "timeframe", "split_side"] if c in d.columns]
    group_keys = base_keys + extras + ["param__entry_type"]
    g = d.groupby(group_keys, dropna=False)["pnl_pct"].agg(["count", "mean"]).reset_index()
    g = g.rename(columns={"count": "n_trades", "mean": "avg_pnl"})

    # Split into two tables: close vs next_open
    key_cols = [c for c in group_keys if c != "param__entry_type"]
    # If there are still no join keys, synthesize a constant key to pair globally
    synth_key = None
    if len(key_cols) == 0:
        synth_key = "_pair_key"
        g[synth_key] = 1
        key_cols = [synth_key]
    close_tbl = g[g["param__entry_type"] == "close"].drop(columns=["param__entry_type"]).copy()
    close_tbl = close_tbl.rename(columns={"n_trades": "n_close", "avg_pnl": "avg_pnl_close"})

    open_tbl = g[g["param__entry_type"] == "next_open"].drop(columns=["param__entry_type"]).copy()
    open_tbl = open_tbl.rename(columns={"n_trades": "n_open", "avg_pnl": "avg_pnl_open"})

    # Inner join on identical params (excluding entry_type)
    pairs = pd.merge(close_tbl, open_tbl, on=key_cols, how="inner")
    if pairs.empty:
        print("No matching param pairs found for close vs next_open")
        return

    pairs["delta_avg_pnl_close_minus_open"] = pairs["avg_pnl_close"] - pairs["avg_pnl_open"]
    pairs["total_trades_pair"] = pairs["n_close"].fillna(0) + pairs["n_open"].fillna(0)

    # Summary
    n_pairs = len(pairs)
    wins = (pairs["delta_avg_pnl_close_minus_open"] > 0).sum()
    losses = (pairs["delta_avg_pnl_close_minus_open"] < 0).sum()
    ties = n_pairs - wins - losses
    avg_delta = pairs["delta_avg_pnl_close_minus_open"].mean()
    med_delta = pairs["delta_avg_pnl_close_minus_open"].median()

    print(f"pairs: {n_pairs}, close better: {wins}, next_open better: {losses}, ties: {ties}")
    print(f"mean delta (close - next_open): {avg_delta:.6f}, median: {med_delta:.6f}")

    # Drop synthetic key from presentation if present
    if synth_key and synth_key in pairs.columns:
        pairs = pairs.drop(columns=[synth_key])
        key_cols = [c for c in key_cols if c != synth_key]

    top = pairs.sort_values(by="delta_avg_pnl_close_minus_open", ascending=False).head(10)
    print("\nTop 5 pairs where close > next_open (by avg_pnl delta):")
    print(top[key_cols + ["n_close", "n_open", "avg_pnl_close", "avg_pnl_open", "delta_avg_pnl_close_minus_open"]].head(5).to_string(index=False))

    bottom = pairs.sort_values(by="delta_avg_pnl_close_minus_open", ascending=True).head(10)
    print("\nTop 5 pairs where next_open > close (by avg_pnl delta):")
    print(bottom[key_cols + ["n_close", "n_open", "avg_pnl_close", "avg_pnl_open", "delta_avg_pnl_close_minus_open"]].head(5).to_string(index=False))

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        pairs.to_csv(args.out, index=False)
        print(f"\nWrote pairwise A/B table -> {args.out}")


if __name__ == "__main__":
    main()
