# Unclaimed Asset Recovery Project

Internal launch kit for a lawful asset-recovery / claimant-reconnection business.

## Core thesis

Public agencies, courts, trustees, insolvency offices, and corporations routinely hold money or property for people who do not know it exists or cannot be located. The project does **not** treat discovery as ownership. It creates value by:

1. identifying a public record of an asset or payment;
2. verifying who is legally entitled to it;
3. locating that person or successor using lawful sources;
4. obtaining written authorization or a legally valid assignment/purchase where permitted;
5. helping complete the claim process or referring the matter to a licensed professional; and
6. earning a disclosed recovery fee, purchase spread, referral/technology fee, or resale margin where lawful.

## Non-negotiable rules

- Never file a claim without a documented legal basis for entitlement.
- Never impersonate an owner, heir, creditor, executor, officer, or representative.
- Never fabricate lineage, ownership, addresses, IDs, assignments, powers of attorney, signatures, invoices, or claim evidence.
- Never bypass CAPTCHAs, authentication, rate limits, access controls, or database terms.
- Do not solicit or perform regulated private-investigation, legal, accounting, debt-collection, or claims-representation work without the required license/authorization.
- Verify each jurisdiction's current law before signing a fee agreement or assignment.
- Prefer official, public, machine-readable or manually searchable sources.
- Keep claimant PII out of shared datasets; store only what is needed and restrict access.

## Best launch models

| Model | Capital | Speed | Regulatory burden | Revenue mechanism |
|---|---:|---:|---:|---|
| Bankruptcy unclaimed-funds locator | Low | Medium | Medium | contingency recovery fee / authorized joint payment |
| Bankruptcy claim purchase / successor claim | Low-Medium | Medium | Medium-High | buy claim at discount; recover as successor |
| Foreclosure surplus assignment | Low-Medium | Medium | High | statutory assignment/purchase spread |
| State unclaimed-property locator | Low | Medium | High in some states | capped recovery fee |
| Heir finder / probate genealogy | Low | Medium-Slow | Medium-High | contingency genealogy/recovery fee |
| Federal canceled-check locator | Low | Medium-Slow | Medium | fee for reconnecting payee with issuing agency |
| Dissolved-company asset acquisition | Medium | Medium-Slow | Medium | buy Crown-owned IP/shares/land at agreed value |
| Public auction acquisition | Medium | Fast-Medium | Low-Medium | buy tangible unclaimed property; resale margin |
| Data/lead intelligence for licensed firms | Low | Fast-Medium | Lower if scoped correctly | subscription, software, or B2B research fee |

## Florida operating constraint

Florida defines paid "private investigation" to include locating owners of unclaimed/escheated property and heirs to estates. A Florida-based operator should therefore assume claimant locating is regulated unless counsel or the regulator confirms a specific exemption. The cleanest Florida launch paths are:

- work under / partner with a properly licensed Florida investigative agency;
- pursue the Class CC intern route under a sponsor;
- provide software/data infrastructure to licensed professionals without personally performing regulated investigations; or
- focus on transactions such as public-auction purchases where no claimant locating is being performed.

Florida state-held unclaimed-property claims have an additional Chapter 717 regime: claimant representatives must be registered Florida attorneys, Florida CPAs, or Florida private investigators, and authorized fees/discounts are capped by statute.

## Recommended pilot

1. Build a manually reviewed lead queue from U.S. Bankruptcy Court unclaimed-funds records.
2. Do not perform paid claimant tracing from Florida until a licensing path/partner is in place.
3. In parallel, build the source-ingestion and scoring system using only public fields.
4. Recruit a Florida Class A investigative agency / Class C investigator as operating partner or sponsor.
5. Test 10-25 records with documented chain-of-entitlement and a compliant outreach script.
6. Track: face value, claimant type, evidence difficulty, contactability, expected fee cap, filing friction, and time-to-payment.


## Runnable engine (v1.5.0)

The repository now includes a working Python intelligence engine under `fia/` with:

