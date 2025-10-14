# thin wrapper: choose PIP or DC based on config

from __future__ import annotations

from typing import List, Tuple, Optional
import numpy as np
import pandas as pd

# We try to import PIP and Directional Change from wherever you kept them.
# Fall back to a tiny local swing-high/low detector if unavailable.

def _try_import_pip():
    for mod in (
        ".perceptually_important",
        "..flag_patterns.perceptually_important",
        "perceptually_important",
    ):
        try:
            pkg = __import__(mod, fromlist=["pip"])
            return getattr(pkg, "pip")
        except Exception:
            continue
    return None


def _try_import_dc():
    for mod in (
        ".directional_change",
        "..flag_patterns.directional_change",
        "directional_change",
    ):
        try:
            pkg = __import__(mod, fromlist=["directional_change_stream"])
            # Different repos expose different APIs; adapt later if needed.
            return getattr(pkg, "directional_change_stream")
        except Exception:
            continue
    return None


def pivots_pip(
    prices: pd.Series,
    order: int,
) -> List[int]:
    """
    Wrapper around PIP. If missing, uses a simple local-extrema fallback.
    Returns pivot indices (subset of the series index positions).
    """
    pip_fn = _try_import_pip()
    if pip_fn is not None:
        # Expectation: pip(prices, order) -> list of (index, value) or indices.
        try:
            pts = pip_fn(prices.to_numpy(dtype=float), order)
            # Normalize outputs to indices
            if isinstance(pts, list) and len(pts) and isinstance(pts[0], (tuple, list)):
                return [int(p[0]) for p in pts]
            elif isinstance(pts, np.ndarray):
                return [int(i) for i in pts.tolist()]
            else:
                return [int(i) for i in pts]
        except Exception:
            pass
    # Fallback: simple local extrema using window=order
    return simple_local_pivots(prices, window=max(2, order // 2))


def pivots_directional_change(
    prices: pd.Series,
    epsilon: float,
) -> List[int]:
    """
    Wrapper around DC. If missing, uses fallback extrema based on epsilon moves.
    """
    dc_fn = _try_import_dc()
    if dc_fn is not None:
        try:
            # Example API; adapt to actual function signature if needed.
            indices = dc_fn(prices.to_numpy(dtype=float), epsilon)
            return [int(i) for i in indices]
        except Exception:
            pass
    # Fallback: mark a pivot when absolute change exceeds epsilon from last pivot
    idxs: List[int] = []
    arr = prices.to_numpy(dtype=float)
    if len(arr) == 0:
        return idxs
    last_idx = 0
    last_price = arr[0]
    for i in range(1, len(arr)):
        if abs(arr[i] - last_price) >= epsilon:
            idxs.append(i)
            last_idx, last_price = i, arr[i]
    return idxs


def simple_local_pivots(prices: pd.Series, window: int = 3) -> List[int]:
    """
    Mark local maxima/minima within a rolling window; returns both highs and lows.
    """
    x = prices.to_numpy(dtype=float)
    n = len(x)
    pivots: List[int] = []
    w = max(1, window)
    for i in range(w, n - w):
        seg = x[i - w: i + w + 1]
        if np.argmax(seg) == w or np.argmin(seg) == w:
            pivots.append(i)
    return pivots


def get_pivots(
    df: pd.DataFrame,
    method: str,
    *,
    pip_order: Optional[int] = None,
    dc_epsilon: Optional[float] = None,
    price_col: str = "close",
) -> List[int]:
    """
    Unified entry: returns pivot indices for the selected method.
    """
    prices = df[price_col].astype(float)
    if method == "PIP":
        return pivots_pip(prices, order=int(pip_order or 8))
    elif method == "DirectionalChange":
        return pivots_directional_change(prices, epsilon=float(dc_epsilon or prices.std() * 0.3))
    else:
        return simple_local_pivots(prices, window=3)
