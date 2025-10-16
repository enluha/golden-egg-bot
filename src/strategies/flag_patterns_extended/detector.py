# /src/strategies/flag_patterns_extended/detector.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple, Literal, Dict, Any
import math
import numpy as np
import pandas as pd

from .config import Config
from .geometry import (
    angle_deg,
    band_width_at,
    intersection_x,
    is_flag_parallel,
    is_pennant_converging,
)
from .pivots import get_pivots

Direction = Literal["bull", "bear"]
PatternKind = Literal["flag", "pennant"]


# ---------------- Data structures ----------------

@dataclass(frozen=True)
class BoundaryLine:
    """y = slope * x + intercept, evaluated in bar index space."""
    slope: float
    intercept: float
    r2: Optional[float] = None
    touches: Optional[int] = None


@dataclass(frozen=True)
class PoleStats:
    i0: int                 # pole start index
    i1: int                 # pole end index
    height: float           # abs(price[i1] - price[i0])
    score: float            # normalized (e.g., ATR multiple)
    direction: Direction


@dataclass(frozen=True)
class ConsolidationStats:
    j0: int                 # consolidation start (usually i1+1)
    j1: int                 # consolidation end (inclusive)
    retrace_ratio: float    # depth / pole_height (relative to pole leg)
    width_start: float      # (approx width at j0; diagnostic)
    width_end: float        # (approx width at j1; diagnostic)


@dataclass(frozen=True)
class DetectedPattern:
    """Pure detection result, NO lookahead beyond j1."""
    kind: PatternKind
    pole: PoleStats
    cons: ConsolidationStats
    upper: BoundaryLine
    lower: BoundaryLine
    apex_x: Optional[float]  # x-coordinate of line intersection (if converging)
    features: Dict[str, Any] # geometry diagnostics for ranking


# ---------------- Public entry-point ----------------

def detect_patterns(
    df: pd.DataFrame,
    cfg: Config,
    *,
    price_col: str = "close",
) -> List[DetectedPattern]:
    """
    Scan `df` and return flag/pennant detections using ONLY data up to consolidation end.
    Expected columns: open, high, low, close (and volume if you'll use filters later).
    """
    cfg.validate()
    atr = compute_atr(df["high"], df["low"], df["close"], cfg.atr_len)

    patterns: List[DetectedPattern] = []

    t = cfg.pole_lookback_k
    n = len(df)
    while t < n - cfg.min_consolidation_bars:
        pole = _detect_pole_at_index(df, atr, t, cfg, price_col=price_col)
        if pole is None:
            t += 1
            continue

        cons = _find_consolidation(df, pole, cfg, price_col=price_col)
        if cons is None:
            t = pole.i1 + 1
            continue

        # Fit boundary lines over [cons.j0, cons.j1]
        upper, lower = _fit_boundaries(df, cons, cfg)

        # Prepare arrays for touch statistics
        xs = np.arange(cons.j0, cons.j1 + 1, dtype=float)
        highs = df["high"].iloc[cons.j0: cons.j1 + 1].to_numpy(dtype=float)
        lows = df["low"].iloc[cons.j0: cons.j1 + 1].to_numpy(dtype=float)

        # Classify with shared geometry helpers
        kind, apex_x, geom_feats = _classify_flag_or_pennant(
            upper=upper,
            lower=lower,
            cons=cons,
            cfg=cfg,
            direction=pole.direction,
            highs=highs,
            lows=lows,
            xs=xs,
            pole_height=pole.height,
            pole_len_bars=(pole.i1 - pole.i0),
        )
        if kind is None:
            t = cons.j1  # skip ahead to end of this consolidation window
            continue

        # Enforce retracement cap relative to the POLE
        if cons.retrace_ratio > cfg.max_retrace_ratio:
            t = cons.j1
            continue

        # (Optional) median-close-above check relative to pole height
        if cfg.median_close_above is not None:
            # simple diagnostic: median close should stay above pole_high - c * pole_height (bull) or vice versa
            closes = df["close"].iloc[cons.j0: cons.j1 + 1].to_numpy(dtype=float)
            if pole.direction == "bull":
                pole_high = float(df["high"].iloc[pole.i0: pole.i1 + 1].max())
                threshold = pole_high - cfg.median_close_above * pole.height
                if np.median(closes) < threshold:
                    t = cons.j1
                    continue
            else:
                pole_low = float(df["low"].iloc[pole.i0: pole.i1 + 1].min())
                threshold = pole_low + cfg.median_close_above * pole.height
                if np.median(closes) > threshold:
                    t = cons.j1
                    continue

        fit_meta = {
            "boundary_fit_mode": cfg.boundary_fit_mode,
            "n_pivot_hi": float(upper.touches or 0.0),
            "n_pivot_lo": float(lower.touches or 0.0),
        }

        # Build combined features (geometry helpers already computed angles/width/apex)
        features: Dict[str, Any] = {
            **geom_feats,
            **fit_meta,
            "pole_len_bars": pole.i1 - pole.i0,
            "pole_height": pole.height,
            "pole_score": pole.score,
            "retrace_ratio": cons.retrace_ratio,
        }

        patterns.append(
            DetectedPattern(
                kind=kind,
                pole=pole,
                cons=cons,
                upper=upper,
                lower=lower,
                apex_x=apex_x,
                features=features,
            )
        )

        # De-duplicate near-by detections if desired
        t = max(t + 1, cons.j1 + cfg.dedup_distance_bars)

    return patterns


