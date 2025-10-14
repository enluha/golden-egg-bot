# breakout detection post-j (+ buffer/close rules)

from __future__ import annotations

from typing import Optional

import pandas as pd

from .config import Config
from .detector import DetectedPattern, BoundaryLine
from .detector import compute_atr  # reuse same ATR impl


def boundary_value_at(ln: BoundaryLine, x: int) -> float:
    """Evaluate y = m*x + b at bar index x."""
    return ln.slope * x + ln.intercept


def find_breakout_index(
    df: pd.DataFrame,
    pat: DetectedPattern,
    cfg: Config,
    atr: Optional[pd.Series] = None,
    *,
    price_col: str = "close",
) -> Optional[int]:
    """
    First bar AFTER j1 that breaks in the pole direction.
    - No lookahead: only checks bars >= j1+1
    - Optional ATR buffer
    - Close-vs-High/Low trigger per config
    - Expires after cfg.max_wait_bars_after_consolidation bars
    """
    j1 = pat.cons.j1
    start = j1 + 1
    end = min(j1 + cfg.max_wait_bars_after_consolidation, len(df) - 1)
    if atr is None:
        atr = compute_atr(df["high"], df["low"], df["close"], cfg.atr_len)

    for t in range(start, end + 1):
        buf = cfg.breakout_buffer_atr * float(atr.iat[t])
        up = boundary_value_at(pat.upper, t)
        lo = boundary_value_at(pat.lower, t)

        hi_t = float(df["high"].iat[t])
        lo_t = float(df["low"].iat[t])
        cl_t = float(df["close"].iat[t])

        if pat.pole.direction == "bull":
            if cfg.breakout_requires_close:
                if cl_t >= up + buf:
                    return t
            else:
                if hi_t >= up + buf:
                    return t
        else:
            if cfg.breakout_requires_close:
                if cl_t <= lo - buf:
                    return t
            else:
                if lo_t <= lo - buf:
                    return t
    return None


def entry_index_from_breakout(
    breakout_idx: int,
    cfg: Config,
    n_bars: int,
) -> Optional[int]:
    """Map breakout bar to entry bar (close vs next_open)."""
    if breakout_idx is None:
        return None
    if cfg.entry_type == "close":
        return breakout_idx
    # next_open
    nxt = breakout_idx + 1
    return nxt if nxt < n_bars else None
