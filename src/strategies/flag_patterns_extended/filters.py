# volume dry-up, breakout expansion, trend filters

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from .detector import DetectedPattern
from .detector import compute_atr  # reuse same ATR impl


# ---- Core stats (EMA/SMA/RMA/ADX/OBV) ---------------------------------------

def sma(x: pd.Series, length: int) -> pd.Series:
    return x.rolling(length, min_periods=length).mean()


def ema(x: pd.Series, length: int) -> pd.Series:
    return x.ewm(alpha=2.0 / (length + 1.0), adjust=False).mean()


def rma_wilder(x: pd.Series, length: int) -> pd.Series:
    """Wilder's RMA (like EMA with alpha=1/length)."""
    return x.ewm(alpha=1.0 / max(length, 1), adjust=False).mean()


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    tr1 = (high - low).abs()
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def atr_wilder(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> pd.Series:
    return rma_wilder(true_range(high, low, close), length)


def adx_wilder(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    length: int = 14
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Returns (+DI, -DI, ADX) using Wilder smoothing.
    """
    up = high.diff()
    dn = low.shift(1) - low

    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)

    tr = true_range(high, low, close)
    atr = rma_wilder(tr, length)

    plus_di = pd.Series(100.0 * rma_wilder(pd.Series(plus_dm, index=high.index), length) / atr, index=high.index)
    minus_di = pd.Series(100.0 * rma_wilder(pd.Series(minus_dm, index=high.index), length) / atr, index=high.index)

    dx = (100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(0.0)
    adx = rma_wilder(dx, length)
    return plus_di, minus_di, adx


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume."""
    sign = np.sign(close.diff().fillna(0.0))
    return (sign * volume).fillna(0.0).cumsum()


# ---- Simple filters (volume dry-up, breakout expansion, trend) --------------

def volume_dryup_ratio(
    df: pd.DataFrame,
    pat: DetectedPattern,
    *,
    volume_col: str = "volume",
) -> Optional[float]:
    """
    mean(volume over consolidation) / mean(volume over pole)
    Returns None if volume column is missing.
    """
    if volume_col not in df.columns:
        return None
    i0, i1 = pat.pole.i0, pat.pole.i1
    j0, j1 = pat.cons.j0, pat.cons.j1

    vol = df[volume_col]
    vol_pole = float(vol.iloc[i0: i1 + 1].mean())
    vol_cons = float(vol.iloc[j0: j1 + 1].mean())
    return (vol_cons / vol_pole) if vol_pole > 0 else None


def passes_volume_dryup(
    df: pd.DataFrame,
    pat: DetectedPattern,
    max_ratio: Optional[float],
    *,
    volume_col: str = "volume",
) -> bool:
    """
    True if volume dry-up condition is satisfied (or filter disabled with None).
    """
    if max_ratio is None:
        return True
    r = volume_dryup_ratio(df, pat, volume_col=volume_col)
    return True if r is None else (r <= max_ratio)


def volume_breakout_expansion(
    df: pd.DataFrame,
    breakout_idx: int,
    ma_len: int = 20,
    *,
    volume_col: str = "volume",
) -> Optional[Dict[str, float]]:
    """
    Compute breakout volume stats at breakout_idx:
      - vol: breakout bar volume
      - vol_ma: rolling mean volume
      - mult: vol / vol_ma
      - z: z-score vs rolling window (mean, std)
    Returns None if no volume column.
    """
    if volume_col not in df.columns:
        return None

    vol = df[volume_col].astype(float)
    vol_ma = sma(vol, ma_len)
    vol_std = vol.rolling(ma_len, min_periods=ma_len).std(ddof=0)

    v = float(vol.iat[breakout_idx])
    m = float(vol_ma.iat[breakout_idx]) if not np.isnan(vol_ma.iat[breakout_idx]) else np.nan
    s = float(vol_std.iat[breakout_idx]) if not np.isnan(vol_std.iat[breakout_idx]) else np.nan

    mult = v / m if (m and m > 0) else np.nan
    z = (v - m) / s if (s and s > 0) else np.nan
    return {"vol": v, "vol_ma": m, "mult": mult, "z": z}


def passes_volume_breakout(
    df: pd.DataFrame,
    breakout_idx: int,
    *,
    mult_min: Optional[float] = None,
    z_min: Optional[float] = None,
    ma_len: int = 20,
    volume_col: str = "volume",
) -> bool:
    """
    True if breakout volume passes either multiplier or z-score threshold.
    If both thresholds are None, the filter is disabled.
    """
    if mult_min is None and z_min is None:
        return True
    stats = volume_breakout_expansion(df, breakout_idx, ma_len=ma_len, volume_col=volume_col)
    if stats is None:
        return True  # no volume available -> don't constrain by default
    ok_mult = True if mult_min is None else (stats["mult"] >= mult_min)
    ok_z = True if z_min is None else (stats["z"] >= z_min)
    return ok_mult and ok_z


def adx_trend_ok(
    df: pd.DataFrame,
    idx: int,
    *,
    adx_len: int = 14,
    adx_min: Optional[float] = None,
) -> bool:
    """
    Non-directional trend strength at index via ADX.
    If adx_min is None, filter disabled.
    """
    if adx_min is None:
        return True
    _, _, adx = adx_wilder(df["high"], df["low"], df["close"], adx_len)
    if idx >= len(adx):
        return False
    val = float(adx.iat[idx])
    return val >= adx_min


def ma_slope(
    series: pd.Series,
    length: int,
) -> float:
    """
    Linear-regression slope over `length` bars (price units per bar).
    For scale-free version, divide by series.mean() or by ATR.
    """
    if len(series) < length:
        return float("nan")
    y = series.iloc[-length:].astype(float).to_numpy()
    x = np.arange(length, dtype=float)
    x = (x - x.mean())  # center to reduce intercept influence
    slope = float(np.dot(x, y) / np.dot(x, x))
    return slope


def ma_slope_ok(
    df: pd.DataFrame,
    idx: int,
    *,
    ma_len: int = 50,
    slope_min: float = 0.0,
    price_col: str = "close",
    normalize_by_price: bool = True,
) -> bool:
    """
    Directional check using slope of a moving average (or raw price) near idx.
    - Uses a trailing window ending at idx.
    - If normalize_by_price=True, slope is scaled by mean price to be unitless.
    """
    if idx < ma_len:
        return True  # don't constrain early bars

    ma = sma(df[price_col].astype(float), ma_len)
    window = ma.iloc[idx - ma_len + 1: idx + 1]
    slope = ma_slope(window, ma_len)
    if normalize_by_price:
        denom = float(window.mean())
        if denom > 0:
            slope /= denom
    return slope >= slope_min


# ---- Composite convenience (apply at consolidation end or breakout) ----------

def passes_basic_filters(
    df: pd.DataFrame,
    pat: DetectedPattern,
    *,
    breakout_idx: Optional[int],
    vol_dryup_ratio_max: Optional[float] = None,
    vol_expansion_mult_min: Optional[float] = None,
    vol_expansion_z_min: Optional[float] = None,
    vol_ma_len: int = 20,
    adx_len: int = 14,
    adx_min: Optional[float] = None,
    ma_len: int = 50,
    ma_slope_min: float = 0.0,
    price_col: str = "close",
) -> bool:
    """
    A lightweight composite gate you can call from the backtest before entering:
      - volume dry-up over consolidation vs pole
      - volume expansion on breakout (if breakout_idx is provided)
      - ADX trend strength at consolidation end
      - MA slope (directional) at consolidation end
    Each sub-filter is optional (pass None to disable).
    """
    j1 = pat.cons.j1

    if not passes_volume_dryup(df, pat, vol_dryup_ratio_max):
        return False

    if breakout_idx is not None:
        if not passes_volume_breakout(
            df,
            breakout_idx,
            mult_min=vol_expansion_mult_min,
            z_min=vol_expansion_z_min,
            ma_len=vol_ma_len,
        ):
            return False

    if not adx_trend_ok(df, j1, adx_len=adx_len, adx_min=adx_min):
        return False

    if not ma_slope_ok(
        df,
        j1,
        ma_len=ma_len,
        slope_min=ma_slope_min,
        price_col=price_col,
        normalize_by_price=True,
    ):
        return False

    return True
