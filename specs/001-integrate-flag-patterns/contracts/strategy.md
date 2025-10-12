# Contract – FlagPatternsStrategy

## Overview
Defines the interface and expected behavior for `FlagPatternsStrategy`, a concrete implementation of `StrategyBase`.

## Public API

### Class: `FlagPatternsStrategy(StrategyBase)`
- **Constructor** `__init__(self, config: FlagPatternsConfig, data_source: DataSourceBase, risk_manager: RiskManagerBase)`
  - Stores validated config, references to data source and risk manager.
  - Vendors TechnicalAnalysisAutomation helper modules on import.

- **Method** `warmup_bars(self) -> int`
  - Returns maximum lookback required (derived from `config.min_pole_bars` and hold multiplier).

- **Method** `generate_signal(self, market_data: pd.DataFrame) -> Optional[Signal]`
  - Input: DataFrame with OHLC columns at configured timeframe.
  - Behavior:
    1. Convert to numpy log returns as expected by TAA utilities.
    2. Call `find_flags_pennants_pips` or `find_flags_pennants_trendline` based on `config.use_trendline_mode`.
    3. Translate detected pattern into `Signal` with entry/stop/target & metadata.
    4. Return `None` when no actionable pattern is confirmed.

- **Method** `optimize_parameters(self, historical: pd.DataFrame) -> dict`
  - Runs offline calibration (grid search across `order_scan_range`) and returns best-performing configuration summary.
  - Should leverage deterministic seeds for reproducibility.

## Non-Functional Requirements
- Must remain exchange-neutral; never reference concrete exchange implementations.
- Deterministic behavior given identical `market_data` and `seed`.
- Raise descriptive exceptions when upstream modules or datasets are missing.
- Include MIT attribution headers for vendored code segments.

## Dependencies
- TechnicalAnalysisAutomation modules: `flags_pennants`, `trendline_automation`, `perceptually_important`, `rolling_window`.
- mcpt modules only used in validation scripts, not during live signal generation.

## Extension Points
- `FlagPatternsStrategyVisualizer` helper (optional) producing annotated charts for telemetry; must accept `FlagSignal` metadata and produce PNG.
- Config overrides via CLI/params: allow environment or YAML override with validation through Pydantic schema.

