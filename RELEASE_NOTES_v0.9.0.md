# Forgotten Asset Intelligence v0.9.0

## Adaptive case economics

Added a probability/time/cost/regulation-aware economic triage layer on top of v0.8 case resolution.

### New persistence

- `case_economic_states`
- `case_task_economics`

### New commands

```bash
fia economics
fia economic-cases
fia case-economics <anomaly-id>
fia next-economic-lookup <anomaly-id>
```

`fia pipeline` now runs adaptive economics after case resolution.

### New API

- `GET /api/economic-cases`
- `GET /api/economic-cases/{anomaly_id}`
- `GET /api/economic-cases/{anomaly_id}/next-task`

### Value discipline

- Known California locator property values use the verified 10% maximum fee ceiling.
- Known New York locator values can use the verified 15% maximum, but the standard provider file itself omits amounts, so unknown values remain `null`.
- Intelligence-sale values are explicitly analyst planning assumptions.
- Successor/acquisition cases may use an explicit configurable capture-rate assumption for research prioritization only.
- Mixed-currency values are never silently summed or FX-converted.

### Research economics

Each pending lookup receives:

- task blocker-resolution probability heuristic;
- research-cost assumption;
- time discount;
- probability-adjusted incremental value when a valid monetary reference exists;
- economic score; and
- complete rationale/assumptions for auditability.

### Compliance boundary

Economic scoring never establishes entitlement and never clears licensing, owner-agreement, title, chain-of-ownership, court, outreach, purchase, filing, or claimant authorization gates.
