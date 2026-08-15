# Source validation — 2026-08-12

This file records current official-source facts used by the MVP. Re-check before production use.

## UK Bona Vacantia estates

- Official GOV.UK unclaimed-estates list is a downloadable CSV.
- GOV.UK showed the list updated 10 August 2026 during validation.
- Discovery does not establish entitlement; claims require the appropriate heir/representative evidence.

Official source: https://www.gov.uk/government/statistical-data-sets/unclaimed-estates-list

## Companies House

- Public company data is available via a REST API.
- API access requires credentials; API keys are sent using HTTP Basic authentication.
- Published default rate limit: 600 requests per five minutes.
- Keep credentials in environment variables, not source control.

Official sources:
- https://developer.company-information.service.gov.uk/
- https://developer.company-information.service.gov.uk/authentication
- https://developer.company-information.service.gov.uk/developer-guidelines

## USPTO Official Gazette

- Official Gazette is published weekly.
- Notices can include patents/applications advertised for license or sale and patents expired for nonpayment of maintenance fees.
- Expiration signals require status/reinstatement/family/FTO diligence before product use.

Official source: https://www.uspto.gov/learning-and-resources/official-gazette

## Federal Laboratory Consortium

- FLC Business publishes current notices of intent to grant exclusive/co-exclusive/partially exclusive federal patent licenses.
- Notices may contain short objection windows; the engine treats them as time-sensitive intelligence, not legal advice.

Official source: https://federallabs.org/flc-business/notice-of-intent-to-license

## USAspending

- USAspending V2 provides public federal award data through an API.
- Advanced award search is available at `/api/v2/search/spending_by_award/`.

Official source: https://api.usaspending.gov/

## New York unclaimed funds

- Location service providers may use a notarized owner authorization/fee agreement.
- Maximum provider fee is 15% of cash/value refunded.
- New York offers a quarterly zipped delimited owner-name file through secure FTP after a request; it omits values and taxpayer IDs.

Official source: https://www.osc.ny.gov/unclaimed-funds/resources/location-service-providers

## Pennsylvania unclaimed property

- Compensated finders must hold a Pennsylvania Treasury Certificate of Finder Registration.
- Maximum fee is 15%.
- Payments go directly to claimants rather than finders.

Official source: https://www.patreasury.gov/Unclaimed-Property/finder/

## California unclaimed property

- California recognizes investigators/asset locators/heir finders.
- General fee ceiling is 10% of property returned, with an exception described for county probated estates.
- California says its public unclaimed-property database can be downloaded in CSV form.

Official sources:
- https://www.sco.ca.gov/upd_investigators.html
- https://www.sco.ca.gov/upd_faq_investigator_claim_dbsearch_q01.html

## Mississippi unclaimed property

- Mississippi Treasury states claim finders may charge a maximum of 10%.
- This build does not yet treat Mississippi as production-cleared because contract/licensing details still need official verification.

Official source: https://treasury.ms.gov/for-citizens/unclaimed-property/learn/

## Music-rights data

- SoundExchange publicly describes four unclaimed/registration-status categories for creators/rightsholders.
- The MLC offers Bulk Data Access and a Public Search API through its Data Access Hub; its unmatched-recordings program exists to help resolve royalties that cannot yet be accurately paid.

Official sources:
- https://www.soundexchange.com/what-we-do/for-artists-labels-and-producers/
- https://www.themlc.com/dataprograms

## Dissolved-company assets (UK)

- Assets of a dissolved company can pass to the Crown as bona vacantia.
- GOV.UK expressly identifies shares, trademarks/copyrights and other assets as potentially referable/purchasable.
- BVD sells qualifying IP at open-market value and is not required to sell an asset to the person who referred it.

Official sources:
- https://www.gov.uk/claiming-money-or-property-from-dissolved-company/overview
- https://www.gov.uk/claiming-money-or-property-from-dissolved-company/buy-dissolved-company-assets
- https://www.gov.uk/guidance/buy-intellectual-property-bvc8