# ---------------- Helpers ----------------

def compute_atr(
    high: pd.Series, low: pd.Series, close: pd.Series, length: int
) -> pd.Series:
    """Wilder ATR; simple implementation sufficient here."""
    tr1 = (high - low).abs()
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / max(length, 1), adjust=False).mean()
    return atr


def _detect_pole_at_index(
    df: pd.DataFrame,
    atr: pd.Series,
    t: int,
    cfg: Config,
    *,
    price_col: str,
) -> Optional[PoleStats]:
    """Volatility-aware impulse over [t-k, t] (ATR-normalized starter)."""
    k = cfg.pole_lookback_k
    if t - k < 0:
        return None
    p0 = float(df[price_col].iat[t - k])
    p1 = float(df[price_col].iat[t])
    height = abs(p1 - p0)
    direction: Direction = "bull" if p1 >= p0 else "bear"

    if cfg.pole_method == "atr_normalized":
        # average ATR in the lookback window (robust to local spikes)
        denom = float(atr.iloc[max(t - cfg.atr_len, 0): t + 1].mean())
        score = height / denom if denom > 0 else 0.0
        if score < cfg.pole_score_min:
            return None
    else:
        # Other methods (slope_zscore/quantile) can be added later
        return None

    return PoleStats(i0=t - k, i1=t, height=height, score=score, direction=direction)


def _find_consolidation(
    df: pd.DataFrame,
    pole: PoleStats,
    cfg: Config,
    *,
    price_col: str,
) -> Optional[ConsolidationStats]:
    """
    Search forward from pole end (i1) for a compact consolidation window [j0, j1].
    Uses the minimum required duration initially; you can extend heuristics later.
    """
    j0 = pole.i1 + 1
    j1_max = min(pole.i1 + cfg.max_consolidation_bars, len(df) - 1)
    j1 = j0 + cfg.min_consolidation_bars - 1
    if j0 >= len(df) or j1 > j1_max:
        return None

    # Compute retracement depth within [j0, j1] relative to the *pole leg*
    pole_high = float(df["high"].iloc[pole.i0: pole.i1 + 1].max())
    pole_low = float(df["low"].iloc[pole.i0: pole.i1 + 1].min())
    pole_range = max(1e-12, pole_high - pole_low)

    if pole.direction == "bull":
        min_low = float(df["low"].iloc[j0: j1 + 1].min())
        retrace_ratio = (pole_high - min_low) / pole_range
    else:
        max_high = float(df["high"].iloc[j0: j1 + 1].max())
        retrace_ratio = (max_high - pole_low) / pole_range

    # Rough width diagnostics from raw bars (final width from fitted lines in classifier)
    width_start = float(df["high"].iloc[j0]) - float(df["low"].iloc[j0])
    width_end = float(df["high"].iloc[j1]) - float(df["low"].iloc[j1])

    return ConsolidationStats(
        j0=j0,
        j1=j1,
        retrace_ratio=float(retrace_ratio),
        width_start=float(width_start),
        width_end=float(width_end),
    )


