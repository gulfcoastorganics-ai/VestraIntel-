# FIA v1.5.0 — Vestra Intel GPT Control Release

## Added

- Authenticated `/agent/*` API designed for GPT Actions.
- Portfolio, opportunities, case, review-ready, source-candidate, and portal-candidate action endpoints.
- Local analysis, official-source discovery, portal discovery, source refresh, bounded research, and portfolio-cycle action endpoints.
- Explicit local review-state endpoints for source candidates, portal candidates, and anomalies.
- Bearer-key protection using `FIA_AGENT_API_KEY`.
- Protection for legacy dashboard/API surfaces whenever the agent key is configured.
- Dynamic public GPT Action schema at `/gpt/openapi.json`.
- Public privacy-policy route at `/privacy`.
- Curated custom-GPT instructions, conversation starters, and four-file knowledge pack.
- Docker deployment configuration and GPT setup documentation.

## Boundaries

The GPT API does not expose claimant outreach, assignments, asset purchases, claims, filings, CAPTCHA bypass, or legal entitlement conclusions. Source refresh and research execution default to preview/dry-run.

## Validation

- 75 tests passed.
- Python compilation passed.
- Agent bearer authentication tested.
- Public Action schema tested.
- Internal API protection tested.
- Local analysis and dry-run research tested.
