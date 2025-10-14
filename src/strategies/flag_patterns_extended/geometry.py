# angles, width shrink, apex math

from __future__ import annotations

import math
from typing import Optional, Tuple, Dict, Literal

import numpy as np

from .detector import BoundaryLine, ConsolidationStats

Direction = Literal["bull", "bear"]

# -------- Basic geometry helpers --------

def angle_deg(slope: float) -> float:
    """Map slope to angle in degrees (scale invariant)."""
    return math.degrees(math.atan(slope))


def line_value_at(line: BoundaryLine, x: int | float) -> float:
    """Evaluate y = m*x + b."""
    return float(line.slope) * float(x) + float(line.intercept)


def band_width_at(upper: BoundaryLine, lower: BoundaryLine, x: int | float) -> float:
    """Distance between the two fitted lines at position x."""
    return line_value_at(upper, x) - line_value_at(lower, x)


def intersection_x(upper: BoundaryLine, lower: BoundaryLine, eps: float = 1e-9) -> Optional[float]:
    """X-coordinate of intersection; None if (near) parallel."""
    denom = float(upper.slope) - float(lower.slope)
    if abs(denom) < eps:
        return None
    return (float(lower.intercept) - float(upper.intercept)) / denom


def channel_slope_deg(upper: BoundaryLine, lower: BoundaryLine) -> float:
    """Approximate channel slope as mean of the two angles."""
    return 0.5 * (angle_deg(upper.slope) + angle_deg(lower.slope))


# -------- Touch counting (optional diagnostic) --------

def count_touches(
    highs: np.ndarray,
    lows: np.ndarray,
    upper: BoundaryLine,
    lower: BoundaryLine,
    xs: np.ndarray,
    *,
    tol_abs: Optional[float] = None,
) -> Tuple[int, int]:
    """
    Count how many times highs/lows are within `tol_abs` of the fitted lines.
    If tol_abs is None, use 10% of the median band width as tolerance.
    """
    widths = band_width_at_array(upper, lower, xs)
    med_w = float(np.median(widths)) if len(widths) else 0.0
    tol = tol_abs if (tol_abs is not None) else max(1e-9, 0.10 * med_w)

    up_vals = line_value_at_array(upper, xs)
    lo_vals = line_value_at_array(lower, xs)

    touch_u = int(np.sum(np.abs(highs - up_vals) <= tol))
    touch_l = int(np.sum(np.abs(lows - lo_vals) <= tol))
    return touch_u, touch_l


def line_value_at_array(line: BoundaryLine, xs: np.ndarray) -> np.ndarray:
    return (float(line.slope) * xs.astype(float)) + float(line.intercept)


def band_width_at_array(upper: BoundaryLine, lower: BoundaryLine, xs: np.ndarray) -> np.ndarray:
    return line_value_at_array(upper, xs) - line_value_at_array(lower, xs)


# -------- Classification helpers (used by detector) --------

