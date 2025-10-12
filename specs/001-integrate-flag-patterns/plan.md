# Implementation Plan: Flag Patterns Strategy Integration

**Branch**: `001-integrate-flag-patterns` | **Date**: 2025-10-12 | **Spec**: specs/001-integrate-flag-patterns/spec.md
**Input**: Feature specification from `/speckit.specify` prompt focusing on TechnicalAnalysisAutomation integration

## Summary

Integrate the TechnicalAnalysisAutomation Flag Patterns (trendline-based) strategy into GoldenEggBot as a first-class module. Reuse upstream code with minimal adaptation, supply deterministic validation runners powered by mcpt permutation & walk-forward tooling, and ensure CLI/Telegram parity, risk controls, and documentation updates required for live-readiness.

## Technical Context

**Language/Version**: Python 3.12.3 via `venvTrading/`
**Primary Dependencies**: pandas, numpy, scipy, matplotlib, statsmodels, pydantic, typer, structlog, tenacity, python-telegram-bot, TechnicalAnalysisAutomation (vendored modules), mcpt (vendored modules)
**Storage**: SQLite (telemetry/logging), artifact files (CSV/JSON/PNG) in `artifacts/`
**Testing**: pytest, strategy runners (`*_is_excellence.py`, `*_is_permute.py`, `*_wf_test.py`, `*_wf_permute.py`), mypy --strict, ruff, black
**Target Platform**: Linux server / WSL (CI + ops)
**Project Type**: Single backend/CLI project
**Performance Goals**: Signal-to-order submission latency <250ms (excluding exchange response), deterministic artifact generation across runs
**Constraints**: Exchange-neutral architecture (ABC contracts), deterministic seeding, CLI/Telegram parity, risk guardrails (daily loss, per-trade caps, concurrency)
**Scale/Scope**: Single strategy module plus supporting validation/telemetry updates
**Tooling Baseline**: Use `/home/kiluh/.local/bin/uv` with `--python venvTrading/bin/python` for all dependency operations (no system pip)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Mission Fit**: Introduces modular strategy with reusable validation and live tooling.
- **Architecture Contracts**: Strategy conforms to `StrategyBase`; exchange neutrality maintained.
- **Strategy Validation**: Four deterministic runners with mcpt permutation & walk-forward tooling producing seeded artifacts.
- **Risk & Capital**: Strategy-specific risk constraints integrated with RiskManager before live trading.
- **Telemetry & Observability**: CLI/Telegram parity with chart snapshots and structured logging.
- **Tooling Workflow**: uv-managed env (`venvTrading`), mypy --strict, ruff, black, Pydantic config, artifacts stored under versioned directories.

No gaps identified; proceed to design.

## Architecture & Repository Layout

### Documentation Artifacts

```
specs/001-integrate-flag-patterns/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
└── tasks.md
```

### Codebase Shape

```
GoldenEggBot/
├── src/
│  ├── core/
│  ├── telemetry/
│  ├── platforms/
│  ├── strategies/
│  │  ├── strategy_base.py
│  │  ├── flag_patterns/
│  │  │  ├── __init__.py
│  │  │  ├── strategy.py
│  │  │  ├── params.yaml
│  │  │  ├── upstream/  # vendored TAA modules (flags_pennants, trendline_automation, etc.)
│  │  │  └── tests/
│  │  │     ├── flag_patterns_is_excellence.py
│  │  │     ├── flag_patterns_is_permute.py
│  │  │     ├── flag_patterns_wf_test.py
│  │  │     └── flag_patterns_wf_permute.py
│  │  └── donchian_breakout/
│  ├── scripts/
│  └── cli/
├── tests/
├── artifacts/
├── .env.example
├── requirements.txt / pyproject.toml
└── README.md
```

**Structure Decision**: Introduce `flag_patterns` module and validation scripts; vendor only necessary upstream files beneath `src/strategies/flag_patterns/upstream/` with attribution.

## Strategy Integration Notes

- Wrap `flags_pennants.find_flags_pennants_pips` & supporting modules inside `FlagPatternsStrategy` to generate GoldenEggBot `Signal` objects.
- Provide adapter functions to load klines from `DataSourceBase`, perform log transformations, and translate results into entries/exits with risk metadata.
- Parameter schema stored in `params.yaml` (min flag length, hold multiplier, breakout confirmations) validated with Pydantic.
- Risk settings (per-trade %, daily cap) surfaced for RiskManager consumption.

## Telemetry Contract

- Telegram/CLI notifications include chart snapshots with detected flag annotations.
- Commands `/status`, `/positions`, `/pnl`, `/strategy_config`, `/close_all`, `/stop` remain mirrored.
- Structured JSON logs capture correlation IDs for signals/orders.

## Configuration & Secrets

- No new secrets; rely on existing `.env` for exchange keys and Telegram bot token.
- Introduce `STRATEGY_FLAG_PATTERNS_ENABLED`, `STRATEGY_FLAG_PATTERNS_RISK_CAPS` parameters in config.

## CI/CD & Quality Gates

- Update CI workflow to execute Flag Patterns validation scripts on sample data (upload artifacts & summary markdown).
- mypy/ruff to include new modules; ensure vendored code adheres or is excluded from lint with rationale.

## Milestones & Execution Order

1. **Research & Preparation** (complete) – upstream licensing, entry points, uv compatibility.
2. **Design & Data Modeling** – define entities, data schemas, contract surfaces, quickstart flows (current stage).
3. **Scaffold Strategy Module** – create `flag_patterns` package, vendor upstream modules, implement StrategyBase subclass.
4. **Validation Harness Integration** – build four deterministic runners using mcpt permutation/walk-forward functions.
5. **Telemetry & Visualization** – implement chart snapshot generation and Telegram delivery.
6. **Risk & Config Wiring** – integrate risk caps, CLI/Telegram controls.
7. **Documentation & Examples** – strategy README and root README updates, sample notebook.
8. **CI Integration & Dry Run** – pipeline updates, artifact verification, paper-trading dry run.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |
