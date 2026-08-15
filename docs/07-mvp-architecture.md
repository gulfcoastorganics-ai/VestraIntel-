# MVP architecture

## Goal

Turn fragmented public records into a normalized, ranked queue of lawful business opportunities without automating regulated claims or outreach.

## Pipeline

1. **Source registry** — records the official custodian, access method, legal/compliance gate, and implementation status.
2. **Adapters** — fetch only public/authorized sources. Credentials are read from environment variables. CAPTCHA/authentication barriers are never bypassed.
3. **Normalizer** — converts source-specific records into the common `Opportunity` schema.
4. **Scoring** — ranks freshness, value (when known), asset class, legal clarity, and urgency. The score is a triage heuristic, not a legal conclusion or valuation.
5. **SQLite store** — deduplicated by `(source_id, external_id)`.
6. **Human review** — verifies entitlement/ownership, source accuracy, local law, economics, and contact rules before any action.
7. **Export/API/dashboard** — exposes the reviewed discovery queue to operators or downstream research tooling.

## Implemented source paths

- UK Bona Vacantia unclaimed-estates CSV.
- USPTO Official Gazette: license/sale notices and maintenance-fee expiration signals.
- Federal Laboratory Consortium notice-of-intent-to-license index.
- Companies House read-only company-profile enrichment (API key required).
- USAspending read-only award-search query client.

## Gated paths intentionally not automated

- State locator files where registration or agreements are required (e.g. New York).
- Bankruptcy court claimant interfaces that present CAPTCHA or court-specific procedures.
- MLC bulk/API programs until Data Access Hub enrollment.
- Any claimant tracing, heir investigation, assignment execution, legal filing, or submission of identity evidence.
