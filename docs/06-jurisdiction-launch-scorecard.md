# Jurisdiction Launch Scorecard

Research date: 2026-08-11.

This file is a **launch shortlist**, not a substitute for current legal review. Rules can depend on asset type, age of property, owner location, where the work is performed, and whether the operator is tracing people, preparing claims, buying claims, or merely licensing data.

## Verified high-signal jurisdictions

| Jurisdiction | Fee economics | Data access | Licensing / barrier | Waiting period | Launch view |
|---|---|---|---|---|---|
| New York | up to 15% | Excellent: quarterly statewide zipped delimited text file available to location-service providers; includes names, last-known addresses, nature of property, reporter; excludes amounts/TINs | Follow NY location-service-provider agreement rules | Verify property-specific timing before contracting | **Tier A — best data-driven finder feed found** |
| Pennsylvania | up to 15% | Good public program; finder list/registration | Finder Certificate of Registration required | Verify current property-specific restrictions | **Tier A — clear finder regime** |
| California | up to 10%; county probated-estate investigator fees not subject to same 10% limit | Strong investigator resources, estate files, forms | Standard investigator agreements/workflow; determine any separate PI/other licensing implications for actual services | statutory restrictions apply | **Tier A-/B+ — standardized, probate niche notable** |
| Maine | compensation must satisfy statutory contract/unconscionability rules | Public program | Agreement must satisfy statute | 24 months after delivery to administrator | **Tier B — older inventory only** |
| Arizona | up to 30% | Weak for bulk: searchable list; source/value/nature confidential until authorized | Current PI license required for locator/heir finder | fee only after property held >2 years | **Tier C for launch despite high nominal fee** |
| Florida | Chapter 717 recovery/purchase regime plus Chapter 493 PI issues | Good state/county sources | Florida claimant representation/tracing can trigger PI/attorney/CPA and registration rules | asset-specific | **Partner-only / specialized acquisition workflows** |

## Why New York is strategically important

The New York Office of the State Comptroller explicitly offers location service providers a quarterly statewide file through secure FTP. The file can be imported into software and contains names, last-known addresses, property nature, and reporting holder, while withholding amounts and taxpayer IDs.

That is almost ideal for an intelligence engine because it provides a lawful, refreshable, structured lead universe. The first product could be **lead scoring for registered providers** even before operating recovery agreements directly.

## Why Pennsylvania is attractive

Pennsylvania explicitly allows compensated finders who obtain a Treasury certificate. Current Treasury guidance caps fees at 15%, requires a written agreement with disclosures, and pays the claimant directly rather than routing the owner's funds through the finder.

This creates a clear compliance target and lowers ambiguity compared with jurisdictions that require a PI license.

## Why Arizona is not the obvious winner

The 30% headline cap looks attractive, but official Arizona guidance says:

- the property must have been held over two years before a locator is legally entitled to a fee;
- an asset locator/heir finder must be a currently licensed private investigator;
- the state does not provide a downloadable locator list;
- source/value/nature are confidential until an authorized claimant is involved; and
- roughly 75% of reported accounts are under $100.

So the nominal fee ceiling overstates the actual opportunity.

## Secondary 50-state triage source

A 2026 commercial reference table was reviewed only to identify statutes/candidates for later official verification. It is **not authoritative** and has at least some discrepancies with official/current state materials, so its fee numbers must not be used operationally until each state's statute/treasury guidance is checked.

The project should verify states in this order:

### Wave 1 — likely attractive based on economics/data

New York, Pennsylvania, California, Colorado, South Dakota, Oklahoma, New Jersey, Hawaii, Wisconsin, Michigan, Arkansas, Idaho, Iowa, Kansas, South Carolina.

### Wave 2 — middle-of-market / likely 10% or material waiting rules

Alabama, Alaska, Connecticut, Georgia, Illinois, Indiana, Kentucky, Louisiana, Massachusetts, Minnesota, Mississippi, Missouri, Montana, Nebraska, Nevada, New Hampshire, New Mexico, Ohio, Rhode Island, Tennessee, Texas, Utah, Virginia, West Virginia, Wyoming, District of Columbia.

### Wave 3 — structural friction / lower priority

Arizona (PI license despite 30%), Florida (special representative/PI regime), North Carolina (PI/license friction), Oregon (finder/PI implications; digital-asset niche merits separate partner model), Vermont (bond/license friction), Washington (low fee ceiling), Delaware (longer finder-agreement lockout), Maine (24-month older-inventory play).

### Unverified / explicitly queued

Maryland, North Dakota and any jurisdiction whose current official 2026 source has not yet been added to `sources/official-sources.md`.

## Scoring formula

Use a 100-point launch score:

- 25 — maximum lawful economic take / fee structure
- 20 — machine-readable or downloadable lead data
- 15 — no PI/attorney/CPA prerequisite
- 10 — no long finder lockout
- 10 — claimant payment/processing speed
- 10 — average/likely property value
- 5 — remote/nonresident operator friendliness
- 5 — clear forms, standard contracts, published finder guidance

A state cannot receive a production score until its official statute and administrator guidance are both verified.
