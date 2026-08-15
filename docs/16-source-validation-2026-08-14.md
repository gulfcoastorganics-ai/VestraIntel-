# v0.5 source validation — 2026-08-14

This release revalidated the rules against official/primary sources.

## U.S. Bankruptcy Unclaimed Funds

- U.S. Courts states that bankruptcy unclaimed funds are held for someone entitled to the money and may be claimed by an owner, successor, or other claimant who proves a right to the funds.
- The judiciary's national Unclaimed Funds Locator is a federated search and requires CAPTCHA authentication to initiate searches.
- The Southern District of Ohio expressly describes successor entitlement resulting from assignment, purchase, merger, acquisition, succession, or other means and requires supporting documentation.
- v0.5 therefore registers this source as `manual_or_court_export_only`; it will not automate around CAPTCHA.

Official references:
- https://www.uscourts.gov/court-programs/bankruptcy/unclaimed-funds-bankruptcy
- https://ucf.uscourts.gov/
- https://www.ohsb.uscourts.gov/unclaimed-funds

## Companies House

The official dissolved-company search returns company number, status, cessation/creation dates, previous-company-name data, and registered-office address when present. API-key authentication is required.

Official reference:
- https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/reference/search/search-dissolved-companies

## USPTO maintenance-fee expirations

USPTO publishes weekly Official Gazette notices for patents that expire after failure to pay maintenance fees. USPTO also has a reinstatement procedure for unintentionally delayed maintenance payment. Therefore, an expiration notice is a research signal and is never treated as permanent public-domain clearance without a fresh status/family review.

Official references:
- https://www.uspto.gov/patents/maintain
- https://patentsgazette.uspto.gov/

## The MLC

The MLC's data programs are designed to let technology/media companies use ownership and sound-recording data. Its Distributor Unmatched Recordings Portal exposes unmatched recordings to eligible distributors/aggregators to improve matching and royalty distribution.

Official reference:
- https://www.themlc.com/dataprograms

## SoundExchange

SoundExchange publishes statuses for unclaimed royalties including unregistered artists, partially unregistered artists, unregistered performers, and unregistered sound recording owners. SoundExchange states that it does not need a digital royalty broker and generally pays the entitled creator/rightsholder rather than third parties. v0.5 therefore treats SoundExchange correlations as metadata/reconciliation intelligence rather than a third-party claim mechanism.

Official references:
- https://www.soundexchange.com/what-we-do/for-artists-labels-and-producers/
- https://www.soundexchange.com/frequently-asked-questions/

## UK dissolved-company assets

GOV.UK confirms that dissolved-company assets can pass to the Crown as bona vacantia and that assets can include patents, trademarks, copyright, shares, cash, land, and contractual rights. Anyone can refer certain assets, but Crown disposal is discretionary and normally at full/open market value; title and restoration risks remain.

Official references:
- https://www.gov.uk/claiming-money-or-property-from-dissolved-company
- https://www.gov.uk/guidance/buy-intellectual-property-bvc8
- https://www.gov.uk/government/publications/bona-vacantia-dissolved-companies-bvc1/bona-vacantia-dissolved-companies-bvc1
