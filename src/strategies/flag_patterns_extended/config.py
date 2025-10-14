# dataclass + loader (YAML/JSON) to surface these to every module (detector, breakout, execution, filters)
# the existing test/driver should pass a Config object or a dict to the new harness

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional, Literal, Dict, Any


PoleMethod = Literal["atr_normalized", "slope_zscore", "quantile"]
PivotMethod = Literal["PIP", "DirectionalChange"]
EntryType = Literal["close", "next_open"]
TargetType = Literal["measured_move", "atr_multiple"]
BoundaryFitMode = Literal["bars", "pivots"]
PivotPrice = Literal["close", "hl2", "ohlc4"]


@dataclass
class Config:
    # ---- Pole (ATR-normalized default) ----
    pole_method: PoleMethod = "atr_normalized"
    pole_lookback_k: int = 5
    atr_len: int = 14
    pole_score_min: float = 3.0  # ATR-multiple (N)

    # ---- Consolidation ----
    min_consolidation_bars: int = 5
    max_consolidation_bars: int = 16
    max_retrace_ratio: float = 0.40  # <= 0.33–0.50 typical
    median_close_above: Optional[float] = None  # fraction of pole height

    # ---- Flags (parallel) ----
    parallel_angle_max_deg: float = 8.0        # |θ_u − θ_l|
    channel_slope_cap_deg: float = 12.0        # |θ_channel|
    min_touches_per_line: int = 2
    channel_gentle_deg: float = 5.0            # accept either direction if slope is gentle
    touch_tol_frac_of_width: float = 0.10      # touch tolerance as fraction of median width

    # ---- Pennants (converging) ----
    width_shrink_ratio_max: float = 0.60       # end/start ≤ r
    apex_pos_factor_max: float = 2.0           # ≤ X× consolidation length (to the right)
    pennant_require_slope_opposition: bool = True

    # ---- Breakout & execution ----
    breakout_requires_close: bool = True
    breakout_buffer_atr: float = 0.05
    max_wait_bars_after_consolidation: int = 5
    entry_type: EntryType = "next_open"
    stop_offset_atr: float = 0.25
    target_type: TargetType = "measured_move"
    measured_move_factor: float = 1.0
    atr_target_k: float = 2.0  # if target_type == "atr_multiple"

    # ---- Pivots (structure resolution) ----
    pivot_method: PivotMethod = "PIP"
    pip_order: int = 8
    dc_epsilon_atr_mult: Optional[float] = None  # ex: 0.3 * ATR

    # ---- Filters (optional; keep in evaluation layer) ----
    vol_dryup_ratio_max: Optional[float] = 0.80
    vol_expansion_mult_min: Optional[float] = 1.60
    vol_ma_len: int = 20
    adx_len: int = 14
    adx_min: Optional[float] = 25.0
    ma_len: int = 50
    ma_slope_min: float = 0.0

    # ---- Backtest hygiene ----
    slippage_bps: int = 2
    commission_bps: int = 0
    event_purge_bars: int = 20
    embargo_bars: int = 10

    # ---- Misc ----
    dedup_distance_bars: int = 5  # de-duplicate nearby detections

    # ---- Boundary fitting (where "order" bites) ----
    boundary_fit_mode: BoundaryFitMode = "pivots"
    pivot_price_for_fit: PivotPrice = "hl2"
    min_pivot_points_per_line: int = 2

    # ---- Filters A/B switch ----
    enable_filters: bool = False

    # -------- Helpers --------
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Config":
        return cls(**d)

    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        # Lazy import to avoid hard dependency if you prefer JSON
        import yaml  # type: ignore
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data)

    def validate(self) -> None:
        assert self.min_consolidation_bars >= 1
        assert self.max_consolidation_bars >= self.min_consolidation_bars
        assert 0.0 < self.max_retrace_ratio <= 1.0
        assert self.pole_lookback_k >= 2
        assert self.atr_len >= 2
        if self.pivot_method == "PIP":
            assert self.pip_order >= 2
        if self.target_type == "atr_multiple":
            assert self.atr_target_k > 0.0
        assert self.min_pivot_points_per_line >= 1
