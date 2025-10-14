# entries, stops, targets, trailing, expiry

from __future__ import annotations

from typing import Literal, Optional

import numpy as np
import pandas as pd

from .config import Config
from .detector import DetectedPattern, BoundaryLine

Direction = Literal["bull", "bear"]


# ---------- Stops, Targets, Slippage, Returns ----------

def compute_stop_at_entry(
    df: pd.DataFrame,
    atr: pd.Series,
    pat: DetectedPattern,
    entry_idx: int,
    cfg: Config,
) -> float:
    """
    Stop placed beyond the opposite boundary at entry, plus ATR offset.
    """
    opp = pat.lower if pat.pole.direction == "bull" else pat.upper
    boundary_px = boundary_value_at(opp, entry_idx)
    offset = cfg.stop_offset_atr * float(atr.iat[entry_idx])
    if pat.pole.direction == "bull":
        return boundary_px - offset
    else:
        return boundary_px + offset


def compute_target_at_entry(
    pat: DetectedPattern,
    entry_price: float,
    cfg: Config,
    *,
    atr: Optional[pd.Series] = None,
    entry_idx: Optional[int] = None,
) -> float:
    """Return target anchored at entry based on config selection."""
    if cfg.target_type == "measured_move":
        mm = cfg.measured_move_factor * pat.pole.height
        return entry_price + mm if pat.pole.direction == "bull" else entry_price - mm
    if cfg.target_type == "atr_multiple":
        if atr is None or entry_idx is None:
            raise ValueError("ATR target requires atr Series and entry_idx.")
        k = float(cfg.atr_target_k or 2.0)
        a = float(atr.iat[entry_idx])
        if not np.isfinite(a) or a <= 0.0:
            a = 1e-8
        delta = k * a
        return entry_price + delta if pat.pole.direction == "bull" else entry_price - delta
    raise ValueError(f"Unknown target_type: {cfg.target_type}")


def apply_entry_slippage(price: float, direction: Direction, slippage_bps: int) -> float:
    slip = slippage_bps / 10_000.0
    return price * (1.0 + slip) if direction == "bull" else price * (1.0 - slip)


def apply_exit_slippage(price: float, direction: Direction, slippage_bps: int) -> float:
    slip = slippage_bps / 10_000.0
    return price * (1.0 - slip) if direction == "bull" else price * (1.0 + slip)


def compute_net_return(entry_price: float, exit_price: float, direction: Direction, commission_bps: int) -> float:
    """
    Return per-unit net of commissions (per side).
    Slippage should be already baked into adjusted prices.
    """
    gross = (exit_price / entry_price - 1.0) if direction == "bull" else (entry_price / exit_price - 1.0)
    fees = 2.0 * (commission_bps / 10_000.0)
    return gross - fees


# ---------- Small helpers ----------

def boundary_value_at(ln: BoundaryLine, x: int) -> float:
    return ln.slope * x + ln.intercept
