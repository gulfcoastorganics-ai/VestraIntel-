# Forgotten Asset Intelligence v0.2.0

Released for local evaluation: 2026-08-14

## Added

- California State Controller public bulk unclaimed-property adapter.
- California offline ZIP/CSV importer.
- New York OSC owner-name ZIP/TXT/CSV importer for files legitimately obtained through OSC's request flow.
- Generic resilient delimited-file parser with ZIP support and header aliasing.
- Companies House dissolved-company search, date-range search and filing-history client methods.
- Source-run audit table.
- New/changed/unchanged source-record classification using stable fingerprints.
- `/api/runs`, `/api/changes`, and `/api/joins` endpoints.
- `fia runs` and `fia changes` commands.
- Dashboard counters for recent changes, joins and ingestion runs.
- USPTO Open Data Portal credential gate reflecting the 2026 sign-in/API-key requirement.

## Validation

- Python compilation: passed.
- Unit tests: 9 passed.
- FastAPI route smoke test: passed.
- California local-file CLI ingestion smoke test: passed.
- No access controls, CAPTCHA systems, private databases or claimant identity checks were bypassed.

## External-access note

The build environment used for code validation did not have general outbound DNS access, so live source adapters were validated structurally against current official source documentation plus local parser/API fixtures. Run live ingestion from a normal networked environment.
