# Source Validation — 2026-08-14

This file records the official-source assumptions used by v0.6.

## Companies House

Status: **validated official read-only API**.

The Companies House Public Data API documents endpoints for company profiles, officers, filing history, insolvency, charges, registered office address, and persons with significant control. API-key authentication is required for the read endpoints used by the engine.

References:

- https://developer.company-information.service.gov.uk/get-started
- https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/reference
- https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/reference/officers/list
- https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/reference/persons-with-significant-control/list
- https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/reference/filing-history/list
- https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/reference/insolvency/get

The profile resource also exposes previous company names and registered-office information. These are corroborating evidence only and do not establish ownership of another asset.

## USPTO Open Data Portal

Status: **official account-gated research source**.

USPTO states that Open Data Portal access requires sign-in with a USPTO.gov account beginning June 18, 2026. Patent Export Assignment Data Search moved from Assignment Center to Open Data Portal effective July 24, 2026.

References:

- https://data.uspto.gov/apis/bulk-data/search
- https://www.uspto.gov/system-status/20260707-assignment-center-patent-search-service-alert

v0.6 therefore plans assignment/status research tasks but does not implement anonymous scraping or authentication bypass.

## U.S. Bankruptcy unclaimed funds

Status: **manual/court-process gate**.

Federal bankruptcy courts publish successor-claim procedures. Examples state that a successor may be entitled through assignment, purchase, merger, acquisition, succession, or other means, but documentation sufficient to establish the chain of ownership/transfer is required. Local court procedures vary.

References:

- https://www.ohsb.uscourts.gov/unclaimed-funds
- https://www.alnb.uscourts.gov/unclaimed-funds
- https://www.nmb.uscourts.gov/successor-claimant
- https://www.canb.uscourts.gov/case-info/unclaimed-dividends/instructions-submitting-application-unclaimed-dividends

The national locator uses an interactive challenge. v0.6 never automates around CAPTCHA.

## Boundary encoded in v0.6

The planner may identify a missing edge such as `successor_of`, `assigned_to`, or `controlled_by`. A planned or discovered edge is **evidence for review**, not an ownership or entitlement conclusion.
