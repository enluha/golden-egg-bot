---
description: "Task list template for feature implementation"
---

# Tasks: [FEATURE NAME]

**Input**: Design documents from `/specs/[###-feature-name]/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Strategy features MUST include the four deterministic runners (excellence, permute, wf, wf_permute) plus seeded artifact verification. Other tests are optional unless the plan/spec require them.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions
- **Core services**: `src/core/` (config, data, risk)
- **Exchange adapters**: `src/exchanges/`
- **Strategies**: `src/strategies/<strategy_slug>/`
- **Telemetry**: `src/telemetry/` (CLI + Telegram)
- **CLI entrypoints**: `src/cli/`
- **Artifacts**: `artifacts/` (outputs should be git-ignored)
- **Tests**: `tests/` mirrors src modules plus strategy runners

<!-- 
  ============================================================================
  IMPORTANT: The tasks below are SAMPLE TASKS for illustration purposes only.
  
  The /speckit.tasks command MUST replace these with actual tasks based on:
  - User stories from spec.md (with their priorities P1, P2, P3...)
  - Feature requirements from plan.md
  - Entities from data-model.md
  - Endpoints from contracts/
  
  Tasks MUST be organized by user story so each story can be:
  - Implemented independently
  - Tested independently
  - Delivered as an MVP increment
  
  DO NOT keep these sample tasks in the generated tasks.md file.
  ============================================================================
-->

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [ ] T001 Ensure uv environment, Poetry/uv lockfiles, and Docker targets match plan.md
- [ ] T002 Sync linting/typing tooling (ruff, black, mypy `--strict`, Pydantic config validation)
- [ ] T003 [P] Update Makefile/justfile commands for new workflows

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

Examples of foundational tasks (adjust based on your project):

- [ ] T004 Define/update ABC contracts (`ExchangeBase`, `StrategyBase`, `DataSourceBase`, `RiskManagerBase`)
- [ ] T005 [P] Extend risk policies and guardrails in `src/core/risk_manager.py`
- [ ] T006 [P] Refresh telemetry scaffolding (structured logging, SQLite persistence, notification pipelines)
- [ ] T007 Harden data integrity pipelines (validation, provenance logging, quarantine handling)
- [ ] T008 Update configuration schemas and secrets handling per `.env` + keyring policy
- [ ] T009 Confirm CI hooks run required validation runners with seeded artifacts

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - [Title] (Priority: P1) 🎯 MVP

**Goal**: [Brief description of what this story delivers]

**Independent Test**: [How to verify this story works on its own]

### Tests for User Story 1 (Constitution-mandated) ⚠️

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T010 [P] [US1] Excellence runner in `tests/strategies/<slug>_is_excellence.py` produces deterministic artifacts
- [ ] T011 [P] [US1] Permutation runner in `tests/strategies/<slug>_is_permute.py` validates mcpt thresholds
- [ ] T012 [P] [US1] Walk-forward runner in `tests/strategies/<slug>_wf_test.py`
- [ ] T013 [P] [US1] Walk-forward permutation runner in `tests/strategies/<slug>_wf_permute.py`
- [ ] T014 [US1] Verify artifacts stored under `artifacts/<slug>/` with seed metadata

### Implementation for User Story 1

- [ ] T015 [P] [US1] Implement StrategyBase subclass in `src/strategies/<slug>/strategy.py`
- [ ] T016 [P] [US1] Provide default parameters in `src/strategies/<slug>/params.yaml`
- [ ] T017 [US1] Wire strategy into backtest CLI command (no exchange coupling)
- [ ] T018 [US1] Capture artifacts + summary and attach to docs/README updates
- [ ] T019 [US1] Update strategy README with parameters, assumptions, risk controls

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - [Title] (Priority: P2)

**Goal**: [Brief description of what this story delivers]

**Independent Test**: [How to verify this story works on its own]

### Tests for User Story 2

- [ ] T020 [P] [US2] Backtest CLI regression suite for live runner safeguards
- [ ] T021 [US2] Simulated exchange failsafe test (circuit breaker triggers, no orphaned orders)

### Implementation for User Story 2

- [ ] T022 [P] [US2] Extend exchange adapter in `src/exchanges/<adapter>.py`
- [ ] T023 [US2] Update `src/core/risk_manager.py` with strategy-specific caps and alerts
- [ ] T024 [US2] Enhance telemetry broadcasting in `src/telemetry/telegram_bot.py`
- [ ] T025 [US2] Ensure CLI parity in `src/telemetry/cli_dashboard.py`
- [ ] T026 [US2] Log portfolio snapshots + market data in SQLite

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - [Title] (Priority: P3)

**Goal**: [Brief description of what this story delivers]

**Independent Test**: [How to verify this story works on its own]

### Tests for User Story 3

- [ ] T027 [P] [US3] Contract tests verifying new adapter/strategy honors ABC interfaces
- [ ] T028 [US3] Static analysis (mypy/ruff) coverage for new modules

### Implementation for User Story 3

- [ ] T029 [P] [US3] Scaffold adapter folder with README + contract compliance checklist
- [ ] T030 [US3] Document integration steps in `/docs/` or strategy README
- [ ] T031 [US3] Add CI job updates to run new strategy/adapter tests

**Checkpoint**: All user stories should now be independently functional

---

[Add more user story phases as needed, following the same pattern]

---

## Phase N: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] TXXX [P] Documentation updates in docs/ and strategy READMEs
- [ ] TXXX Code cleanup and refactoring with focus on separation of concerns
- [ ] TXXX Performance optimization (latency targets, resource usage)
- [ ] TXXX [P] Additional unit/integration tests as required
- [ ] TXXX Security & compliance hardening (secrets, audit logs)
- [ ] TXXX Validate quickstart flows (backtest, paper, live)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - May integrate with US1 but should be independently testable
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - May integrate with US1/US2 but should be independently testable

### Within Each User Story

- Tests (if included) MUST be written and FAIL before implementation
- Models before services
- Services before endpoints
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes, all user stories can start in parallel (if team capacity allows)
- All tests for a user story marked [P] can run in parallel
- Models within a story marked [P] can run in parallel
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: User Story 1

```bash
# Launch constitution-mandated validation runners in parallel:
Task: "Excellence runner in tests/strategies/<slug>_is_excellence.py"
Task: "Permutation runner in tests/strategies/<slug>_is_permute.py"
Task: "Walk-forward runner in tests/strategies/<slug>_wf_test.py"
Task: "Walk-forward permutation runner in tests/strategies/<slug>_wf_permute.py"

# Launch supporting implementation tasks:
Task: "Implement StrategyBase subclass in src/strategies/<slug>/strategy.py"
Task: "Configure params.yaml defaults in src/strategies/<slug>/params.yaml"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 independently
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo
4. Add User Story 3 → Test independently → Deploy/Demo
5. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1
   - Developer B: User Story 2
   - Developer C: User Story 3
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
