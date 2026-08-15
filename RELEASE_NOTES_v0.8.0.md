# Forgotten Asset Intelligence v0.8.0

## Added

- recursive case-resolution states and target conditions;
- finite per-case research budgets;
- expected-value-of-information ranking for pending research tasks;
- one recommended next lookup per active case;
- explicit separation between research-resolvable conditions and non-automatable legal gates;
- `fia resolve-cases`, `fia cases`, `fia case-resolution`, and `fia next-lookup`;
- `/api/cases`, `/api/cases/{id}`, and `/api/cases/{id}/next-task`;
- case-resolution unit coverage.

## Safety/compliance boundary

A `review_ready` case is ready for human legal/commercial assessment only. The engine does not establish ownership or entitlement and does not automate claimant outreach, contracts, assignments, purchases, claims, court filings, or royalty collection.
