# Forgotten Asset Intelligence v0.4.0

Released: 2026-08-14

## Added

- Commercial opportunity inference engine.
- Separate commercial and actionability scores.
- Source-specific locator fee ceilings for currently verified California and New York workflows.
- Hard compliance/precondition blocks and machine-readable next actions.
- Entity-level commercial summaries with multi-currency value/fee aggregation.
- Companies House previous-name graph evidence.
- Companies House registered-office graph evidence without identity auto-merge.
- CLI commands: `infer`, `commercial`, `entity-commercial`, `case`.
- API endpoints under `/api/commercial`.
- Dashboard commercial/actionability columns.

## Guardrails

- No score establishes ownership or entitlement.
- No automated outreach, filing, assignment, purchase, or claimant representation.
- Fuzzy person matching remains disabled.
- Shared address evidence never creates an automatic organization merge.
- Monetary fee ceilings are legal maximum calculations, not expected revenue.
