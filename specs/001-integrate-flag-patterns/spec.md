# Feature Specification: Flag Patterns Strategy Integration

**Feature Branch**: `001-integrate-flag-patterns`  
**Created**: 2025-10-12  
**Status**: Draft  
**Input**: User description: "Integrate the Flag Patterns (trendline-based) strategy from TechnicalAnalysisAutomation into GoldenEggBot. Ensure the strategy is packaged as a dedicated module under src/strategies/flag_patterns with the four mandatory validation runners (excellence, permute, walk-forward, walk-forward-permute) wrapping mcpt permutation & walk-forward tooling."

## Product Definition *(mandatory)*
Deliver a production-ready Flag Patterns trading strategy module that plugs into GoldenEggBot’s modular architecture, leverages reusable open-source research assets, and satisfies the constitution’s validation, telemetry, and risk requirements. The feature enables the team to operationalize an existing profitable research strategy with deterministic backtesting, live controls, and auditable artifacts.

### Purpose
- Unlock a reusable strategy implementation that showcases GoldenEggBot’s modular strategy pipeline.
- Provide deterministic validation (Excellence, Permutation, Walk-Forward, Walk-Forward Permutation) to build confidence before risking capital.
- Offer live/paper trading capability via existing exchange adapters and shared telemetry surfaces.

### Scope Boundaries
- **In Scope**: Strategy module under `src/strategies/flag_patterns`, wrapper helpers around TechnicalAnalysisAutomation (TAA) utilities, seeded validation runners integrating mcpt tooling, CLI bindings (`geb backtest`, `geb live`), telemetry notifications with visual context, documentation and artifacts.
- **Out of Scope**: Creation of new exchange adapters, changes to Donchian strategy, portfolio allocation logic, or production deployment of Aster DEX adapter (remains flagged for later milestones).

### Actors
- **Researcher**: Runs the four validation scripts with deterministic seeds, inspects artifacts, and reviews performance metrics.
- **Trader**: Launches paper or live sessions using the Flag Patterns module, monitors telemetry, and enforces risk controls via CLI/Telegram.
- **Contributor**: Extends strategy helpers, updates parameters, or adds new visualization hooks without breaking ABC contracts.

Assumptions & Dependencies:
- TechnicalAnalysisAutomation (TAA) and mcpt repositories remain accessible and license-compatible for reuse.
- Exchange adapters (Binance, Hyperliquid, virtual simulator) already exist and expose the shared contract defined in the constitution.
- Market data feeds (exchange klines, CSV backtest datasets) are available and version-controlled.

### Upstream Assets *(reference when applicable)*
- Flag Patterns (TechnicalAnalysisAutomation): https://github.com/neurotrader888/TechnicalAnalysisAutomation — source for trendline detection, flag pattern enumeration, and related helpers.
- mcpt permutation & walk-forward tooling: https://github.com/neurotrader888/mcpt — reused for permutation tests, walk-forward slicing, and statistical evaluation.
- Additional repositories/data sources: GoldenEggBot sample datasets (CSV), exchange REST/WebSocket endpoints surfaced via existing adapters.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Researcher Validates Strategy (Priority: P1)
A researcher selects the Flag Patterns module and runs each of the four validation scripts (`flag_patterns_is_excellence.py`, `flag_patterns_is_permute.py`, `flag_patterns_wf_test.py`, `flag_patterns_wf_permute.py`) with a controlled seed. The scripts fetch historical price data, invoke TAA helpers to produce signals, wrap mcpt routines for permutation statistics, and drop artifacts (metrics CSV/JSON, plots) under `artifacts/flag_patterns/<timestamp>`.

**Why this priority**: Without deterministic evidence the strategy meets performance criteria, the bot must not graduate to live trading. Validation is therefore the primary acceptance gate.

**Independent Test**: Run each script separately with provided CLI options (`--seed`, `--data-path`), verify the artifacts contain expected summaries, and ensure permutation p-values meet configured thresholds.

**Acceptance Scenarios**:

1. **Given** seeded historical data and the researcher invokes `python src/strategies/flag_patterns/tests/flag_patterns_is_excellence.py --seed 42`, **When** the script executes, **Then** it logs the run, persists metrics/visuals under `artifacts/flag_patterns/seed-42/excellence`, and reports success/failure criteria meeting configured thresholds.
2. **Given** the researcher runs the permutation harness with `--seed 42`, **When** mcpt permutation routines complete, **Then** the resulting CSV shows p-value ≤ configured cutoff, and the script exits non-zero if the threshold is missed.

---

### User Story 2 - Trader Operates Live Session (Priority: P2)
A trader launches `geb live --strategy flag_patterns --exchange binance --symbol BTC/USDT --timeframe 1h --seed 42`, reviews pre-trade signal notifications in Telegram (including chart snapshot highlighting the identified flag), monitors PnL and open positions, and can halt trading with `/stop` or `/close_all`.

**Why this priority**: After validation, live/paper trading delivers production utility; telemetry parity keeps operators informed and mitigates risk.

**Independent Test**: Spin up the virtual exchange in dry-run mode, run the live command for a bounded session, confirm CLI and Telegram surfaces stay in sync, risk guardrails fire, and notifications include visuals derived from TAA helpers.

