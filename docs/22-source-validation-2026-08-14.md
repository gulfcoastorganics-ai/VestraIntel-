# Source validation — 2026-08-14

This release revalidated the economic assumptions against primary/official sources.

## California State Controller — investigators / asset locators

Official source: https://sco.ca.gov/upd_investigator_about.html

The Controller states that investigators/asset locators may not charge more than 10% of the value of property returned to an owner (with the stated county-probated-estate exception). FIA therefore uses 10% only as a maximum fee ceiling when a California record has a known value. It is not treated as expected revenue.

## New York Office of the State Comptroller — location service providers

Official source: https://www.osc.ny.gov/unclaimed-funds/resources/location-service-providers

The Office says the maximum location-service-provider fee is 15% of cash or securities refunded and requires an owner agreement. The quarterly provider data file intentionally omits property dollar values and taxpayer identifiers. FIA therefore leaves New York case value unknown unless a value is obtained legitimately elsewhere.

Official claimant timing source: https://www.osc.ny.gov/unclaimed-funds/claimants/how-search-claim-property

The Office says most direct claims are paid within 30 days. FIA does not use 30 days as a locator guarantee; v0.9 uses a more conservative editable 45-day planning assumption for the locator lane.

## U.S. Courts — bankruptcy unclaimed funds

Official source: https://www.uscourts.gov/court-programs/bankruptcy/unclaimed-funds-bankruptcy

The federal judiciary states that unclaimed bankruptcy funds may be claimed by an owner, successor, or other claimant who proves a right to the funds. FIA does not treat face value as a service fee or guaranteed recoverable margin.

Representative successor documentation source: https://www.ohsb.uscourts.gov/unclaimed-funds

The Southern District of Ohio explains that a successor may arise through assignment, purchase, merger, acquisition, succession, or other means and requires documentation sufficient to establish the transfer/ownership chain. FIA keeps successor cases behind a chain-of-ownership and court-review gate.

## Companies House API

Official sources:

- https://developer-specs.company-information.service.gov.uk/guides/gettingStarted
- https://developer-specs.company-information.service.gov.uk/guides/rateLimiting

Companies House requires authentication for API services and documents a default rate limit of 600 requests per five minutes per application. v0.9 does not price a Companies House lookup as if it were a paid data purchase, but it retains analyst-time/access-mode costs and does not attempt to bypass the rate limit.
