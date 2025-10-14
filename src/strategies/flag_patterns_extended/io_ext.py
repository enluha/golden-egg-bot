from __future__ import annotations

import json
import os
from typing import Optional

import pandas as pd

from .plots import plot_trade_from_row


def archive_trade_bundle(
	df: pd.DataFrame,
	row: pd.Series,
	cfg,
	outdir: str,
	*,
	include_plot: bool = True,
) -> None:
	"""Persist trade metadata and optional plot for diagnostics."""

	os.makedirs(outdir, exist_ok=True)
	symbol = row.get("symbol", "UNK")
	timeframe = row.get("timeframe", "UNK")
	key = f"{symbol}_{timeframe}_i1{int(row['i1'])}_j1{int(row['j1'])}"

	payload = {
		"symbol": symbol,
		"timeframe": timeframe,
		"kind": row.get("kind"),
		"direction": row.get("direction"),
		"i0": int(row["i0"]),
		"i1": int(row["i1"]),
		"j0": int(row["j0"]),
		"j1": int(row["j1"]),
		"breakout_idx": int(row["breakout_idx"]) if pd.notna(row.get("breakout_idx")) else None,
		"entry_idx": int(row["entry_idx"]) if pd.notna(row.get("entry_idx")) else None,
		"exit_idx": int(row["exit_idx"]) if pd.notna(row.get("exit_idx")) else None,
		"exit_reason": row.get("exit_reason"),
		"pnl_pct": float(row["pnl_pct"]) if pd.notna(row.get("pnl_pct")) else None,
	}

	with open(os.path.join(outdir, key + ".json"), "w", encoding="utf-8") as handle:
		json.dump(payload, handle, indent=2)

	if include_plot and pd.notna(row.get("entry_idx")):
		png_path = os.path.join(outdir, key + ".png")
		try:
			plot_trade_from_row(df, row, cfg, title=key, savepath=png_path, show=False)
		except Exception:
			pass