def _fit_boundaries(
    df: pd.DataFrame,
    cons: ConsolidationStats,
    cfg: Optional[Config] = None,
) -> Tuple[BoundaryLine, BoundaryLine]:
    """
    Fit upper/lower lines over [j0, j1]. If pivot-based mode is active we
    regress on swing points chosen by the configured pivot routine; otherwise
    fall back to bar-by-bar OLS (prior behaviour).
    """
    if cfg is not None and cfg.boundary_fit_mode == "pivots":
        pivot_ok, up, lo = _fit_boundaries_pivots(df, cons, cfg)
        if pivot_ok and up is not None and lo is not None:
            return up, lo

    # ----- bars OLS fallback (legacy behaviour) -----
    x = np.arange(cons.j0, cons.j1 + 1, dtype=float)
    y_hi = df["high"].iloc[cons.j0: cons.j1 + 1].to_numpy(dtype=float)
    y_lo = df["low"].iloc[cons.j0: cons.j1 + 1].to_numpy(dtype=float)

    s_u, i_u = _ols(x, y_hi)
    s_l, i_l = _ols(x, y_lo)
    r2_u = _r2(x, y_hi, s_u, i_u)
    r2_l = _r2(x, y_lo, s_l, i_l)

    upper = BoundaryLine(slope=float(s_u), intercept=float(i_u), r2=float(r2_u), touches=None)
    lower = BoundaryLine(slope=float(s_l), intercept=float(i_l), r2=float(r2_l), touches=None)
    return upper, lower


def _fit_boundaries_pivots(
    df: pd.DataFrame,
    cons: ConsolidationStats,
    cfg: Config,
) -> Tuple[bool, Optional[BoundaryLine], Optional[BoundaryLine]]:
    """
    Regress boundaries using pivot-selected swing highs/lows inside [j0, j1].
    Returns (success, upper_line, lower_line); on failure caller falls back.
    """
    j0, j1 = cons.j0, cons.j1
    win = df.iloc[j0: j1 + 1]

    # Select price series feeding the pivot routine
    if cfg.pivot_price_for_fit == "hl2":
        price_series = (win["high"].astype(float) + win["low"].astype(float)) * 0.5
        pivot_df = win.copy()
        price_col_name = "__pivot_price__"
        pivot_df[price_col_name] = price_series
    elif cfg.pivot_price_for_fit == "ohlc4":
        price_series = (
            win["open"].astype(float)
            + win["high"].astype(float)
            + win["low"].astype(float)
            + win["close"].astype(float)
        ) * 0.25
        pivot_df = win.copy()
        price_col_name = "__pivot_price__"
        pivot_df[price_col_name] = price_series
    else:
        pivot_df = win
        price_col_name = "close"

    # Determine epsilon for DC pivots if requested
    dc_eps: Optional[float] = None
    if cfg.pivot_method == "DirectionalChange" and cfg.dc_epsilon_atr_mult is not None:
        local_atr = compute_atr(win["high"], win["low"], win["close"], cfg.atr_len)
        if not local_atr.empty:
            last_atr = float(local_atr.iloc[-1])
            if math.isfinite(last_atr) and last_atr > 0.0:
                dc_eps = float(cfg.dc_epsilon_atr_mult) * last_atr

    piv_idxs = get_pivots(
        pivot_df,
        method=cfg.pivot_method,
        pip_order=cfg.pip_order,
        dc_epsilon=dc_eps,
        price_col=price_col_name,
    )

    if len(piv_idxs) < 3:
        return False, None, None

    price_vals = pivot_df[price_col_name].astype(float).to_numpy()
    piv_sorted = sorted({int(i) for i in piv_idxs if 0 <= int(i) < len(price_vals)})
    if len(piv_sorted) < 3:
        return False, None, None

    highs_idx: List[int] = []
    lows_idx: List[int] = []
    for k in range(1, len(piv_sorted) - 1):
        p = piv_sorted[k]
        left = piv_sorted[k - 1]
        right = piv_sorted[k + 1]
        v = float(price_vals[p])
        if v >= float(price_vals[left]) and v >= float(price_vals[right]):
            highs_idx.append(p)
        if v <= float(price_vals[left]) and v <= float(price_vals[right]):
            lows_idx.append(p)

    if (
        len(highs_idx) < cfg.min_pivot_points_per_line
        or len(lows_idx) < cfg.min_pivot_points_per_line
    ):
        return False, None, None

    # Map back to absolute indices for regression
    hi_abs = [j0 + idx for idx in highs_idx]
    lo_abs = [j0 + idx for idx in lows_idx]

    x_hi = np.array(hi_abs, dtype=float)
    y_hi = df["high"].iloc[hi_abs].astype(float).to_numpy()
    x_lo = np.array(lo_abs, dtype=float)
    y_lo = df["low"].iloc[lo_abs].astype(float).to_numpy()

    s_u, i_u = _ols(x_hi, y_hi)
    s_l, i_l = _ols(x_lo, y_lo)
    r2_u = _r2(x_hi, y_hi, s_u, i_u)
    r2_l = _r2(x_lo, y_lo, s_l, i_l)

    upper = BoundaryLine(slope=float(s_u), intercept=float(i_u), r2=float(r2_u), touches=len(highs_idx))
    lower = BoundaryLine(slope=float(s_l), intercept=float(i_l), r2=float(r2_l), touches=len(lows_idx))
    return True, upper, lower