- SQLite opportunity store and deduplication;
- source/access/compliance registry;
- live adapters for the UK unclaimed-estates CSV, California State Controller bulk ZIP/CSV, USPTO Official Gazette and Federal Laboratory Consortium license-intent notices;
- offline ingestion for the legitimately obtained New York OSC owner-name file;
- Companies House dissolved-company ingestion plus read-only profile/filing/officer/PSC/insolvency research, and USAspending search clients;
- normalized opportunity schema, 0-100 triage score, record-change tracking, and a conservative entity/evidence graph;
- source-run audit history with new/changed/unchanged counts;
- CLI commands for ingestion, ranking, joins, change review and CSV export;
- FastAPI JSON endpoints and a local dashboard; and
- persistent second-hop research-task planning with missing-edge priorities;
- recursive completed-result assimilation into durable evidence facts and graph relations;
- tests plus hard action gates preventing automated claims or regulated outreach.

Quick start:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
fia init-db
fia ingest uk-estates
fia ingest flc
fia ingest california --bucket 500_plus
fia resolve
fia entities --min-sources 2
fia relations --min-confidence 0.9
fia pipeline
fia tasks --min-priority 65
fia rank
fia changes
fia serve
```

Then open `http://127.0.0.1:8787`. See `docs/07-mvp-architecture.md`, `docs/10-v0.2-data-ingestion.md`, and `docs/11-v0.3-entity-resolution.md`.

## Folder map

- `docs/` — project thesis, opportunity map, revenue and data architecture
- `workflows/` — operating procedures by recovery model
- `compliance/` — licensing and legal-control notes
- `templates/` — outreach, intake, due-diligence and case review templates
- `sources/` — official-source registry and research notes
- `schemas/` — structured lead/case schema

This kit is operational research, not legal advice. Before handling real claimant funds, signing assignments, or offering regulated services, have the relevant workflow reviewed for the jurisdiction where the work and claimant are located.


## v0.4 commercial inference

After ingestion, build the evidence graph and commercial triage layer:

```bash
fia resolve
fia infer
fia commercial --min-score 60
fia entity-commercial --min-sources 2
fia case 123
```

`commercial_score` estimates research/commercial interest. `actionability_score` subtracts unresolved legal/compliance preconditions. Fee ceilings, when present, are statutory/official maximum calculations and **not expected revenue**.


## v0.5 anomaly/discrepancy detection

After ingesting records, run the complete analysis pipeline:

```bash
fia pipeline
```

Then review compound findings:

```bash
fia anomaly-rules
fia anomalies --min-severity 70
fia anomaly 1
fia anomaly-state 1 confirmed
```

The detector searches for cross-system discrepancies such as dissolved companies connected to unclaimed assets or IP, potential successor-claim chains, royalty metadata mismatches, lapsed patents with independent commercial signals, high-value identity gaps, and material changes to previously ingested records. Findings are research leads only: entitlement, outreach, assignments, purchases, filings, and royalty claims remain human/compliance gated.

See `docs/15-v0.5-anomaly-discrepancy-engine.md` and `docs/16-source-validation-2026-08-14.md`.

## v0.6 opportunity-graph expansion

Anomaly findings now generate a persistent, ranked research queue:

```bash
fia pipeline
fia plan
fia research-task-types
fia tasks --min-priority 65
fia task 1
fia task-state 1 in_progress
```

The planner records the missing graph edge each task is trying to establish, the blockers it can resolve, expected information uplift, source/access mode, and analyst state. Only whitelisted read-only Companies House API tasks can be auto-executed with `fia task-execute`; court/CAPTCHA, legal, USPTO account, MLC enrollment, outreach, filing and acquisition work remains gated.

See `docs/17-v0.6-opportunity-graph-expansion.md` and `docs/18-source-validation-2026-08-14.md`.


## v0.7 recursive evidence ingestion

Completed research tasks now feed back into the evidence graph:

```bash
fia task-execute 1
fia assimilate
fia facts
fia pipeline
```

For externally completed/manual research, attach a structured JSON result without bypassing any source controls:

```bash
fia task-result-file 12 result.json
fia pipeline
```

The first recursive path is Companies House company -> officer -> officer appointments -> newly linked company -> official profile corroboration. Research facts keep task/source provenance and are evidence only; they do not establish ownership, entitlement, or permission to contact anyone.

