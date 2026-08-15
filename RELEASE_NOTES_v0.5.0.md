# Forgotten Asset Intelligence v0.5.0

Released: 2026-08-14

## Added

- Explainable anomaly/discrepancy detector (`fia/anomalies.py`).
- Persistent anomaly findings with provenance, confidence, severity, commercial/actionability scores, blocks, next actions, and analyst state.
- Eight initial rules:
  - dissolved company + unclaimed asset
  - dissolved company + independent IP signal
  - bankruptcy successor-entitlement candidate
  - royalty metadata reconciliation mismatch
  - lapsed patent + live technology/commercial signal
  - high-value three-plus-source entity
  - high-value record with unresolved identity
  - material change to a high-value source record
- CLI:
  - `fia detect`
  - `fia anomaly-rules`
  - `fia anomalies`
  - `fia anomaly <id>`
  - `fia anomaly-state <id> <state>`
  - `fia pipeline`
- API:
  - `GET /api/anomaly-rules`
  - `GET /api/anomalies`
  - `GET /api/anomalies/{id}`
- U.S. Bankruptcy Unclaimed Funds source registration as a manual/CAPTCHA-gated source.
- Analyst decisions (`confirmed` / `dismissed`) survive later detector runs; disappeared findings become `stale`.

## Safety and compliance behavior

- Correlations never establish ownership or entitlement.
- Every anomaly carries a `human_review_required` block.
- Claimant outreach, filings, assignments, purchases, and royalty claims remain outside autonomous execution.
- Patent-expiration anomalies always require a current status/reinstatement and patent-family review.
- SoundExchange/MLC correlations are treated as metadata-reconciliation intelligence, not third-party royalty claims.
- CAPTCHA-gated judiciary sources are not automatically scraped.

## Validation

- 21 unit tests passed.
- Python compilation passed.
- CLI/API smoke checks passed.
