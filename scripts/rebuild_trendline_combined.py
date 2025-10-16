import os
import glob
import sys

import pandas as pd


def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(root, "phase1_outputs")
    pattern = os.path.join(
        out_dir, "phase1_btc1h_variant_trendline_only_BTCUSDT_1h_split*_s*.csv"
    )
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"No per-split files found with pattern: {pattern}")
        return 1

    frames = []
    total_rows = 0
    for fp in files:
        try:
            df = pd.read_csv(fp)
        except pd.errors.EmptyDataError:
            print(f"Skipping empty file: {fp}")
            continue
        if df.empty:
            print(f"Skipping zero-row file: {fp}")
            continue
        frames.append(df)
        total_rows += len(df)

    if not frames:
        print("All matched files were empty; nothing to combine.")
        return 2

    combined = pd.concat(frames, ignore_index=True, sort=False)

    out_fp = os.path.join(out_dir, "phase1_btc1h_variant_trendline_only_combined.csv")
    combined.to_csv(out_fp, index=False)
    print(
        f"Wrote combined file: {out_fp} from {len(frames)} files, total rows: {len(combined)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
