# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]
**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: [e.g., Python 3.11, Swift 5.9, Rust 1.75 or NEEDS CLARIFICATION]  
**Primary Dependencies**: [e.g., FastAPI, UIKit, LLVM or NEEDS CLARIFICATION]  
**Storage**: [if applicable, e.g., SQLite, files or N/A]  
**Testing**: [e.g., pytest, XCTest, cargo test or NEEDS CLARIFICATION]  
**Target Platform**: [e.g., Linux server, iOS 15+, WASM or NEEDS CLARIFICATION]
**Project Type**: [single/web/mobile - determines source structure]  
**Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps or NEEDS CLARIFICATION]  
**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable or NEEDS CLARIFICATION]  
**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens or NEEDS CLARIFICATION]  
**Tooling Baseline**: All dependency management must use `/home/kiluh/.local/bin/uv` targeting the existing `venvTrading/` virtual environment (do not use system pip).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Confirm alignment with the GoldenEggBot Constitution v1.0.0:

- **Mission Fit**: Plan reinforces modular strategy development, live multi-exchange execution, and dual CLI/Telegram control.
- **Architecture Contracts**: All changes respect separation of concerns and use `ExchangeBase`, `StrategyBase`, `DataSourceBase`, `RiskManagerBase`.
- **Strategy Validation**: Strategy folders include the four deterministic runners outputting seeded artifacts under `artifacts/`.
- **Risk & Capital**: RiskManager enforcement updates cover loss caps, concurrency limits, and promotion criteria before live use.
- **Telemetry & Observability**: CLI/Telegram parity, notifications with visuals, SQLite + structured logging, portfolio metrics maintained.
- **Tooling Workflow**: uv-managed env, mypy `--strict`, ruff, black, Pydantic config, Makefile/just tasks, CI artifacts, Docker parity.

Document any gaps plus remediation tasks before proceeding.

## Architecture & Repository Layout

### Documentation Artifacts

```
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan output)
├── research.md          # Phase 0 research findings
├── data-model.md        # Phase 1 entities + schemas
├── quickstart.md        # Phase 1 runbooks
├── contracts/           # Phase 1 interface definitions
└── tasks.md             # Phase 2 execution plan (/speckit.tasks)
```

### Codebase Shape

```
GoldenEggBot/
├── src/
│  ├── core/
│  │  ├── __init__.py
│  │  ├── config.py          # Pydantic settings; loads .env
│  │  ├── data_handler.py    # DataSourceBase + kline fetch/caching
│  │  ├── risk_manager.py    # RiskManagerBase + guards
│  │  ├── types.py           # Signal, OrderRequest, Position, enums
│  │  └── utils.py           # logging, time, retry, seeds
│  ├── telemetry/
│  │  ├── telegram_api.py    # notifier (python-telegram-bot)
│  │  └── bot_controller.py  # command handlers (/status, /stop, etc.)
│  ├── platforms/
│  │  ├── exchange_base.py   # ABC: get_klines, place/cancel, balances
│  │  ├── binance_ccxt.py    # CCXT or python-binance adapter
│  │  ├── hyperliquid_api.py # official SDK wrapper
│  │  └── aster_api.py       # stub adapter (feature-flagged)
│  ├── strategies/
│  │  ├── strategy_base.py   # ABC: init, warmup, generate_signal, optimize
│  │  ├── flag_patterns/
│  │  │  ├── strategy.py
│  │  │  ├── params.yaml
│  │  │  └── tests/
│  │  │     ├── flag_patterns_is_excellence.py
│  │  │     ├── flag_patterns_is_permute.py
│  │  │     ├── flag_patterns_wf_test.py
│  │  │     └── flag_patterns_wf_permute.py
│  │  └── donchian_breakout/
│  │     ├── strategy.py
│  │     ├── params.yaml
│  │     └── tests/
│  │        ├── donchian_is_excellence.py
│  │        ├── donchian_is_permute.py
│  │        ├── donchian_wf_test.py
│  │        └── donchian_wf_permute.py
│  ├── scripts/
│  │  ├── run_live_bot.py     # orchestrates strategy + adapter + telemetry
│  │  └── telegram_runner.py  # optional standalone bot service
│  └── cli/                   # geb CLI entrypoints (backtest/live)
├── tests/
│  ├── unit/
│  └── integration/
├── artifacts/                # deterministic outputs (git-ignored)
├── .env.example
├── requirements.txt / pyproject.toml (uv-managed)
└── README.md
```