See `docs/19-v0.7-recursive-evidence-ingestion.md` and `docs/20-source-validation-2026-08-14.md`.

## v0.8 recursive case resolution

v0.8 adds a bounded case-resolution layer on top of v0.7's recursive evidence graph:

```bash
fia pipeline
fia cases
fia case-resolution 1
fia next-lookup 1
```

Each active anomaly now has a target research state, explicit missing conditions, a finite research budget, and an expected-value-of-information ranking for pending lookups. The resolver recommends one highest-value eligible next lookup instead of expanding every possible edge.

A `review_ready` case means the configured research conditions are satisfied enough for a human legal/commercial decision. It never establishes ownership, entitlement, authority to contact a claimant, authority to purchase/assign a claim, or authority to file.

See `docs/19-v0.8-case-resolution-engine.md` and `docs/20-source-validation-2026-08-14.md`.


## v0.9 adaptive case economics

v0.9 adds a planning-economics layer on top of case resolution:

```bash
fia pipeline
fia economic-cases
fia case-economics 1
fia next-economic-lookup 1
```

For each active case, the engine now separates:

- verified revenue ceilings (for example, a source-specific locator fee cap applied to known property value);
- unknown value (never silently converted into a dollar estimate);
- explicit planning assumptions for intelligence-sale or acquisition/successor-review lanes;
- probability the case remains viable given present evidence and unresolved human/legal gates;
- assumed time-to-value and time discount;
- estimated research cost; and
- probability that a pending lookup resolves a configured case blocker.

The resulting `expected_case_value` and task `economic_score` are triage tools, not earnings forecasts.
They never establish ownership, entitlement, market value, acquisition price, or authorization to contact,
contract with, purchase from, or file on behalf of anybody. All monetary assumptions are returned in the
case output so an analyst can audit or replace them.

See `docs/21-v0.9-adaptive-case-economics.md` and `docs/22-source-validation-2026-08-14.md`.


## v1.0 live scheduler

FIA v1.0 adds a bounded economic scheduler that can automatically execute only whitelisted read-only research. It is dry-run by default.

```bash
fia pipeline
fia scheduler-run
COMPANIES_HOUSE_API_KEY=... fia scheduler-run --execute
fia scheduler-runs
```

The scheduler stops before outreach, contracting, asset purchase, claimant filing, CAPTCHA-gated work, or legal entitlement conclusions. See `docs/23-v1.0-live-research-scheduler.md`.


## v1.1 live source orchestration

FIA now tracks source freshness separately from case research. `fia source-refresh` is a dry-run by default; `--execute` is required before it calls public/read-only sources. `fia portfolio-run` first refreshes due feeds and then allocates permitted research effort across the highest-economic-value case in the portfolio.

```bash
fia source-status
fia source-refresh
fia source-refresh --execute --source flc_license_notices
COMPANIES_HOUSE_STREAM_KEY=... fia source-refresh --execute --source companies_house_stream
fia portfolio-run
fia portfolio-run --execute-sources --execute-research
```

Automatic source modes are deliberately different: California uses a Thursday-oriented bulk refresh, Companies House uses bounded resumable stream catch-up, FLC uses periodic public-page polling, UK estates use periodic public-file polling, and the USPTO Official Gazette uses the most recent Tuesday issue. USPTO ODP stays credential-gated.


## v1.2 discovery breadth + monetization routing

FIA v1.2 adds lawful source breadth and an explicit monetization-routing layer. New importers cover SoundExchange public unclaimed-status signals, authorized MLC metadata exports, Treasury/federal canceled-check data obtained lawfully, manual official bankruptcy exports, official county/court surplus files, and SAM.gov public Contract Opportunities extracts.

```bash
fia ingest soundexchange-file data/soundexchange.csv
fia ingest mlc-file data/mlc.csv
fia ingest treasury-checks-file data/federal-checks.csv
fia ingest bankruptcy-file data/bankruptcy.csv
fia ingest surplus-file data/surplus.csv \
  --jurisdiction "Example County, State, USA" \
  --custodian "Example County Clerk" \
  --source-url "https://official.example.gov/surplus"
fia ingest sam-opportunities-file data/ContractOpportunitiesFullCSV.csv

fia pipeline
fia route-catalog
fia routes --min-score 70
fia route-case anomaly 1
```

