<!-- Sync Impact Report
Version change: 0.0.0 → 1.0.0
Modified principles:
- N/A → I. Mission-Driven Automation
- N/A → II. Modular Architecture Contracts
- N/A → III. Deterministic Strategy Validation
- N/A → IV. Risk & Capital Safeguards
- N/A → V. Telemetry, Control & Observability
Added sections:
- Engineering Workflow & Tooling
- Integrations & Data
- Quality Gates
- Documentation & UX
Removed sections:
- None
Templates requiring updates:
- ⚠ .specify/templates/plan-template.md (populate Constitution Check criteria aligned with v1.0.0 principles)
- ⚠ .specify/templates/spec-template.md (embed new risk/data/telemetry constraints)
- ⚠ .specify/templates/tasks-template.md (ensure task categories cover validation, risk, telemetry duties)
- ⚠ .specify/templates/commands/*.md (verify guidance references GoldenEggBot constitution terminology)
Follow-up TODOs:
- None
-->

# GoldenEggBot Constitution

## Core Principles

### I. Mission-Driven Automation
GoldenEggBot exists to deliver a Python 3.11+ toolkit that supports rigorous research, walk-forward
validation, and live execution across multiple exchanges while exposing identical operational
controls via CLI and Telegram. The architecture must natively wrap the Flag Patterns
(`TechnicalAnalysisAutomation`) and Donchian Breakout (`mcpt`) strategy families while remaining
extensible for future strategy modules and exchange adapters. Every roadmap choice must reinforce
this mission: modular strategy development, reliable live trading, and remote observability.

### II. Modular Architecture Contracts
The repository enforces separation of concerns across core services (data, risk, config), exchange
adapters, strategies, and telemetry surfaces. All cross-component collaboration flows through
abstract base contracts (`ExchangeBase`, `StrategyBase`, `DataSourceBase`, `RiskManagerBase`);
exchange neutrality is non-negotiable and no strategy may reference concrete exchange classes.

### III. Deterministic Strategy Validation
Each strategy lives in its own folder alongside four runnable companions
(`*_is_excellence.py`, `*_is_permute.py`, `*_wf_test.py`, `*_wf_permute.py`) that integrate with
mcpt-style permutation and walk-forward tooling. All validation scripts accept `--seed`, emit
artifacts under `artifacts/`, and guarantee reproducible CSV/JSON/PNG outputs for auditability.

### IV. Risk & Capital Safeguards
Risk management logic centralizes inside `RiskManager`, enforcing hard daily loss limits,
per-position caps, maximum concurrent trades, and circuit breakers on exception spikes. Live
trading is permitted only when strategies demonstrate profitable out-of-sample walk-forward
results, statistically significant permutation p-values, and drawdowns within policy thresholds.

### V. Telemetry, Control & Observability
CLI and Telegram interfaces must expose the same command surface (trade execution, portfolio
state, history, status, log retrieval) and remain available simultaneously so operators can pivot
between them without losing context. Portfolio views present USD-valued account totals (sum across
assets), individual asset balances, open positions, cross and isolated margin metrics, and
configurable portfolio limits (max isolated and cross-margin allocations, portfolio guardrails) in
both UIs. Every order, position change, and risk event emits
structured Telegram notifications with strategy-specific visuals (flag patterns, Donchian channels,
etc.). Command handlers remain idempotent, telemetry pipelines log real and simulated trading
activity plus associated market data to SQLite, and structured JSON logs with correlation IDs
preserve end-to-end traceability.

## Engineering Workflow & Tooling
The stack uses uv-managed environments (with Poetry interoperability as needed), mypy `--strict`,
ruff, black, and Pydantic-backed configuration. The canonical uv binary lives at
`/home/kiluh/.local/bin/uv`, and all package installations run against the repository-managed
virtual environment `venvTrading/` (never the system interpreter). Credentials live in `.env` plus
OS keyring (local files allowed only for development) and are never committed. Makefile/justfile
tasks codify the spec-driven workflow: `/speckit.constitution` → `/speckit.specify` →
`/speckit.plan` → task execution. Dockerized development targets remain maintained to ensure parity
across contributors.

## Integrations & Data
Priority exchange adapters cover the virtual simulator (mirroring Hyperliquid API with live market
data and simulated fees), Binance via CCXT or python-binance, and Hyperliquid via its official SDK.
Aster DEX is tracked as a phase-two adapter; interface scaffolding aligns with
`github.com/asterdex/api-docs`. Data inputs include exchange klines and CSV backtest data compatible
with NeuroTrader repositories. All market data sourcing, validation, and versioning must preserve
data integrity: log every transformation, enforce provenance metadata, and quarantine suspect feeds
immediately.

## Quality Gates
Continuous integration executes unit tests, static checks, and the four per-strategy validation
scripts with representative small-sample windows. Pull requests fail without uploaded artifacts and
a human-readable summary. Live trading promotion requires sign-off on the risk safeguards described
in Principle IV plus a portfolio readiness review covering liquidity and capital reserves.

## Documentation & UX
Each strategy maintains a README detailing parameters, assumptions, and risk controls. The
repository `README.md` includes quickstarts for backtesting, paper trading, and live execution,
alongside instructions for telemetry setup and artifact inspection.

## Governance
This constitution supersedes informal practices. Amendments require a documented proposal, review
against existing principles, and semantic version increments (MAJOR for breaking governance
changes, MINOR for new principles or sections, PATCH for clarifications). Ratified updates must be
propagated into associated templates and surfaced during reviews. All pull requests must confirm
compliance; deviations demand explicit approval and follow-up tasks to reconcile gaps.

**Version**: 1.0.0 | **Ratified**: 2025-10-12 | **Last Amended**: 2025-10-12
