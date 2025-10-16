# event-driven run over historical bars

from __future__ import annotations
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Literal, Any
import numpy as np
import pandas as pd

from .config import Config
from .detector import (
    detect_patterns,
    DetectedPattern,
    compute_atr,
    BoundaryLine,
)
from .features import build_feature_row, regime_features_at
from .filters import passes_basic_filters
from .execution import update_trailing_stop, last_swing_protective_stop
from .io_ext import archive_trade_bundle


Direction = Literal["bull", "bear"]

# Optional Numba acceleration (falls back to no-op decorator if Numba unavailable)
try:  # pragma: no cover
    import numba as _nb  # type: ignore
    _njit = _nb.njit(cache=True, fastmath=True)
except Exception:  # pragma: no cover
    _nb = None
    def _njit(*dargs, **dkwargs):  # type: ignore
        # Support both bare-decorator (@_njit) and parameterized (@_njit(...)) usage
        if dargs and callable(dargs[0]) and len(dargs) == 1 and not dkwargs:
            # Bare decorator form: @_njit above a function
            return dargs[0]
        def deco(fn):
            return fn
        return deco


@dataclass(frozen=True)
class TradeResult:
    symbol: Optional[str]
    timeframe: Optional[str]
    kind: str                 # "flag" or "pennant"
    direction: Direction      # "bull" or "bear"
    i0: int                   # pole start
    i1: int                   # pole end
    j0: int                   # consolidation start
    j1: int                   # consolidation end
    breakout_idx: Optional[int]
    entry_idx: Optional[int]
    exit_idx: Optional[int]
    entry_price: Optional[float]
    stop_price: Optional[float]
    target_price: Optional[float]
    exit_price: Optional[float]
    exit_reason: Optional[str]  # "target" | "stop" | "timeout" | "no_breakout"
    pnl_pct: Optional[float]     # net of slippage/commission (per unit)
    r_multiple: Optional[float]  # PnL / initial_risk
    hold_bars: Optional[int]
    # Diagnostics / features (flattened)
    features: Dict[str, float]


def run_backtest(
    df: pd.DataFrame,
    cfg: Config,
    *,
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    price_col: str = "close",
    apply_filters: Optional[bool] = None,
) -> pd.DataFrame:
    """
    Event-driven backtest:
      - detect patterns with NO lookahead beyond j1 (delegated to detector)
      - find breakout AFTER j1 within cfg.max_wait_bars_after_consolidation
      - enter per cfg.entry_type (close vs next_open)
      - set stop/target per cfg
      - manage trade forward bar-by-bar
      - apply slippage & commissions from cfg
      - return a DataFrame of trades with flattened features

    Required columns in df: open, high, low, close (volume optional).
    Index can be integer or datetime; we log indices and timestamps if available.
    """
    cfg.validate()
    # Indicators used for breakout buffer & stops
    atr = compute_atr(df["high"], df["low"], df["close"], cfg.atr_len)

    # Detect patterns (scanner guarantees windows end at j1; no lookahead)
    patterns: List[DetectedPattern] = detect_patterns(df=df, cfg=cfg, price_col=price_col)
    use_filters = cfg.enable_filters if apply_filters is None else bool(apply_filters)

    rows: List[Dict[str, Any]] = []
    for pat in patterns:
        row = _simulate_trade_for_pattern(
            df=df,
            atr=atr,
            pat=pat,
            cfg=cfg,
            symbol=symbol,
            timeframe=timeframe,
            price_col=price_col,
            use_filters=use_filters,
        )
        rows.append(row)

    trades_df = pd.DataFrame(rows)
    # Unpack timestamps if df has them
    if not trades_df.empty and isinstance(df.index, (pd.DatetimeIndex, pd.PeriodIndex)):
        def safe_ts(ix: Optional[int]) -> Optional[pd.Timestamp]:
            if ix is None:
                return None
            if 0 <= ix < len(df.index):
                return pd.Timestamp(df.index[ix])
            return None

        trades_df["pole_start_time"] = trades_df["i0"].map(safe_ts)
        trades_df["pole_end_time"] = trades_df["i1"].map(safe_ts)
        trades_df["cons_start_time"] = trades_df["j0"].map(safe_ts)
        trades_df["cons_end_time"] = trades_df["j1"].map(safe_ts)
        trades_df["breakout_time"] = trades_df["breakout_idx"].map(safe_ts)
        trades_df["entry_time"] = trades_df["entry_idx"].map(safe_ts)
        trades_df["exit_time"] = trades_df["exit_idx"].map(safe_ts)

    # Expand flattened features to columns
    if not trades_df.empty:
        feat_df = trades_df["features"].apply(pd.Series)
        trades_df = pd.concat([trades_df.drop(columns=["features"]), feat_df], axis=1)

    archive_dir = getattr(cfg, "archive_dir", None)
    archive_prob = float(getattr(cfg, "archive_prob", 0.0) or 0.0)
    if archive_dir and archive_prob > 0.0 and not trades_df.empty:
        for _, row in trades_df.iterrows():
            entry_idx = row.get("entry_idx")
            if pd.notna(entry_idx) and random.random() <= archive_prob:
                archive_trade_bundle(df, row, cfg, archive_dir, include_plot=True)

    return trades_df


# ---- Internals ---------------------------------------------------------------

def _simulate_trade_for_pattern(
    df: pd.DataFrame,
    atr: pd.Series,
    pat: DetectedPattern,
    cfg: Config,
    *,
    symbol: Optional[str],
    timeframe: Optional[str],
    price_col: str,
    use_filters: bool,
) -> Dict[str, Any]:
    """
    From a single DetectedPattern:
      - find breakout after j1 (within max_wait)
      - compute entry price (close or next_open)
      - compute stop & target
      - walk forward to exit (target, stop, or timeout)
      - price adjustments for slippage/commission at entry & exit
    """
    i0, i1 = pat.pole.i0, pat.pole.i1
    j0, j1 = pat.cons.j0, pat.cons.j1
    direction = pat.pole.direction

    filters_applied_val = 1.0 if use_filters else 0.0

    def _base_features(
        entry_idx_for_target: Optional[int] = None,
        *,
        base: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        if base is not None:
            feat_inner = dict(base)
        else:
            feat_inner = build_feature_row(df, atr, pat)
            regime_inner = regime_features_at(
                df,
                idx=pat.cons.j1,
                r2_window=50,
                rv_window=50,
                vol_ma_short=20,
                vol_ma_long=50,
                swing_window=200,
                pivot_method_for_feature="PIP",
                pip_order_for_feature=8,
            )
            feat_inner.update(regime_inner)
            feat_inner["filters_applied"] = filters_applied_val
        if entry_idx_for_target is not None and 0 <= entry_idx_for_target < len(atr):
            feat_inner["telemetry_target_type"] = 1.0 if cfg.target_type == "atr_multiple" else 0.0
            feat_inner["telemetry_atr_at_entry"] = float(atr.iat[entry_idx_for_target])
        return feat_inner

    base_features = _base_features()

    breakout_idx = _find_breakout_index(df, atr, pat, cfg, price_col=price_col)
    if breakout_idx is None:
        feat = _base_features(base=base_features)
        return _finalize_row(
            symbol, timeframe, pat, breakout_idx=None, entry_idx=None, exit_idx=None,
            entry_price=None, stop_price=None, target_price=None, exit_price=None,
            exit_reason="no_breakout", pnl_pct=None, r_multiple=None, hold_bars=None, features=feat
        )

    # Optional filters before placing the trade entry
    if use_filters:
        passes_filters = passes_basic_filters(
            df,
            pat,
            breakout_idx=breakout_idx,
            vol_dryup_ratio_max=cfg.vol_dryup_ratio_max,
            vol_expansion_mult_min=cfg.vol_expansion_mult_min,
            vol_expansion_z_min=None,
            vol_ma_len=cfg.vol_ma_len,
            adx_len=cfg.adx_len,
            adx_min=cfg.adx_min,
            ma_len=cfg.ma_len,
            ma_slope_min=cfg.ma_slope_min,
            price_col=price_col,
        )
        if not passes_filters:
            feat = _base_features(base=base_features)
            return _finalize_row(
                symbol, timeframe, pat, breakout_idx=breakout_idx, entry_idx=None, exit_idx=None,
                entry_price=None, stop_price=None, target_price=None, exit_price=None,
                exit_reason="filtered_out", pnl_pct=None, r_multiple=None, hold_bars=None, features=feat,
            )

    # scoring gate (optional)
    if getattr(cfg, "enable_scoring", False):
        scorer = getattr(cfg, "scorer", None)
        threshold = float(getattr(cfg, "scoring_threshold", 0.5))
        if scorer is not None:
            try:
                score_val = float(scorer.predict_proba(base_features))
                base_features["score"] = score_val
                if score_val < threshold:
                    feat = _base_features(base=base_features)
                    return _finalize_row(
                        symbol, timeframe, pat, breakout_idx=breakout_idx, entry_idx=None, exit_idx=None,
                        entry_price=None, stop_price=None, target_price=None, exit_price=None,
                        exit_reason="filtered_out", pnl_pct=None, r_multiple=None, hold_bars=None,
                        features=feat,
                    )
            except Exception:
                pass

    # Entry handling
    entry_idx = breakout_idx
    if cfg.entry_type == "next_open":
        entry_idx = breakout_idx + 1
        if entry_idx >= len(df):
            feat = _base_features(base=base_features)
            return _finalize_row(
                symbol, timeframe, pat, breakout_idx=breakout_idx, entry_idx=None, exit_idx=None,
                entry_price=None, stop_price=None, target_price=None, exit_price=None,
                exit_reason="no_breakout", pnl_pct=None, r_multiple=None, hold_bars=None, features=feat
            )

    raw_entry_price = float(df["close"].iat[breakout_idx]) if cfg.entry_type == "close" else float(df["open"].iat[entry_idx])
    entry_price = _apply_entry_slippage(raw_entry_price, direction, cfg.slippage_bps)

    # Stops & targets
    stop_price = _compute_stop_at_entry(df, atr, pat, entry_idx, cfg)
    target_price = _compute_target_at_entry(pat, entry_price, cfg, atr=atr, entry_idx=entry_idx)

    # Risk R for R-multiple
    initial_risk = (entry_price - stop_price) if direction == "bull" else (stop_price - entry_price)
    if initial_risk <= 0:
        feat = _base_features(entry_idx, base=base_features)
        return _finalize_row(
            symbol, timeframe, pat, breakout_idx=breakout_idx, entry_idx=entry_idx, exit_idx=None,
            entry_price=entry_price, stop_price=stop_price, target_price=target_price, exit_price=None,
            exit_reason="no_breakout", pnl_pct=None, r_multiple=None, hold_bars=None, features=feat
        )

    # Walk forward bar-by-bar to find exit
    max_idx = len(df) - 1
    exit_reason: Optional[str] = None
    exit_idx: Optional[int] = None
    exit_price: Optional[float] = None

    trailing_on = bool(getattr(cfg, "enable_trailing", False) or getattr(cfg, "enable_last_swing_stop", False))
    if not trailing_on:
        highs = df["high"].to_numpy(dtype=float)
        lows = df["low"].to_numpy(dtype=float)
        dir_flag = 1 if direction == "bull" else -1

        @_njit
        def _scan_exit(start_i: int, end_i: int, highs: np.ndarray, lows: np.ndarray, stop_p: float, target_p: float, dir_flag: int):
            # returns (idx, code): code 0=stop, 1=target, -1=timeout
            for t in range(start_i, end_i + 1):
                hi = highs[t]
                lo = lows[t]
                if dir_flag == 1:
                    if lo <= stop_p:
                        return t, 0
                    if hi >= target_p:
                        return t, 1
                else:
                    if hi >= stop_p:
                        return t, 0
                    if lo <= target_p:
                        return t, 1
            return -1, -1

        eidx, code = _scan_exit(entry_idx + 1, max_idx, highs, lows, float(stop_price), float(target_price), dir_flag)
        if eidx >= 0:
            exit_idx = int(eidx)
            if code == 0:
                exit_reason = "stop"
                raw_exit = float(stop_price)
            else:
                exit_reason = "target"
                raw_exit = float(target_price)
            exit_price = _apply_exit_slippage(raw_exit, direction, cfg.slippage_bps)
        else:
            exit_idx = max_idx
            exit_reason = "timeout"
            exit_price = _apply_exit_slippage(float(df["close"].iat[exit_idx]), direction, cfg.slippage_bps)
    else:
        # Fallback to original loop when trailing or swing stops are enabled
        for t in range(entry_idx + 1, max_idx + 1):
            hi = float(df["high"].iat[t])
            lo = float(df["low"].iat[t])

            if getattr(cfg, "enable_trailing", False):
                stop_price = update_trailing_stop(df, atr, t, direction, stop_price, cfg)
            if getattr(cfg, "enable_last_swing_stop", False):
                swing_stop = last_swing_protective_stop(df, t, direction, getattr(cfg, "swing_lookback", 10))
                if swing_stop is not None:
                    if direction == "bull":
                        stop_price = max(stop_price, swing_stop)
                    else:
                        stop_price = min(stop_price, swing_stop)

            if direction == "bull":
                if lo <= stop_price:
                    exit_idx, exit_reason, raw_exit = t, "stop", stop_price
                elif hi >= target_price:
                    exit_idx, exit_reason, raw_exit = t, "target", target_price
                else:
                    continue
            else:
                if hi >= stop_price:
                    exit_idx, exit_reason, raw_exit = t, "stop", stop_price
                elif lo <= target_price:
                    exit_idx, exit_reason, raw_exit = t, "target", target_price
                else:
                    continue

            # Apply exit slippage
            exit_price = _apply_exit_slippage(raw_exit, direction, cfg.slippage_bps)
            break

        if exit_idx is None:
            # No exit event — treat as timeout at last available bar
            exit_idx = max_idx
            exit_reason = "timeout"
            exit_price = _apply_exit_slippage(float(df["close"].iat[exit_idx]), direction, cfg.slippage_bps)

    # Compute net P&L (per-unit return), commission per side in bps
    pnl_pct = _compute_net_return(entry_price, exit_price, direction, cfg.commission_bps)

    r_multiple = (exit_price - entry_price) / initial_risk if direction == "bull" else (entry_price - exit_price) / initial_risk
    hold_bars = exit_idx - entry_idx

    feat = _base_features(entry_idx, base=base_features)
    return _finalize_row(
        symbol, timeframe, pat, breakout_idx=breakout_idx, entry_idx=entry_idx, exit_idx=exit_idx,
        entry_price=entry_price, stop_price=stop_price, target_price=target_price, exit_price=exit_price,
        exit_reason=exit_reason, pnl_pct=pnl_pct, r_multiple=r_multiple, hold_bars=hold_bars, features=feat
    )


# ---- Breakout, Stops, Targets ------------------------------------------------

def _boundary_value_at(ln: BoundaryLine, x: int) -> float:
    return ln.slope * x + ln.intercept


def _find_breakout_index(
    df: pd.DataFrame,
    atr: pd.Series,
    pat: DetectedPattern,
    cfg: Config,
    *,
    price_col: str,
) -> Optional[int]:
    """
    First bar AFTER j1 that breaks out of the consolidation boundary
    in the pole direction, with optional ATR buffer and close requirement.
    """
    j1 = pat.cons.j1
    start = j1 + 1
    end = min(j1 + cfg.max_wait_bars_after_consolidation, len(df) - 1)

    if start > end:
        return None

    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    atr_arr = atr.to_numpy(dtype=float)

    us, ui = float(pat.upper.slope), float(pat.upper.intercept)
    ls, li = float(pat.lower.slope), float(pat.lower.intercept)
    buf_m = float(cfg.breakout_buffer_atr)
    dflag = 1 if pat.pole.direction == "bull" else -1
    rclose = 1 if cfg.breakout_requires_close else 0

    @_njit
    def _scan_breakout(start_i: int, end_i: int,
                       highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, atr_arr: np.ndarray,
                       us: float, ui: float, ls: float, li: float,
                       buf_m: float, dflag: int, rclose: int) -> int:
        for t in range(start_i, end_i + 1):
            buf = buf_m * atr_arr[t]
            up = us * t + ui
            lo = ls * t + li
            hi_t = highs[t]
            lo_t = lows[t]
            cl_t = closes[t]
            if dflag == 1:
                thr = up + buf
                if rclose == 1:
                    if cl_t >= thr:
                        return t
                else:
                    if hi_t >= thr:
                        return t
            else:
                thr = lo - buf
                if rclose == 1:
                    if cl_t <= thr:
                        return t
                else:
                    if lo_t <= thr:
                        return t
        return -1

    idx = _scan_breakout(start, end, highs, lows, closes, atr_arr, us, ui, ls, li, buf_m, dflag, rclose)
    return None if idx < 0 else int(idx)


def _compute_stop_at_entry(
    df: pd.DataFrame,
    atr: pd.Series,
    pat: DetectedPattern,
    entry_idx: int,
    cfg: Config,
) -> float:
    """
    Stop set beyond the opposite boundary at ENTRY time, plus ATR offset.
    """
    opp = pat.lower if pat.pole.direction == "bull" else pat.upper
    boundary_px = _boundary_value_at(opp, entry_idx)
    offset = cfg.stop_offset_atr * float(atr.iat[entry_idx])
    if pat.pole.direction == "bull":
        return boundary_px - offset
    else:
        return boundary_px + offset


def _compute_target_at_entry(
    pat: DetectedPattern,
    entry_price: float,
    cfg: Config,
    *,
    atr: pd.Series,
    entry_idx: int,
) -> float:
    if cfg.target_type == "measured_move":
        mm = cfg.measured_move_factor * pat.pole.height
        return entry_price + mm if pat.pole.direction == "bull" else entry_price - mm
    if cfg.target_type == "atr_multiple":
        k = float(cfg.atr_target_k or 2.0)
        atr_val = float(atr.iat[entry_idx])
        if not np.isfinite(atr_val) or atr_val <= 0.0:
            atr_val = 1e-8
        delta = k * atr_val
        return entry_price + delta if pat.pole.direction == "bull" else entry_price - delta
    raise ValueError(f"Unknown target_type: {cfg.target_type}")


# ---- Pricing adjustments & PnL ----------------------------------------------

def _apply_entry_slippage(price: float, direction: Direction, slippage_bps: int) -> float:
    slip = slippage_bps / 10_000.0
    if direction == "bull":
        return price * (1.0 + slip)
    else:
        return price * (1.0 - slip)


def _apply_exit_slippage(price: float, direction: Direction, slippage_bps: int) -> float:
    slip = slippage_bps / 10_000.0
    if direction == "bull":
        return price * (1.0 - slip)
    else:
        return price * (1.0 + slip)


def _compute_net_return(entry_price: float, exit_price: float, direction: Direction, commission_bps: int) -> float:
    """
    Per-unit return net of per-side commissions & slippage already baked into prices.
    """
    gross_ret = (exit_price / entry_price - 1.0) if direction == "bull" else (entry_price / exit_price - 1.0)
    fees = 2.0 * (commission_bps / 10_000.0)  # entry + exit
    return gross_ret - fees


# ---- Row assembly ------------------------------------------------------------

def _finalize_row(
    symbol: Optional[str],
    timeframe: Optional[str],
    pat: DetectedPattern,
    *,
    breakout_idx: Optional[int],
    entry_idx: Optional[int],
    exit_idx: Optional[int],
    entry_price: Optional[float],
    stop_price: Optional[float],
    target_price: Optional[float],
    exit_price: Optional[float],
    exit_reason: Optional[str],
    pnl_pct: Optional[float],
    r_multiple: Optional[float],
    hold_bars: Optional[int],
    features: Dict[str, float],
) -> Dict:
    return dict(
        symbol=symbol,
        timeframe=timeframe,
        kind=pat.kind,
        variant=pat.features.get("variant") if isinstance(pat.features, dict) else None,
        direction=pat.pole.direction,
        i0=pat.pole.i0,
        i1=pat.pole.i1,
        j0=pat.cons.j0,
        j1=pat.cons.j1,
        breakout_idx=breakout_idx,
        entry_idx=entry_idx,
        exit_idx=exit_idx,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        exit_price=exit_price,
        exit_reason=exit_reason,
        pnl_pct=pnl_pct,
        r_multiple=r_multiple,
        hold_bars=hold_bars,
        features=features,
    )
