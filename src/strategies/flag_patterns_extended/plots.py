# optional: snapshot charts for QC

# /src/strategies/flag_patterns_extended/plots.py
from __future__ import annotations

from typing import Iterable, List, Optional, Tuple, Dict

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf

from .config import Config
from .detector import DetectedPattern, BoundaryLine, compute_atr
from .breakout import boundary_value_at
from .geometry import intersection_x, band_width_at


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def plot_pattern(
    df: pd.DataFrame,
    pat: DetectedPattern,
    cfg: Config,
    *,
    pad_left: int = 10,
    pad_right: int = 20,
    price_col: str = "close",
    show_breakout_idx: Optional[int] = None,
    show_entry_idx: Optional[int] = None,
    show_exit_idx: Optional[int] = None,
    entry_price: Optional[float] = None,
    stop_price: Optional[float] = None,
    target_price: Optional[float] = None,
    title: Optional[str] = None,
    savepath: Optional[str] = None,
    show: bool = True,
) -> Tuple[plt.Figure, plt.Axes]:
    """
    Draw one detected pattern with pole, consolidation boundaries, (optional) breakout,
    and (optional) trade overlays (entry/stop/target/exit).

    Expects df with columns open, high, low, close (and optional volume).
    The df index should ideally be a DatetimeIndex for mplfinance.
    """
    # --------------- Slice the plotting window ---------------
    start = max(0, pat.pole.i0 - pad_left)
    right_anchor = max(
        x for x in [pat.cons.j1, show_breakout_idx, show_entry_idx, show_exit_idx] if x is not None
    ) if any(x is not None for x in [show_breakout_idx, show_entry_idx, show_exit_idx]) else pat.cons.j1
    end = min(len(df) - 1, right_anchor + pad_right)
    window = df.iloc[start:end + 1].copy()
    idx = window.index

    # --------------- Build alines for pole & consolidation ---------------
    alines = []
    acolors = []

    # Pole line from i0 -> i1 (use close)
    pole = [(idx[pat.pole.i0 - start], float(df[price_col].iat[pat.pole.i0])),
            (idx[pat.pole.i1 - start], float(df[price_col].iat[pat.pole.i1]))]
    alines.append(pole)
    acolors.append('w')

    # Consolidation boundaries from [j0, j1] and an extension to the right
    ext_right = min(end, pat.cons.j1 + pad_right)
    up0 = _line_value(pat.upper, pat.cons.j0)
    up1 = _line_value(pat.upper, ext_right)
    lo0 = _line_value(pat.lower, pat.cons.j0)
    lo1 = _line_value(pat.lower, ext_right)

    upper_line = [(idx[pat.cons.j0 - start], up0), (idx[ext_right - start], up1)]
    lower_line = [(idx[pat.cons.j0 - start], lo0), (idx[ext_right - start], lo1)]
    alines.extend([upper_line, lower_line])
    acolors.extend(['#4da3ff', '#4da3ff'])

    # Optional: vertical markers for i1 and j1
    vlines = [
        (pat.pole.i1, 'y'),
        (pat.cons.j1, '#8888ff'),
    ]

    # --------------- mplfinance setup ---------------
    plt.style.use('dark_background')
    fig = plt.figure(figsize=(12, 6))
    ax = fig.gca()

    mpf.plot(
        window,
        type='candle',
        style='charles',
        ax=ax,
        alines=dict(alines=alines, colors=acolors, linewidths=(1.5, 1.5, 1.5)),
        volume=False,
        datetime_format='%Y-%m-%d %H:%M',
        xrotation=15,
        tight_layout=True,
        warn_too_much_data=10_000,
    )

    # Draw vertical markers
    for bar_idx, color in vlines:
        if start <= bar_idx <= end:
            ax.axvline(idx[bar_idx - start], color=color, alpha=0.5, linestyle='--', linewidth=1)

    # --------------- Breakout threshold overlay (optional) ---------------
    if show_breakout_idx is not None and start <= show_breakout_idx <= end:
        atr = compute_atr(df["high"], df["low"], df["close"], cfg.atr_len)
        buf = cfg.breakout_buffer_atr * float(atr.iat[show_breakout_idx])
        if pat.pole.direction == "bull":
            thr = boundary_value_at(pat.upper, show_breakout_idx) + buf
        else:
            thr = boundary_value_at(pat.lower, show_breakout_idx) - buf
        ax.scatter(idx[show_breakout_idx - start], thr, s=35, marker='^' if pat.pole.direction == "bull" else 'v',
                   color='#ffd166', zorder=5, label='breakout-threshold')
        ax.legend(loc='best', fontsize=8, frameon=False)

    # --------------- Entry / Stop / Target / Exit (optional) ---------------
    if show_entry_idx is not None and entry_price is not None and start <= show_entry_idx <= end:
        ax.scatter(idx[show_entry_idx - start], entry_price, s=40, color='#06d6a0', zorder=10, label='entry')
    if stop_price is not None:
        ax.axhline(stop_price, color='#ef476f', linestyle='--', linewidth=1.2, alpha=0.9, label='stop')
    if target_price is not None:
        ax.axhline(target_price, color='#ffd166', linestyle='--', linewidth=1.2, alpha=0.9, label='target')
    if show_exit_idx is not None and entry_price is not None and start <= show_exit_idx <= end:
        # Approximate exit marker near close
        exit_y = float(df["close"].iat[show_exit_idx]) if target_price is None else target_price
        ax.scatter(idx[show_exit_idx - start], exit_y, s=36, color='#ffa500', zorder=10, label='exit')

    # --------------- Apex marker for pennants (diagnostic) ---------------
    ax = _maybe_draw_apex(ax, pat, start, end, idx)

    # --------------- Title & annotations ---------------
    if title is None:
        title = f"{pat.kind.upper()} • dir={pat.pole.direction} | pole[{pat.pole.i0}->{pat.pole.i1}] cons[{pat.cons.j0}->{pat.cons.j1}]"
    ax.set_title(title, fontsize=11)

    # Diagnostics: width shrink and retrace
    try:
        w0 = band_width_at(pat.upper, pat.lower, pat.cons.j0)
        w1 = band_width_at(pat.upper, pat.lower, pat.cons.j1)
        ax.text(0.01, 0.96, f"width: {w0:.2f}→{w1:.2f} | retrace={pat.cons.retrace_ratio:.2f}",
                transform=ax.transAxes, fontsize=9, color='#d0d0d0', ha='left', va='top')
    except Exception:
        pass

    if savepath:
        fig.savefig(savepath, dpi=140, bbox_inches='tight')
    if show:
        plt.show()
    else:
        plt.close(fig)
    return fig, ax