def is_flag_parallel(
    upper: BoundaryLine,
    lower: BoundaryLine,
    *,
    parallel_angle_max_deg: float,
    channel_slope_cap_deg: float,
    channel_gentle_deg: float,
    direction: Direction,
    highs: np.ndarray,
    lows: np.ndarray,
    xs: np.ndarray,
    min_touches_per_line: int,
    touch_tol_frac_of_width: float = 0.10,
) -> Tuple[bool, Dict[str, float]]:
    """
    Channel must be near-parallel, counter-trend unless very gentle, and have sufficient touches.
    """
    theta_u = angle_deg(upper.slope)
    theta_l = angle_deg(lower.slope)
    theta_diff = abs(theta_u - theta_l)
    theta_channel = 0.5 * (theta_u + theta_l)

    ok_parallel = theta_diff <= parallel_angle_max_deg

    if abs(theta_channel) <= channel_gentle_deg:
        ok_channel = True
        is_countertrend = True if abs(theta_channel) <= channel_gentle_deg else False
    else:
        if direction == "bull":
            is_countertrend = theta_channel < 0
        else:
            is_countertrend = theta_channel > 0
        ok_channel = is_countertrend and (abs(theta_channel) <= channel_slope_cap_deg)

    widths = band_width_at_array(upper, lower, xs)
    med_w = float(np.median(widths)) if len(widths) else 0.0
    tol = max(1e-9, touch_tol_frac_of_width * med_w)
    up_vals = line_value_at_array(upper, xs)
    lo_vals = line_value_at_array(lower, xs)
    touch_u = int(np.sum(np.abs(highs - up_vals) <= tol))
    touch_l = int(np.sum(np.abs(lows - lo_vals) <= tol))
    ok_touches = (touch_u >= min_touches_per_line) and (touch_l >= min_touches_per_line)

    feats = {
        "theta_u": theta_u,
        "theta_l": theta_l,
        "theta_diff": theta_diff,
        "theta_channel": theta_channel,
        "flag_is_countertrend": 1.0 if is_countertrend else 0.0,
        "touch_u": float(touch_u),
        "touch_l": float(touch_l),
        "touch_tol_abs": float(tol),
    }
    return (ok_parallel and ok_channel and ok_touches), feats


def is_pennant_converging(
    upper: BoundaryLine,
    lower: BoundaryLine,
    cons: ConsolidationStats,
    *,
    width_shrink_ratio_max: float,
    apex_pos_factor_max: float,
    direction: Direction,
    require_slope_opposition: bool = True,
    highs: Optional[np.ndarray] = None,
    lows: Optional[np.ndarray] = None,
    xs: Optional[np.ndarray] = None,
    min_touches_per_line: int = 0,
    touch_tol_frac_of_width: float = 0.10,
) -> Tuple[bool, Optional[float], Dict[str, float]]:
    s_u, s_l = upper.slope, lower.slope
    if require_slope_opposition:
        if direction == "bull":
            slope_ok = (s_u <= 0.0) and (s_l >= 0.0)
        else:
            slope_ok = (s_u >= 0.0) and (s_l <= 0.0)
    else:
        slope_ok = True

    w0 = band_width_at(upper, lower, cons.j0)
    w1 = band_width_at(upper, lower, cons.j1)
    shrink_ratio = (w1 / w0) if w0 != 0 else float("inf")

    apex_x = intersection_x(upper, lower)
    apex_ok = False
    if apex_x is not None:
        max_right = cons.j1 + apex_pos_factor_max * (cons.j1 - cons.j0 + 1)
        apex_ok = apex_x <= max_right

    touches_ok = True
    touch_u = touch_l = 0
    tol = 0.0
    if (min_touches_per_line > 0) and highs is not None and lows is not None and xs is not None:
        widths = band_width_at_array(upper, lower, xs)
        med_w = float(np.median(widths)) if len(widths) else 0.0
        tol = max(1e-9, touch_tol_frac_of_width * med_w)
        up_vals = line_value_at_array(upper, xs)
        lo_vals = line_value_at_array(lower, xs)
        touch_u = int(np.sum(np.abs(highs - up_vals) <= tol))
        touch_l = int(np.sum(np.abs(lows - lo_vals) <= tol))
        touches_ok = (touch_u >= min_touches_per_line) and (touch_l >= min_touches_per_line)

    feats = {
        "width_start": w0,
        "width_end": w1,
        "width_shrink_ratio": shrink_ratio,
        "apex_x": float(apex_x) if apex_x is not None else float("nan"),
        "pen_slope_opposed": 1.0 if slope_ok and require_slope_opposition else 0.0,
        "touch_u": float(touch_u),
        "touch_l": float(touch_l),
        "touch_tol_abs": float(tol),
    }

    ok = slope_ok and (shrink_ratio <= width_shrink_ratio_max) and apex_ok and touches_ok
    return ok, apex_x, feats
