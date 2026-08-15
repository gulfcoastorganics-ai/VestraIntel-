# Forgotten Asset Intelligence v1.1.0

## Added
- Source freshness state and refresh-event audit tables.
- Weekly California bulk refresh policy.
- Companies House real-time stream client with persisted resume timepoints.
- FLC, UK estates, and USPTO Official Gazette periodic orchestration.
- Exponential retry/backoff with bounded delays.
- `source-status`, `source-events`, `source-refresh`, and `portfolio-run` CLI commands.
- Read-only `/api/source-sync` and `/api/source-sync/events` endpoints.
- Portfolio execution path combining source refresh with the existing economic research scheduler.

## Boundaries
- Source refresh is dry-run by default.
- Companies House streaming requires a separately registered stream key.
- USPTO ODP remains disabled for autonomous refresh until a product-specific authenticated query is configured.
- No automated claimant outreach, claim submission, asset purchase, CAPTCHA bypass, or entitlement decision.