The routing layer distinguishes `locator_fee`, `successor_assignment_review`, `asset_acquisition`, `intelligence_sale`, `licensing_introduction`, and `owner_only`. Each route stores prerequisites and prohibited actions. A route is a commercial hypothesis only; it never clears entitlement, owner authority, licensing, assignment, title, court, or jurisdiction-specific legal gates.

See `docs/27-v1.2-discovery-and-monetization-routing.md` and `docs/28-source-validation-2026-08-14.md`.


## v1.3 source-discovery miner

FIA can now discover *candidate datasets* before those datasets become ingestion adapters. It searches official metadata catalogs only, stores provenance and access/licensing metadata, scores the source, and requires an analyst state transition before the source is treated as approved.

Supported discovery catalogs:

- U.S. Data.gov Catalog API v4 (production API key required for automated use)
- UK data.gov.uk CKAN directory
- Canada Open Government Portal CKAN read-only catalog
- European Data Portal read-only Hub Search API

Example:

```bash
fia source-catalogs

# Data.gov automation requires a real key; the other configured catalogs are public metadata searches.
export DATA_GOV_API_KEY='...'
fia source-mine --query 'unclaimed funds' --query 'liquidation distributions'

fia source-candidates --min-score 55
fia source-candidate 12
fia source-candidate-state 12 approved
fia source-mining-runs
```

Candidate-source scoring is auditable and separates asset density, machine readability, access, reuse/licensing metadata, freshness, novelty and monetization fit. A high score does **not** authorize ingestion, outreach, claims, assignments, or use of restricted data.

## v1.4 discovery-of-discovery

FIA can now discover the **portal technology behind candidate datasets**, not just the datasets themselves. It fingerprints public read-only infrastructure and creates analyst-review-only connector proposals for CKAN, Socrata/SODA, ArcGIS Hub/Portal, DCAT/RDF catalogs, advertised SPARQL endpoints, RSS/Atom feeds, and generic bulk-download surfaces.

```bash
fia portal-technologies

# Fingerprint portal origins inferred from v1.3 source candidates.
fia portal-discover

# Or add explicit seeds.
fia portal-discover --url https://example.gov/open-data

fia portal-candidates --min-score 60
fia portal-candidate 12
fia portal-candidate-state 12 approved
fia portal-discovery-runs
```

The portal score is a **connector-build priority**, not an asset valuation. Approval persists across rediscovery, and discovered connectors are never activated automatically. Fingerprinting is bounded to public read-only GET behavior; it does not log in, bypass access controls, issue SPARQL updates, or infer commercial reuse rights from public accessibility.

See `docs/31-v1.4-discovery-of-discovery.md` and `docs/32-source-validation-2026-08-14.md`.



## v1.5 Vestra Intel GPT control layer

v1.5 makes a custom ChatGPT GPT a first-class conversational front end for FIA. The backend remains the persistent intelligence engine; the GPT calls a dedicated bearer-authenticated `/agent/*` API.

```bash
export FIA_AGENT_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export FIA_PUBLIC_BASE_URL="https://your-final-https-host.example"
fia serve
```

After deployment, the GPT Action schema is available at:

```text
https://YOUR-HOST/gpt/openapi.json
```

The release includes:

- `gpt/vestra-intel-instructions.md` — paste into GPT Instructions;
- `gpt/conversation-starters.md`;
- `gpt/knowledge/` — four curated reference files for GPT Knowledge;
- `docs/34-custom-gpt-setup.md` — exact builder workflow;
- `Dockerfile` — public HTTPS backend deployment base;
- `/privacy` — privacy-policy page for the Action configuration.

Live source refresh and automatic read-only research remain preview/dry-run by default. No GPT action exists for claimant outreach, assignments, purchases, claims, filings, CAPTCHA bypass, or binding legal entitlement decisions.

See `docs/33-v1.5-gpt-control-api.md` and `docs/34-custom-gpt-setup.md`.
