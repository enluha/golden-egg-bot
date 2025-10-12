# Contract – Flag Patterns Telemetry & CLI Parity

## Telegram Bot Commands (existing surface)
- `/status`: Include strategy name, session state, current positions, latest validation run ID.
- `/positions`: List open positions with entry/stop/target per signal, color-coded for PnL.
- `/pnl`: Summary of realized/unrealized gains, drawdown, daily loss cap status.
- `/strategy_config flag_patterns`: Render current parameter values (from Pydantic config) and risk caps.
- `/close_all`: Cancel orders & close positions; must acknowledge with confirmation and triggered reason.
- `/stop`: Halt strategy, trip circuit breaker, log to SQLite.

## Notifications
- **Signal Preview**: Chart snapshot (PNG) overlaying detected flag/pennant, accompanied by textual summary (entry, stop, target, confidence, risk %).
- **Order Lifecycle**: Creation, fill, cancellation events with correlation IDs linking to signals.
- **Risk Events**: Daily loss cap hit, max positions reached; include guidance on recovery (cooldown timer).

## Delivery Requirements
- Notifications emitted to Telegram and CLI dashboard simultaneously.
- Structured log entry (JSON) appended for each notification with fields: `event_type`, `strategy`, `run_id`, `order_id`, `timestamp`, `metadata`.
- Chart generation uses matplotlib Agg backend, stored in `artifacts/flag_patterns/telemetry/` before upload.

## Error Handling
- If Telegram upload fails, fall back to text-only message and log error.
- CLI must display retry hints if snapshot generation fails (e.g., missing font packages).

