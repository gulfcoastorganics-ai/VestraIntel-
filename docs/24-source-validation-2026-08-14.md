# v1.0 Source Validation — 2026-08-14

Official-source checks used for the scheduler boundaries:

- Companies House API authentication: API credentials are required. https://developer.company-information.service.gov.uk/authentication
- Companies House developer guidelines: default rate limit is 600 requests per five minutes, and attempts to bypass it may be banned. https://developer.company-information.service.gov.uk/developer-guidelines/
- USPTO Open Data Portal: a USPTO.gov account is required starting June 18, 2026; documented API endpoints require API keys. https://data.uspto.gov/apis/bulk-data/search
- U.S. Courts bankruptcy unclaimed funds: funds remain payable to an owner, successor, or other claimant who proves a right to them; court-specific procedures control. https://www.uscourts.gov/court-programs/bankruptcy/unclaimed-funds-bankruptcy
- Southern District of Ohio bankruptcy instructions: successor claimants can arise through assignment, purchase, merger, acquisition, succession, or other means, but documentation establishing the ownership/transfer chain is required. https://www.ohsb.uscourts.gov/unclaimed-funds
- California State Controller: investigators/asset locators may not charge more than 10% of property returned to owners. https://sco.ca.gov/upd_investigator_about.html
- New York OSC: location-service-provider fees are capped at 15%; owner authorization/fee agreement is required; the provider data file omits amounts and taxpayer identifiers. https://www.osc.ny.gov/unclaimed-funds/resources/location-service-providers
