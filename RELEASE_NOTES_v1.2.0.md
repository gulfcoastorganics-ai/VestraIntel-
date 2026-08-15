# Release Notes — Forgotten Asset Intelligence v1.2.0

Date: 2026-08-14

## Headline

v1.2 broadens FIA from source/case orchestration into **discovery breadth + lawful monetization routing**.

## Added

- `fia/monetization.py`
  - persistent route inference for opportunities and anomaly cases;
  - six commercial routes: locator fee, successor/assignment review, asset acquisition, intelligence sale, licensing introduction, owner-only;
  - explicit prerequisites and prohibited actions.
- `fia/sources/music_rights.py`
  - SoundExchange unclaimed-status import;
  - authorized MLC metadata/reconciliation import;
  - ISRC preservation for cross-source resolution.
- `fia/sources/treasury_unpaid.py`
  - Treasury/federal canceled/unpaid-check record import;
  - payee confirmation and agency-validation gates.
- `fia/sources/court_funds.py`
  - official/manual bankruptcy unclaimed-funds import;
  - provenance-required county/court surplus-funds import.
- `fia/sources/sam_contracts.py`
  - public SAM.gov Contract Opportunities file import.
- API endpoints for the monetization route catalog and route cases.
- CLI ingestion commands and route inspection commands.
- Four new workflow documents plus current official-source validation.

## Changed

- Package/API version bumped to 1.2.0.
- `fia pipeline` now rebuilds monetization routes after anomaly detection.
- Source registry now identifies Treasury canceled-check, SAM contract, UK bona vacantia, and generic official surplus workflows.
- Manual/gated source families appear as disabled orchestration policies rather than being silently scraped.

## Safety/compliance behavior

- SoundExchange rows route to `owner_only`; cross-system royalty discrepancies can route to metadata intelligence, not third-party royalty claims.
- Treasury cancellation data does not establish payee identity.
- Bankruptcy remains court/chain-of-ownership gated and CAPTCHA is not bypassed.
- County/court surplus records carry no universal fee or assignment rule.
- Dissolved-company IP anomalies route to official acquisition review rather than inferred ownership.

## Validation

`56 passed`