def plot_trade_from_row(
    df: pd.DataFrame,
    row: pd.Series | Dict,
    cfg: Config,
    *,
    title: Optional[str] = None,
    savepath: Optional[str] = None,
    show: bool = True,
) -> Tuple[plt.Figure, plt.Axes]:
    """
    Convenience: plot from a single backtest row (as returned by run_backtest()).
    Requires that row has the columns written by backtest: i0,i1,j0,j1, kind, direction,
    entry_idx, exit_idx, entry_price, stop_price, target_price, etc.
    """
    # Build a minimal DetectedPattern-like shell for plotting boundaries
    # We stored the necessary geometry features in the trade row columns produced by features.py.
    # However, the actual BoundaryLine slopes/intercepts are not flattened by default,
    # so we re-fit over the consolidation window for accurate rendering.
    j0, j1 = int(row["j0"]), int(row["j1"])
    i0, i1 = int(row["i0"]), int(row["i1"])
    kind = str(row["kind"])
    direction = str(row["direction"])
    # quick OLS refit
    upper, lower = _ols_lines_over_window(df, j0, j1)
    from .detector import PoleStats, ConsolidationStats, DetectedPattern as DetPat  # local import to avoid circulars

    pole_height = abs(float(df["close"].iat[i1]) - float(df["close"].iat[i0]))
    pole = PoleStats(i0=i0, i1=i1, height=pole_height, score=float(row.get("pole_score", np.nan)), direction=direction)  # type: ignore
    cons = ConsolidationStats(j0=j0, j1=j1, retrace_ratio=float(row.get("retrace_ratio", np.nan)),
                              width_start=float(row.get("width_start", np.nan)),
                              width_end=float(row.get("width_end", np.nan)))
    pat = DetPat(kind=kind, pole=pole, cons=cons, upper=upper, lower=lower, apex_x=None, features={})

    return plot_pattern(
        df=df,
        pat=pat,
        cfg=cfg,
        pad_left=10,
        pad_right=20,
        show_breakout_idx=int(row["breakout_idx"]) if _is_int_like(row.get("breakout_idx")) else None,
        show_entry_idx=int(row["entry_idx"]) if _is_int_like(row.get("entry_idx")) else None,
        show_exit_idx=int(row["exit_idx"]) if _is_int_like(row.get("exit_idx")) else None,
        entry_price=float(row["entry_price"]) if _is_float_like(row.get("entry_price")) else None,
        stop_price=float(row["stop_price"]) if _is_float_like(row.get("stop_price")) else None,
        target_price=float(row["target_price"]) if _is_float_like(row.get("target_price")) else None,
        title=title,
        savepath=savepath,
        show=show,
    )


