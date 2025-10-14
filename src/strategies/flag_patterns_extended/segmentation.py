# pole/consolidation segmentation helpers

from __future__ import annotations

from typing import Optional, Tuple, Literal
import numpy as np
import pandas as pd

from .config import Config
from .detector import PoleStats, ConsolidationStats, BoundaryLine
from .detector import compute_atr  # reuse same ATR impl

Direction = Literal["bull", "bear"]


def detect_pole_at_index(
    df: pd.DataFrame,
    atr: pd.Series,
    t: int,
    cfg: Config,
    *,
    price_col: str = "close",
) -> Optional[PoleStats]:
    """
    Volatility-aware impulse over [t-k, t] using starter method (ATR-normalized).
    """
    k = cfg.pole_lookback_k
    if t - k < 0:
        return None
    p0 = float(df[price_col].iat[t - k])
    p1 = float(df[price_col].iat[t])
    height = abs(p1 - p0)
    direction: Direction = "bull" if p1 >= p0 else "bear"

    if cfg.pole_method == "atr_normalized":
        denom = float(atr.iloc[max(t - cfg.atr_len, 0): t + 1].mean())
        score = height / denom if denom > 0 else 0.0
        if score < cfg.pole_score_min:
            return None
    else:
        return None  # only the starter method for now

    return PoleStats(i0=t - k, i1=t, height=height, score=score, direction=direction)


def find_consolidation_window(
    df: pd.DataFrame,
    pole: PoleStats,
    cfg: Config,
) -> Optional[ConsolidationStats]:
    """
    Pick the smallest acceptable consolidation window after the pole.
    (Later you can add heuristics to extend to j1 best-fit.)
    """
    j0 = pole.i1 + 1
    j1_max = min(pole.i1 + cfg.max_consolidation_bars, len(df) - 1)
    j1 = j0 + cfg.min_consolidation_bars - 1
    if j0 >= len(df) or j1 > j1_max:
        return None

    # Compute retracement depth within [j0, j1] relative to pole height.
    pole_height = max(1e-12, abs(float(df["close"].iat[pole.i1]) - float(df["close"].iat[pole.i0])))
    if pole.direction == "bull":
        pole_high = float(df["high"].iloc[pole.i0: pole.i1 + 1].max())
        pole_low = float(df["low"].iloc[pole.i0: pole.i1 + 1].min())
        min_low = float(df["low"].iloc[j0: j1 + 1].min())
        retrace_ratio = (pole_high - min_low) / (pole_high - pole_low + 1e-12)
    else:
        pole_high = float(df["high"].iloc[pole.i0: pole.i1 + 1].max())
        pole_low = float(df["low"].iloc[pole.i0: pole.i1 + 1].min())
        max_high = float(df["high"].iloc[j0: j1 + 1].max())
        retrace_ratio = (max_high - pole_low) / (pole_high - pole_low + 1e-12)

    # Widths (using raw highs/lows; final classifier should re-evaluate via fitted lines)
    width_start = float(df["high"].iloc[j0]) - float(df["low"].iloc[j0])
    width_end = float(df["high"].iloc[j1]) - float(df["low"].iloc[j1])

    return ConsolidationStats(j0=j0, j1=j1, retrace_ratio=float(retrace_ratio),
                              width_start=float(width_start), width_end=float(width_end))


def fit_boundaries_ols(
    df: pd.DataFrame,
    cons: ConsolidationStats,
) -> Tuple[BoundaryLine, BoundaryLine]:
    """
    OLS on highs and lows vs bar index in [j0, j1].
    """
    x = np.arange(cons.j0, cons.j1 + 1, dtype=float)
    y_hi = df["high"].iloc[cons.j0: cons.j1 + 1].astype(float).to_numpy()
    y_lo = df["low"].iloc[cons.j0: cons.j1 + 1].astype(float).to_numpy()

    s_u, i_u, r2_u = _ols_with_r2(x, y_hi)
    s_l, i_l, r2_l = _ols_with_r2(x, y_lo)

    return (
        BoundaryLine(slope=float(s_u), intercept=float(i_u), r2=float(r2_u), touches=None),
        BoundaryLine(slope=float(s_l), intercept=float(i_l), r2=float(r2_l), touches=None),
    )


# ---- small numeric helpers ----

def _ols_with_r2(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    X = np.vstack([x, np.ones_like(x)]).T
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    slope, intercept = float(beta[0]), float(beta[1])
    y_hat = slope * x + intercept
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return slope, intercept, r2