**Acceptance Scenarios**:

1. **Given** the trader starts a paper session, **When** the strategy generates a breakout signal, **Then** Telegram posts an alert with snapshot + recommended trade parameters while CLI dashboard mirrors current exposure and risk status.
2. **Given** cumulative losses reach the configured daily cap, **When** RiskManager invokes the circuit breaker, **Then** the session halts, outstanding orders cancel, and both CLI/Telegram acknowledge the shutdown.

---

### User Story 3 - Contributor Extends Platform (Priority: P3)
A contributor tweaks strategy parameters (e.g., min flag length, breakout confirmation) by editing `params.yaml`, updates the module to expose new visualization metadata, and verifies all validation scripts still pass without modifying exchange adapters or shared infrastructure.

**Why this priority**: The feature must remain extensible for future improvements or alternative pattern definitions while preserving architecture contracts.

**Independent Test**: Modify a parameter, rerun validation scripts with seeds, and ensure the module still adheres to ABC interfaces and strategy tests.

**Acceptance Scenarios**:

1. **Given** the contributor adds a new optional parameter, **When** they rerun `mypy --strict` and the strategy tests, **Then** no type or runtime regressions occur and generated artifacts reflect the parameter change.
2. **Given** telemetry visual hooks are extended, **When** the contributor triggers a simulated signal, **Then** CLI/Telegram both render the new metadata without manual changes in other subsystems.

---

Add more user stories as needed, each with an assigned priority.

### Edge Cases
- Historical data missing candles or contains gaps: strategy should detect discontinuities, log warnings, and fail the validation script rather than produce misleading metrics.
- TAA repository unavailable at runtime: module should surface a descriptive error and skip execution, prompting contributor to vendor or restore the dependency.
- Telegram rate limits or media upload failures: notifications should fall back to text-only summaries and log the failure for operator awareness.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-Strategy**: Implement `FlagPatternsStrategy` extending `StrategyBase` with methods `generate_signal`, `optimize_parameters`, and `warmup_bars`, sourcing detection logic from TAA modules while maintaining exchange neutrality.
- **FR-Validation**: Provide four deterministic runners (`flag_patterns_is_excellence.py`, `flag_patterns_is_permute.py`, `flag_patterns_wf_test.py`, `flag_patterns_wf_permute.py`) that accept `--seed`, `--data-path`, `--artifacts-dir`, delegate to mcpt functions, and persist CSV/JSON/PNG artifacts under `artifacts/flag_patterns/`.
- **FR-Risk**: Define strategy-specific risk parameters (per-trade risk %, max concurrent positions, stop-loss heuristics) consumable by `RiskManager`; ensure live promotion remains gated by permutation p-value thresholds and walk-forward profitability.
- **FR-Telemetry**: Expose consistent CLI and Telegram commands (`/status`, `/positions`, `/pnl`, `/strategy_config`, `/stop`, `/close_all`) with notifications including chart snapshots highlighting entry and breakout zones produced by TAA; command handlers remain idempotent.
- **FR-Portfolio**: Surface the strategy’s exposure within portfolio dashboards, showing USD-valued balances, isolated/cross margin usage, and drawdown stats derived from risk manager outputs.
- **FR-Data Integrity**: Log all data transformations (smoothing, resampling) with provenance metadata, version backtest datasets, quarantine suspect feeds, and attach transformation logs to validation artifacts.
- **FR-Compliance**: Retain structured logs (JSON with correlation IDs) for orders, signals, and risk events; ensure audit trail meets constitution requirements.

### Key Entities *(include if feature involves data)*

- **FlagPatternsConfig**: Parameters controlling trendline tolerances, breakout confirmation, ATR multipliers; sourced from `params.yaml` and validated via Pydantic.
- **FlagSignal**: Structured output containing signal type, entry price, stop/target levels, confidence score, provenance (seed, dataset), and visualization metadata.
- **StrategyArtifact**: Metadata describing validation run (run id, seed, dataset hash, metric summary, artifact paths).
- **RiskPolicy**: Strategy-specific risk caps (daily loss limit, per-position size, max concurrent trades) consumed by RiskManager.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-Validation**: All four validation scripts complete with matching metrics across repeated seeded runs (variance ≤ 0.1% for key KPIs) and permutation p-value ≤ 0.05 before live enablement.
- **SC-Risk**: Live or paper sessions automatically halt within 2 seconds of breaching the configured daily loss cap, cancelling open orders and notifying operators.
- **SC-Latency**: Median latency from signal generation to order submission (excluding exchange response time) ≤ 250 ms during paper-trading benchmarks.
- **SC-Telemetry**: 100% of orders, fills, stop/target events, and risk halts emit Telegram + CLI updates, each including strategy visualization or a logged reason if media upload fails.
- **SC-Portfolio**: Portfolio dashboard reflects Flag Patterns positions with <1% deviation from exchange balances during benchmarking sessions and refresh latency ≤ 5 seconds.
- **SC-Quality Gates**: CI pipelines run lint, mypy `--strict`, unit/integration suites, and the four validation scripts on sample data; builds fail without uploaded artifacts and summarized results.