def _classify_flag_or_pennant(
    upper: BoundaryLine,
    lower: BoundaryLine,
    cons: ConsolidationStats,
    cfg: Config,
    *,
    direction: Direction,
    highs: np.ndarray,
    lows: np.ndarray,
    xs: np.ndarray,
    pole_height: float,
    pole_len_bars: int,
) -> Tuple[Optional[PatternKind], Optional[float], Dict[str, Any]]:
    """
    Delegate geometry decisions to `geometry.py` helpers so all math lives in one place.
    Returns (kind, apex_x, features).
    """
    features: Dict[str, Any] = {}

    # 1) Evaluate flag (parallel) criteria
    ok_flag, flag_feats = is_flag_parallel(
        upper,
        lower,
        parallel_angle_max_deg=cfg.parallel_angle_max_deg,
        channel_slope_cap_deg=cfg.channel_slope_cap_deg,
        channel_gentle_deg=cfg.channel_gentle_deg,
        direction=direction,
        highs=highs,
        lows=lows,
        xs=xs,
        min_touches_per_line=cfg.min_touches_per_line,
        touch_tol_frac_of_width=cfg.touch_tol_frac_of_width,
    )
    features.update({f"flag_{k}": v for k, v in flag_feats.items()})
    # Prepare flag features (without early return when selection is enforced)
    w0_flag = band_width_at(upper, lower, cons.j0)
    w1_flag = band_width_at(upper, lower, cons.j1)
    flag_variant_feats = {
        "width_start": w0_flag,
        "width_end": w1_flag,
        "width_shrink_ratio": (w1_flag / w0_flag) if w0_flag != 0 else float("inf"),
        "apex_x": float("nan"),
        "variant": "flag_parallel",
    }

    # 2) Evaluate pennant criteria
    ok_pen, apex_x, pen_feats = is_pennant_converging(
        upper,
        lower,
        cons,
        width_shrink_ratio_max=cfg.width_shrink_ratio_max,
        apex_pos_factor_max=cfg.apex_pos_factor_max,
        direction=direction,
        require_slope_opposition=cfg.pennant_require_slope_opposition,
        highs=highs,
        lows=lows,
        xs=xs,
        min_touches_per_line=0,
        touch_tol_frac_of_width=cfg.touch_tol_frac_of_width,
    )
    features.update({f"pen_{k}": v for k, v in pen_feats.items()})
    pen_variant_feats = {
        "apex_x": float(apex_x) if apex_x is not None else float("nan"),
        "variant": "pennant",
    }

    # 3) Evaluate trendline-style flag constraints (without returning yet)
    ok_trend = False
    trend_feats: Dict[str, Any] = {}
    if getattr(cfg, "enable_trendline_variant", False):
        # Estimate pole and flag measures from indices and fitted band
        w0 = band_width_at(upper, lower, cons.j0)
        w1 = band_width_at(upper, lower, cons.j1)
        band_w = 0.5 * (w0 + w1)
        # Use realized range within consolidation window as height proxy
        flag_height = float(np.max(highs) - np.min(lows)) if len(highs) and len(lows) else abs(w0 - w1) + min(w0, w1)
        # Defensive guards
        pole_height_safe = max(1e-9, float(pole_height))
        pole_len_safe = max(1, int(pole_len_bars))
        # Apply relative caps: require a relatively narrow band compared to the pole's height
        width_ok = (band_w <= cfg.trend_flag_width_pole_max * pole_height_safe)
        height_ok = (flag_height <= cfg.trend_flag_height_pole_max * pole_height_safe)
        # Avoid wildly expanding channels
        non_expand_ok = (w1 <= 1.5 * max(1e-12, w0))
        if width_ok and height_ok and non_expand_ok:
            ok_trend = True
            trend_feats.update(
                {
                    "trend_band_width": float(band_w),
                    "trend_flag_height": float(flag_height),
                    "trend_pole_width_bars": float(pole_len_safe),
                    "trend_pole_height": float(pole_height_safe),
                    "variant": "flag_trendline",
                }
            )

    # Decide which variant to emit based on selection (no prioritization across variants when selected)
    selected = getattr(cfg, "selected_variant", None)
    if selected is not None:
        if selected == "flag_parallel" and ok_flag:
            out = dict(features)
            out.update(flag_variant_feats)
            return "flag", None, out
        if selected == "pennant" and ok_pen:
            out = dict(features)
            out.update(pen_variant_feats)
            return "pennant", apex_x, out
        if selected == "flag_trendline" and ok_trend:
            out = dict(features)
            out.update(trend_feats)
            return "flag", None, out
        # When a selection is enforced but not satisfied, this consolidation is ignored
        theta_u = angle_deg(upper.slope)
        theta_l = angle_deg(lower.slope)
        w0 = band_width_at(upper, lower, cons.j0)
        w1 = band_width_at(upper, lower, cons.j1)
        features.update(
            dict(
                theta_u=theta_u,
                theta_l=theta_l,
                theta_diff=abs(theta_u - theta_l),
                theta_channel=0.5 * (theta_u + theta_l),
                width_start=w0,
                width_end=w1,
                width_shrink_ratio=(w1 / w0) if w0 != 0 else float("inf"),
                apex_x=float(intersection_x(upper, lower) or float("nan")),
            )
        )
        return None, intersection_x(upper, lower), features

    # Default behaviour (no selection): keep previous prioritization
    if ok_flag:
        out = dict(features)
        out.update(flag_variant_feats)
        return "flag", None, out
    if ok_pen:
        out = dict(features)
        out.update(pen_variant_feats)
        return "pennant", apex_x, out
    if ok_trend:
        out = dict(features)
        out.update(trend_feats)
        return "flag", None, out

    # Neither condition satisfied
    # Still emit basic angle/width diagnostics for debugging downstream
    theta_u = angle_deg(upper.slope)
    theta_l = angle_deg(lower.slope)
    w0 = band_width_at(upper, lower, cons.j0)
    w1 = band_width_at(upper, lower, cons.j1)
    features.update(
        dict(
            theta_u=theta_u,
            theta_l=theta_l,
            theta_diff=abs(theta_u - theta_l),
            theta_channel=0.5 * (theta_u + theta_l),
            width_start=w0,
            width_end=w1,
            width_shrink_ratio=(w1 / w0) if w0 != 0 else float("inf"),
            apex_x=float(intersection_x(upper, lower) or float("nan")),
        )
    )
    return None, intersection_x(upper, lower), features


# ---------------- Small numeric utils ----------------

def _ols(x: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    X = np.vstack([x, np.ones_like(x)]).T
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    slope, intercept = beta[0], beta[1]
    return float(slope), float(intercept)


def _r2(x: np.ndarray, y: np.ndarray, slope: float, intercept: float) -> float:
    y_hat = slope * x + intercept
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