def plot_gallery(
    df: pd.DataFrame,
    rows_df: pd.DataFrame,
    cfg: Config,
    *,
    n: int = 12,
    pad_left: int = 10,
    pad_right: int = 20,
    selection: Optional[pd.Series] = None,
    save_dir: Optional[str] = None,
    show: bool = True,
) -> None:
    """
    Render a gallery of N trades/patterns for rapid visual QC.
    - rows_df is the trades dataframe from run_backtest().
    - selection: optional boolean mask to choose which subset to draw (e.g., wins, losses, filtered).
    - if save_dir provided, saves PNGs with informative filenames; otherwise shows sequentially.
    """
    dfc = rows_df if selection is None else rows_df[selection]
    sample = dfc.sample(min(n, len(dfc)), random_state=42) if len(dfc) > n else dfc

    for _, r in sample.iterrows():
        t = f"{r['kind']}_{r['direction']}_i1{int(r['i1'])}_j1{int(r['j1'])}_reason_{str(r['exit_reason'])}"
        path = f"{save_dir}/{t}.png" if save_dir else None
        plot_trade_from_row(df=df, row=r, cfg=cfg, title=t, savepath=path, show=show)


# -----------------------------------------------------------------------------
# Internals
# -----------------------------------------------------------------------------

def _line_value(line: BoundaryLine, x: int) -> float:
    return boundary_value_at(line, x)


def _maybe_draw_apex(ax: plt.Axes, pat: DetectedPattern, start: int, end: int, idx_window: pd.Index) -> plt.Axes:
    # Draw apex for pennants
    try:
        axp = pat.apex_x if pat.apex_x is not None else intersection_x(pat.upper, pat.lower)
        if axp is not None and start <= int(axp) <= end:
            y = _line_value(pat.upper, int(axp))
            ax.scatter(idx_window[int(axp) - start], y, s=25, marker='x', color='#bbbbbb', zorder=6)
    except Exception:
        pass
    return ax


def _ols_lines_over_window(df: pd.DataFrame, j0: int, j1: int) -> Tuple[BoundaryLine, BoundaryLine]:
    """
    Quick OLS fit of highs/lows to reconstruct boundary lines for plotting when
    only j0, j1 are known (e.g., plotting from a stored trade row).
    """
    x = np.arange(j0, j1 + 1, dtype=float)
    y_hi = df["high"].iloc[j0: j1 + 1].astype(float).to_numpy()
    y_lo = df["low"].iloc[j0: j1 + 1].astype(float).to_numpy()

    s_u, i_u, r2_u = _ols_with_r2(x, y_hi)
    s_l, i_l, r2_l = _ols_with_r2(x, y_lo)

    return (
        BoundaryLine(slope=float(s_u), intercept=float(i_u), r2=float(r2_u), touches=None),
        BoundaryLine(slope=float(s_l), intercept=float(i_l), r2=float(r2_l), touches=None),
    )


def _ols_with_r2(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    X = np.vstack([x, np.ones_like(x)]).T
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    slope, intercept = float(beta[0]), float(beta[1])
    y_hat = slope * x + intercept
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return slope, intercept, r2


def _is_int_like(x: object) -> bool:
    try:
        int(x)
        return True
    except Exception:
        return False


def _is_float_like(x: object) -> bool:
    try:
        float(x)
        return True
    except Exception:
        return False
