# single-run smoke & invariants

# pytest tests for the extended flag/pennant detector + backtest harness
from __future__ import annotations

import os
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import pytest

from ..config import Config
from ..backtest import run_backtest
from ..breakout import boundary_value_at


# --------- helpers ---------

def _find_sample_csv() -> str:
    """
    Tries to find a CSV under the canonical data_samples folder.
    You can override by setting TEST_CSV env var.
    """
    env = os.getenv("TEST_CSV")
    if env and os.path.exists(env):
        return env

    roots = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data_samples")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data_samples")),
    ]
    for root in roots:
        if os.path.isdir(root):
            # pick first CSV
            for fn in os.listdir(root):
                if fn.lower().endswith(".csv"):
                    return os.path.join(root, fn)
    raise FileNotFoundError("No sample CSV found. Set TEST_CSV to a valid file.")


def _load_df(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "date" in df.columns:
        try:
            df["date"] = pd.to_datetime(df["date"], unit="ms", errors="ignore")
        except Exception:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.set_index("date")
    df.columns = [c.lower() for c in df.columns]
    return df


def _ols_lines_over_window(df: pd.DataFrame, j0: int, j1: int):
    x = np.arange(j0, j1 + 1, dtype=float)
    y_hi = df["high"].iloc[j0: j1 + 1].astype(float).to_numpy()
    y_lo = df["low"].iloc[j0: j1 + 1].astype(float).to_numpy()
    # OLS
    X = np.vstack([x, np.ones_like(x)]).T
    beta_hi, _, _, _ = np.linalg.lstsq(X, y_hi, rcond=None)
    beta_lo, _, _, _ = np.linalg.lstsq(X, y_lo, rcond=None)
    class L:  # tiny shim for BoundaryLine
        def __init__(self, slope, intercept): self.slope, self.intercept = float(slope), float(intercept)
    return L(beta_hi[0], beta_hi[1]), L(beta_lo[0], beta_lo[1])


# --------- tests ---------

def test_smoke_backtest_runs():
    df = _load_df(_find_sample_csv())
    cfg = Config()
    trades = run_backtest(df, cfg, symbol="TEST", timeframe="1h")
    # Should return a dataframe (possibly empty) with expected columns present
    expected_cols = {
        "kind", "direction", "i0", "i1", "j0", "j1", "breakout_idx",
        "entry_idx", "exit_idx", "entry_price", "stop_price", "target_price",
        "exit_price", "exit_reason", "pnl_pct", "r_multiple", "hold_bars"
    }
    missing = expected_cols - set(trades.columns)
    assert not missing, f"Missing expected columns: {missing}"


def test_no_lookahead_and_indices_ordering():
    df = _load_df(_find_sample_csv())
    cfg = Config()
    trades = run_backtest(df, cfg, symbol="TEST", timeframe="1h")

    for _, r in trades.iterrows():
        j1 = int(r["j1"])
        b = r.get("breakout_idx")
        e = r.get("entry_idx")
        # No breakout or entry is allowed, but if present:
        if pd.notna(b):
            assert int(b) > j1, "Breakout must occur AFTER consolidation end (no lookahead)."
        if pd.notna(e) and pd.notna(b):
            if cfg.entry_type == "close":
                assert int(e) == int(b), "Entry at close should use breakout bar index."
            else:
                assert int(e) == int(b) + 1, "Entry at next_open should be the bar after breakout."


def test_retrace_cap_respected():
    df = _load_df(_find_sample_csv())
    cfg = Config()
    trades = run_backtest(df, cfg, symbol="TEST", timeframe="1h")

    for _, r in trades.iterrows():
        # Retrace is logged as part of feature flattening
        if "retrace_ratio" in r and pd.notna(r["retrace_ratio"]):
            assert float(r["retrace_ratio"]) <= cfg.max_retrace_ratio + 1e-9, "Retrace cap violated."


def test_breakout_condition_consistency():
    """
    Re-validate that breakout bar really closed (or ranged) beyond the boundary + buffer.
    Uses an OLS refit on [j0, j1] which matches plotting logic if boundary lines were not serialized.
    """
    df = _load_df(_find_sample_csv())
    cfg = Config()
    trades = run_backtest(df, cfg, symbol="TEST", timeframe="1h")

    for _, r in trades.iterrows():
        if pd.isna(r["breakout_idx"]):
            continue
        j0, j1, t = int(r["j0"]), int(r["j1"]), int(r["breakout_idx"])
        upper, lower = _ols_lines_over_window(df, j0, j1)
        buf = cfg.breakout_buffer_atr * float(_atr(df, cfg.atr_len).iat[t])
        cl = float(df["close"].iat[t])
        hi = float(df["high"].iat[t])
        lo = float(df["low"].iat[t])

        if r["direction"] == "bull":
            thr = boundary_value_at(upper, t) + buf
            if cfg.breakout_requires_close:
                assert cl >= thr, "Bull breakout close did not exceed boundary + buffer."
            else:
                assert hi >= thr, "Bull breakout range did not exceed boundary + buffer."
        else:
            thr = boundary_value_at(lower, t) - buf
            if cfg.breakout_requires_close:
                assert cl <= thr, "Bear breakout close did not exceed boundary - buffer."
            else:
                assert lo <= thr, "Bear breakout range did not exceed boundary - buffer."


def test_atr_target_applied_directionally():
    df = _load_df(_find_sample_csv())
    cfg = Config()
    cfg.target_type = "atr_multiple"
    cfg.atr_target_k = 2.0

    trades = run_backtest(df, cfg, symbol="TEST", timeframe="1h")
    subset = trades.dropna(subset=["entry_idx", "entry_price", "target_price"]).head(5)
    if subset.empty:
        pytest.skip("No trades produced in sample for ATR target check.")

    atr = _atr(df, cfg.atr_len)
    for _, row in subset.iterrows():
        entry_idx = int(row["entry_idx"])
        a = float(atr.iat[entry_idx])
        if row["direction"] == "bull":
            assert row["target_price"] >= row["entry_price"], "Bull ATR target should be above entry."
            assert pytest.approx(row["target_price"] - row["entry_price"], rel=0.25) == 2.0 * a
        else:
            assert row["target_price"] <= row["entry_price"], "Bear ATR target should be below entry."
            assert pytest.approx(row["entry_price"] - row["target_price"], rel=0.25) == 2.0 * a


# ---- tiny ATR for the test ----
def _atr(df: pd.DataFrame, length: int) -> pd.Series:
    tr1 = (df["high"] - df["low"]).abs()
    tr2 = (df["high"] - df["close"].shift(1)).abs()
    tr3 = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / max(length, 1), adjust=False).mean()
