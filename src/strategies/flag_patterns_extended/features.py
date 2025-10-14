# logs R², angles, touches, compression, etc.

# /src/strategies/flag_patterns_extended/features.py
from __future__ import annotations

from typing import Dict, Optional
import math
import numpy as np
import pandas as pd

from .detector import DetectedPattern, BoundaryLine, compute_atr
from .filters import adx_wilder, sma
from .pivots import get_pivots


# ------------------- Regime features (for ORDER correlation) -------------------

def linear_fit_r2(series: pd.Series) -> float:
    y = series.astype(float).to_numpy()
    n = len(y)
    if n < 3:
        return float("nan")
    x = np.arange(n, dtype=float)
    X = np.vstack([x, np.ones_like(x)]).T
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    y_hat = X @ beta
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")


def realized_vol(close: pd.Series, window: int) -> float:
    rets = np.log(close.astype(float)).diff().dropna()
    if len(rets) < max(5, window // 2):
        return float("nan")
    return float(rets.tail(window).std(ddof=0))


def avg_swing_length(
    df: pd.DataFrame,
    end_idx: int,
    window: int,
    *,
    pivot_method: str = "PIP",
    pip_order_for_feature: int = 8,
    dc_epsilon_atr_mult: Optional[float] = None,
    price_col: str = "close",
) -> float:
    """
    Median bars between pivots over a trailing window ending at end_idx.
    """
    start = max(0, end_idx - window + 1)
    w = df.iloc[start: end_idx + 1]
    if len(w) < 10:
        return float("nan")

    if pivot_method == "DirectionalChange" and dc_epsilon_atr_mult is not None:
        # epsilon as ATR multiple (robust)
        atr = compute_atr(w["high"], w["low"], w["close"], 14)
        eps = float(atr.iloc[-1]) * float(dc_epsilon_atr_mult)
        piv = get_pivots(w, "DirectionalChange", dc_epsilon=eps, price_col=price_col)
    else:
        piv = get_pivots(w, "PIP", pip_order=pip_order_for_feature, price_col=price_col)

    if len(piv) < 3:
        return float("nan")
    diffs = np.diff(piv)
    if len(diffs) == 0:
        return float("nan")
    return float(np.median(diffs))


def regime_features_at(
    df: pd.DataFrame,
    idx: int,
    *,
    price_col: str = "close",
    vol_col: str = "volume",
    r2_window: int = 50,
    rv_window: int = 50,
    vol_ma_short: int = 20,
    vol_ma_long: int = 50,
    swing_window: int = 200,
    pivot_method_for_feature: str = "PIP",
    pip_order_for_feature: int = 8,
    dc_epsilon_atr_mult: Optional[float] = None,
) -> Dict[str, float]:
    """
    Compute regime descriptors at time 'idx' without lookahead.
    """
    res: Dict[str, float] = {}

    # ATR/price fraction
    atr = compute_atr(df["high"], df["low"], df["close"], 14)
    price = float(df[price_col].iat[idx])
    atr_now = float(atr.iat[idx])
    res["feat_regime_atr_frac_price"] = (atr_now / price) if price > 0 else float("nan")

    # ADX(14)
    _, _, adx = adx_wilder(df["high"], df["low"], df["close"], 14)
    res["feat_regime_adx14"] = float(adx.iat[idx]) if idx < len(adx) else float("nan")

    # Linear-fit R^2 on log-price over r2_window
    if idx + 1 >= r2_window:
        seg = np.log(df[price_col].iloc[idx - r2_window + 1: idx + 1].astype(float))
        res["feat_regime_r2_logprice_w50"] = linear_fit_r2(seg)
    else:
        res["feat_regime_r2_logprice_w50"] = float("nan")

    # Realized vol over rv_window
    if idx + 1 >= rv_window:
        seg_close = df[price_col].iloc[: idx + 1]
        res["feat_regime_realized_vol_w50"] = realized_vol(seg_close, rv_window)
    else:
        res["feat_regime_realized_vol_w50"] = float("nan")

    # Volume MA ratio (short / long)
    if vol_col in df.columns:
        vs = sma(df[vol_col].astype(float), vol_ma_short)
        vl = sma(df[vol_col].astype(float), vol_ma_long)
        vs_i = float(vs.iat[idx]) if not np.isnan(vs.iat[idx]) else float("nan")
        vl_i = float(vl.iat[idx]) if not np.isnan(vl.iat[idx]) else float("nan")
        res["feat_regime_vol_ma_ratio_20_50"] = (vs_i / vl_i) if (vl_i and vl_i > 0) else float("nan")
    else:
        res["feat_regime_vol_ma_ratio_20_50"] = float("nan")

    # Avg swing length (median bars between pivots) over swing_window
    res["feat_regime_avg_swing_len_w200"] = avg_swing_length(
        df, idx, swing_window,
        pivot_method=pivot_method_for_feature,
        pip_order_for_feature=pip_order_for_feature,
        dc_epsilon_atr_mult=dc_epsilon_atr_mult,
        price_col=price_col,
    )

    return res


# ------------------- Existing trade-feature builder (extended) ----------------

def build_feature_row(
    df: pd.DataFrame,
    atr: pd.Series,
    pat: DetectedPattern,
) -> Dict[str, float]:
    """
    Flatten geometry + context into a single dict for logging alongside each trade.
    (Extended with a few simple context features.)
    """
    i0, i1 = pat.pole.i0, pat.pole.i1
    j0, j1 = pat.cons.j0, pat.cons.j1

    # Angles/widths via fitted lines
    theta_u = _angle_deg(pat.upper.slope)
    theta_l = _angle_deg(pat.lower.slope)
    theta_diff = abs(theta_u - theta_l)
    theta_channel = 0.5 * (theta_u + theta_l)

    w0 = _band_width(pat.upper, pat.lower, j0)
    w1 = _band_width(pat.upper, pat.lower, j1)
    shrink_ratio = (w1 / w0) if w0 != 0 else float("inf")

    atr_j1 = float(atr.iat[j1])
    price_j1 = float(df["close"].iat[j1])
    atr_frac = atr_j1 / price_j1 if price_j1 != 0 else 0.0

    # Volumes (if present)
    vol_cols = [c for c in df.columns if c.lower() == "volume"]
    vol_flag = vol_pole = vol_ratio = None
    if vol_cols:
        vol = df[vol_cols[0]]
        vol_pole = float(vol.iloc[i0: i1 + 1].mean())
        vol_flag = float(vol.iloc[j0: j1 + 1].mean())
        vol_ratio = (vol_flag / vol_pole) if vol_pole else None

    feats = {
        "pattern_kind": 1.0 if pat.kind == "flag" else 0.0,
        "pole_len_bars": float(i1 - i0),
        "pole_height": float(pat.pole.height),
        "pole_score": float(pat.pole.score),
        "cons_len_bars": float(j1 - j0 + 1),
        "retrace_ratio": float(pat.cons.retrace_ratio),
        "upper_r2": float(pat.upper.r2) if pat.upper.r2 is not None else float("nan"),
        "lower_r2": float(pat.lower.r2) if pat.lower.r2 is not None else float("nan"),
        "theta_u": float(theta_u),
        "theta_l": float(theta_l),
        "theta_diff": float(theta_diff),
        "theta_channel": float(theta_channel),
        "width_start": float(w0),
        "width_end": float(w1),
        "width_shrink_ratio": float(shrink_ratio),
        "atr_j1": float(atr_j1),
        "atr_frac_price": float(atr_frac),
    }

    # Include classifier features (prefixed) if present
    for k, v in pat.features.items():
        if isinstance(v, (int, float)):
            feats[f"geom_{k}"] = float(v)

    # Optional volumes
    if vol_flag is not None:
        feats["vol_mean_pole"] = float(vol_pole)
        feats["vol_mean_cons"] = float(vol_flag)
        feats["vol_cons_vs_pole"] = float(vol_ratio) if vol_ratio is not None else float("nan")

    return feats


# ---- small helpers -----------------------------------------------------------

def _angle_deg(slope: float) -> float:
    return math.degrees(math.atan(slope))


def _band_width(upper: BoundaryLine, lower: BoundaryLine, x: int) -> float:
    return (upper.slope * x + upper.intercept) - (lower.slope * x + lower.intercept)
