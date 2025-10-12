# Feature Specification: [FEATURE NAME]

**Feature Branch**: `[###-feature-name]`  
**Created**: [DATE]  
**Status**: Draft  
**Input**: User description: "$ARGUMENTS"

## Product Definition *(mandatory)*
Summarize the outcome in business language: what we are delivering, why it matters, and how it
reinforces the GoldenEggBot constitution and SPECIFY charter (modular strategies, deterministic
validation, live multi-exchange execution, dual telemetry surfaces).

### Purpose
[Explain the business objective and how it advances automated trading research + live operations.]

### Scope Boundaries
- **In Scope**: [Capabilities included, e.g., new strategy folder, exchange adapter, telemetry flow.]
- **Out of Scope**: [Explicit exclusions to prevent scope creep.]

### Actors
- **Researcher**: validates strategies through the four test harnesses and artifacts.
- **Trader**: runs live/paper sessions with Telegram + CLI parity.
- **Contributor**: extends exchanges/strategies via ABC contracts.

Document assumptions or dependencies that materially affect scope.

### Upstream Assets *(reference when applicable)*
- Flag Patterns (TechnicalAnalysisAutomation): [Link or commit] — leveraged for trendline/flag logic.
- Donchian Breakout (mcpt): [Link or commit] — leveraged for channel calculations and permutation/walk-forward tooling.
- Additional repositories/data sources: [List or mark N/A].

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.
  
  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - Researcher Validates Strategy (Priority: P1)

[Describe how a researcher exercises Excellence, Permutation, Walk-Forward, and Walk-Forward
Permutation scripts using seeded runs and inspects artifacts.]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently - e.g., "Can be fully tested by [specific action] and delivers [specific value]"]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]
2. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

### User Story 2 - Trader Operates Live Session (Priority: P2)

[Describe how a trader launches live/paper trading on supported exchanges, receives Telegram/CLI
controls, and monitors portfolio metrics + risk events.]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

### User Story 3 - Contributor Extends Platform (Priority: P3)

[Describe how a contributor adds an exchange adapter or strategy via ABC contracts without touching
other domains.]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

Add more user stories as needed, each with an assigned priority.

### Edge Cases

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right edge cases.
-->

- What happens when [boundary condition]?
- How does system handle [error scenario]?

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

Group requirements by constitution pillar when possible.

- **FR-Strategy**: [e.g., "Strategy module exposes generate_signal/optimize_parameters/warmup_bars via StrategyBase."]
- **FR-Validation**: [e.g., "Provide Excellence/Permutation/WF/WF Permutation runners producing seeded artifacts in `artifacts/`."]  
- **FR-Risk**: [e.g., "RiskManager enforces daily and per-trade caps, concurrency limits, circuit breaker hooks."]
- **FR-Telemetry**: [e.g., "CLI and Telegram share command surface and broadcast structured notifications with visuals."]
- **FR-Portfolio**: [e.g., "Display USD balances, asset holdings, cross/isolated margins, and configured limits."]
- **FR-Data Integrity**: [e.g., "Version inputs, log transformations, quarantine suspect feeds."]
- **FR-Compliance**: [If applicable, outline logging/audit obligations.]

Use `[NEEDS CLARIFICATION: question]` sparingly (max 3) for requirements that cannot be resolved with
a reasonable default and materially affect scope or compliance.

### Key Entities *(include if feature involves data)*

- **PortfolioSnapshot**: [Attributes for balances, PnL, margins, timestamps.]
- **StrategyArtifact**: [Metadata for deterministic outputs (seed, file paths, validation type).]
- **RiskPolicy**: [Caps, thresholds, escalation contacts.]
- Additional entities as required for the feature.

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-Validation**: [e.g., "All four strategy tests complete with identical metrics/artifacts across seeded runs."]
- **SC-Risk**: [e.g., "Live session halts within N seconds when daily loss cap breached and emits notification."]
- **SC-Latency**: [e.g., "Median signal-to-order submission latency <250ms excluding exchange response."]
- **SC-Telemetry**: [e.g., "100% of orders/fills/risk events trigger CLI + Telegram notifications with visuals."]
- **SC-Portfolio**: [e.g., "Portfolio view refresh latency <= X seconds; accuracy verified against exchange balances."]
- **SC-Quality Gates**: [e.g., "CI publishes artifacts and summary for updated strategies before merge."]