**Structure Decision**: [Call out deviations from the default tree, rationale, and links to impacted modules]

## Core Interfaces

Outline the canonical contracts and any planned extensions.

```python
class ExchangeBase(ABC):
    def get_klines(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame: ...
    def place_order(self, req: OrderRequest) -> OrderResult: ...
    def cancel_all(self, symbol: str) -> None: ...
    def get_positions(self) -> list[Position]: ...
    def get_balance(self, asset: str) -> float: ...


class StrategyBase(ABC):
    def generate_signal(self, data: pd.DataFrame) -> Signal: ...
    def optimize_parameters(self, historical: pd.DataFrame) -> dict: ...
    @property
    def warmup_bars(self) -> int: ...


class RiskManagerBase(ABC):
    def apply(self, signal: Signal, state: PortfolioState) -> PositionSizing | Blocked:
        """Enforce daily loss caps, per-trade risk %, max concurrent positions, and circuit breakers."""
```

Document how these map to concrete modules (core, platforms, strategies) and any TODO extensions.

## External Dependencies & Upstream Assets

- **Strategy Sources**: Flag Patterns (TechnicalAnalysisAutomation), Donchian + permutation/walk-forward (mcpt). Define import/submodule approach and wrapper requirements.
- **Exchange Adapters**: Hyperliquid SDK, Binance CCXT/python-binance, Aster DEX (scaffold + validation plan).
- **Telemetry**: python-telegram-bot, event bus helpers.
- **Data & Analysis**: pandas, numpy, scipy, matplotlib, statsmodels (as needed).
- **Supporting Libraries**: pydantic, typer, structlog, tenacity, uv tooling.

List version constraints, licensing considerations, and integration notes.

## Strategy Integration Notes

Detail how built-in strategies reuse upstream code (e.g., wrapping trendline utilities, mcpt runners), deterministic artifact expectations, and hooks for future strategies.

## Telemetry Contract

Summarize notification and command surface:
- Notifications: startup/shutdown, heartbeat, signal previews, order lifecycle, SL/TP, risk halts.
- Commands: `/status`, `/positions`, `/pnl`, `/close_all`, `/strategy_config`, `/stop`.
- Execution: event bus coordination between bot controller and live runner, SQLite + structured logging outputs, visualization assets in Telegram.

## Configuration & Secrets

- `.env` schema (bot token, exchange keys, Hyperliquid wallet, risk policy caps, etc.).
- Keyring usage vs local dev overrides.
- Strategy `params.yaml` overrides and CLI flag mappings.

## CI/CD & Quality Gates

- GitHub Actions matrix: lint (ruff/black), mypy `--strict`, unit/integration tests, strategy 4-pack on sample data, artifact upload, README badges.
- Branch protection / approval requirements.
- Artifact retention policy.

## Milestones & Execution Order

Break delivery into constitutional increments:
1. Scaffold repo + ABCs + CLI bootstrap.
2. Data ingestion + risk manager enforcement.
3. Telemetry surfaces (Telegram + CLI parity).
4. Binance & Hyperliquid adapters (read-only → trading).
5. Donchian strategy pack (wrappers + 4 tests + artifacts).
6. Flag Patterns strategy pack (wrappers + 4 tests + artifacts).
7. End-to-end paper trading with telemetry supervision.
8. Aster DEX adapter (stub → validation → enable).
9. Documentation & examples (notebooks, README quickstarts).

Add acceptance checkpoints, owners, and dependencies per milestone.

## Complexity Tracking

*Fill ONLY if Constitution Check has violations that must be justified*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
