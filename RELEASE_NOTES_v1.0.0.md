# Forgotten Asset Intelligence v1.0.0

## Added
- Bounded live research scheduler.
- Dry-run by default; explicit `--execute` required for external calls.
- Economic candidate selection across active cases.
- Per-run planning-cost and step ceilings.
- Conservative Companies House pacing.
- Explicit scheduler stop states.
- Persistent scheduler runs and steps.
- Scheduler CLI and API surfaces.
- Tests covering dry-run, execution, persistence and non-automatable boundaries.

## Safety/compliance boundary
Automatic work remains read-only research. Outreach, contracts, purchases, claims, filings, CAPTCHA bypass, and legal entitlement decisions are out of the automatic scheduler.
