# Source validation — 2026-08-14

This release revalidated the source assumptions used by the entity-resolution tranche against official documentation.

## California State Controller

- The Controller publishes the public unclaimed-property database as downloadable CSV files.
- The official page splits records into value bands and an all-records archive.
- The page states the files are updated every Thursday.
- The engine therefore treats California bulk files as authoritative public discovery input and preserves the source record rather than scraping claimant workflows.

Official source: `https://sco.ca.gov/upd_download_property_records.html`

## Companies House

- The Companies House public API exposes company profiles at `/company/{companyNumber}`.
- `company_number` is a first-class field in company resources and search results.
- Search/profile endpoints require an API key.
- The documented default rate limit is 600 requests per five minutes.
- v0.3 therefore treats company number as a strong public identifier and never attempts to evade the API's authentication or rate limits.

Official sources:

- `https://developer.company-information.service.gov.uk/get-started`
- `https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/reference/company-profile/company-profile`
- `https://developer.company-information.service.gov.uk/developer-guidelines/`

## USPTO Open Data Portal

- Patent assignment export/search moved into the Open Data Portal in July 2026.
- ODP requires account sign-in as of June 18, 2026.
- The project continues to keep ODP assignment enrichment credential-gated rather than bypassing the sign-in requirement.

Official sources:

- `https://www.uspto.gov/system-status/20260707-assignment-center-patent-search-service-alert`
- `https://data.uspto.gov/apis/bulk-data/search`

## Resolution consequence

Identifiers are not treated equally:

- Companies House company numbers, patent numbers, and ISRCs: strong deterministic identifiers for the referenced object/entity class.
- Exact owner/entity names: cross-source evidence, not proof of legal identity.
- Fuzzy person names: disabled.
- Fuzzy organization names: review-only relationship candidates.
