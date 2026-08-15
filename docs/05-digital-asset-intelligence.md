# Digital Asset & Public-Data Intelligence Models

Research date: 2026-08-11. Re-verify source terms, API access rules, privacy law, and licensing before commercial use.

## Thesis

The highest-value opportunity is often not a hidden file or an ownerless asset. It is a **relationship between two lawful public datasets that nobody has normalized, resolved, or monitored well**.

The project should therefore operate two separate engines:

1. **Recovery Intelligence** — identify assets already owed to a specific owner and route a lawful recovery, referral, or acquisition workflow.
2. **Derived Data Products** — transform public/open/licensed data into a useful commercial signal, without claiming ownership of the source data or exposing restricted personal information.

## Opportunity ranking

| Model | Input | Derived value | Likely buyer | Capital | Revenue speed | Regulatory risk | Priority |
|---|---|---|---|---:|---:|---:|---:|
| Music royalty match intelligence | MLC + SoundExchange metadata | high-confidence unmatched/rightsholder leads | labels, publishers, managers, royalty admins | Low | Fast-Medium | Medium | A+ |
| Procurement rebid clock | SAM + USAspending + TED | likely rebids, incumbent/vendor maps, expiring awards | SMB contractors, consultants | Low | Fast | Low-Medium | A+ |
| Dissolved-company IP watch | Companies House + BVD + trademark/patent/domain data | assets potentially available for Crown sale | IP brokers, agencies, acquirers | Low-Medium | Medium | Medium | A |
| Defunct-owner IP intelligence | USPTO + state corporate registries + SEC | stale/encumbered ownership, acquisition targets | IP attorneys, brokers, lenders | Low | Medium | Medium | A |
| Unclaimed-property lead scoring | state locator files + corporate/public records | owner/contactability/evidence score | registered finders, law firms | Low | Fast-Medium | High if tracing/representation | A |
| Oregon digital-asset recovery intelligence | state unclaimed-property + crypto/estate metadata | lawful recovery leads for native digital assets | licensed finders, estate lawyers, crypto accountants | Low | Medium | High | A- |
| SEC event intelligence | EDGAR real-time + public registries | distress, acquisition, vendor/asset change signals | vendors, investors, consultants | Low | Fast-Medium | Low-Medium | B+ |
| Rights-cleared archival packs | Library of Congress rights-cleared sets | OCR, tags, crops, indexes, embeddings | designers, publishers, researchers | Low | Fast-Medium | Low if rights-screened | B |
| Generic expired-domain intelligence | ICANN-compliant registration data + backlink/market data | descriptive domains with residual utility | builders, marketers | Low-Medium | Fast-Medium | Medium | B |

## Model 1 — Royalty Match Intelligence

### Why this is unusually attractive

SoundExchange publicly maintains categories of creators and rights owners associated with unclaimed royalties. The Mechanical Licensing Collective (The MLC) operates machine-readable bulk data and a Public Search API, plus an unmatched-recordings program designed to help resolve recordings that have not been fully matched to musical works.

The commercial asset is **not the royalty itself** unless the client is legally entitled to it. The commercial asset is a high-confidence metadata reconciliation result.

### Lawful workflow

1. Ingest SoundExchange's public unregistered / partially unregistered creator and sound-recording-owner signals.
2. Ingest The MLC public-search/bulk metadata under its current access terms.
3. Normalize artist, recording, work, label, publisher, writer, ISRC/ISWC and release identifiers.
4. Generate candidate entity links using deterministic rules first, then fuzzy matching.
5. Require evidence fields for every proposed match.
6. Produce a lead such as: `Recording X appears associated with Rightsholder Y; identifier mismatch Z is likely preventing clean matching.`
7. Sell metadata cleanup/reconciliation to the rightsholder or authorized representative, or license the derived intelligence to a royalty administrator.
8. Never submit a claim or ownership assertion without authorization and documentary support.

### Fast MVP

Build a CSV/SQLite prototype with 100-500 public records and output:

- canonical artist/entity
- recording/work title
- identifiers
- suspected owner/rightsholder
- mismatch type
- confidence score
- evidence URLs/source IDs
- recommended correction path
- contact status

The first sale does not require a SaaS product. A verified "royalty leakage audit" for an indie label or catalog owner can be sold as a fixed-fee research service.

## Model 2 — Procurement Rebid Clock

### Thesis

Public procurement portals expose current solicitations, while spending/award systems expose who previously won, how much, and when. Joining those systems can reveal **recurring purchases before a small vendor notices them**.

### U.S. workflow

- SAM.gov: current federal procurement notices and public data services.
- USAspending: comprehensive federal award/spending data.
- Derive: incumbent vendor, award amount, agency, category, period of performance where available, recompete cadence, likely renewal window, and related current notice.

### EU workflow

TED's Search API openly exposes published procurement notices for analysis/reuse and specifically identifies commercial organizations as users that build value-added services for vendors and buyers.

### Monetization

- $29-$99 niche weekly opportunity feed
- $149-$499 "rebid radar" by NAICS/CPV niche
- higher-fee done-for-you bid intelligence for a small set of contractors

This model can produce revenue faster than claimant recovery because no claim-processing cycle is required.

## Model 3 — Dissolved-Company IP Watch

### UK advantage

In England and Wales, assets owned by a dissolved company pass to the Crown as bona vacantia. Official guidance explicitly includes trademarks, patents, copyrights, shares, land, mortgages, cash and other rights. Anybody may refer certain assets they want to buy; the Bona Vacantia Division can sell intellectual property at open-market value after confirming ownership.

### Workflow

1. Monitor Companies House for newly dissolved companies and historic dissolved entities.
2. Resolve each entity against public trademark, patent, domain, software/app and other asset records.
3. Flag digital/IP assets with residual commercial value.
4. Confirm the company owned the asset at dissolution.
5. Determine Crown jurisdiction and whether the asset was restored, disclaimed, transferred, or remains bona vacantia.
6. If economically justified, submit a lawful referral to the relevant Crown body to explore acquisition.
7. Do not assume discovery gives ownership or that the Crown must sell.

### Best targets

- forgotten trademarks with active market meaning
- niche software copyrights where ownership is documented
- patents/design rights with a live commercial niche
- unquoted shares owned by dissolved companies
- contract/mortgage benefits explicitly recognized by BVD guidance

## Model 4 — Defunct-Owner IP Intelligence (United States)

USPTO's Open Data Portal exposes patent/trademark datasets and, as of July 24, 2026, patent assignment export/search moved to ODP for bulk/API access. Combine assignment history with state corporate status and SEC filings to find:

- IP still recorded to dissolved/defunct entities
- stale assignment chains
- security interests/liens recorded against IP
- assets whose corporate owner merged or changed name
- likely acquisition candidates requiring title cleanup

U.S. law does **not** have the same simple Crown-acquisition rule as UK bona vacantia. The product here is intelligence for IP counsel, brokers, lenders, acquirers and former stakeholders—not unilateral appropriation.

## Model 5 — SEC Event Intelligence

SEC data APIs require no API key and expose filing histories and XBRL data, with submissions updating in near real time and bulk files nightly.

Possible commercially useful signals:

- new 8-K restructuring/acquisition events
- material contract/customer concentration disclosures
- name changes and merger trails that help successor-asset research
- distress events that may create receivable/IP/vendor opportunities
- corporate events that help resolve dormant-asset ownership chains

Do not market this as investment advice unless the regulatory implications are understood.

## Model 6 — Rights-Cleared Public-Domain Packs

The Library of Congress publishes curated "Free to Use and Reuse" sets and millions of digital items with collection-specific rights statements.

The value creation is transformation, not pretending to own the originals:

- OCR/transcription
- deduplication
- cleaned metadata
- thematic curation
- crops/derivatives where rights allow
- searchable indexes
- embeddings or machine-learning-ready annotations where legally permitted

Potential customers: designers, publishers, museums, game studios, researchers and ML/data teams.

Every item must retain a rights provenance field because some collections contain third-party copyrighted or privacy/publicity-sensitive material.

## Commercialization channels

AWS Data Exchange allows eligible providers to publish data products containing files, APIs, S3 data access and other supported data-set types through AWS Marketplace. Provider eligibility and data legality/privacy rules must be satisfied.

For a zero-capital pilot, sell the first derived report directly before building marketplace infrastructure.

## Hard boundaries

Do not build revenue from:

- leaked credentials or breach dumps
- stolen private keys or wallets
- bypassing authentication, paywalls, CAPTCHAs or access controls
- unauthorized personal-data brokerage
- impersonating owners/rightsholders
- trademark-typo domains or intentionally confusing brand domains
- claiming abandoned property merely because it was discovered
- submitting false royalty, copyright, corporate-successor or unclaimed-property claims

The durable edge is lawful **normalization + entity resolution + timing + monitoring**, not unauthorized access.

## Model 7 — Federal IP Deal Flow / Expired Patent Radar

The USPTO Official Gazette contains two unusually useful public streams: owner-advertised patents/patent applications available for license or sale, and weekly notices of patents that expired for failure to pay maintenance fees. The Federal Laboratory Consortium and NASA add thousands of government-developed technologies available for licensing, including startup-friendly NASA license structures.

This can become a commercialization-intelligence product or a buyer/seller matching service. A particularly obscure sub-feed is **notices of intent to grant exclusive federal licenses**: monitoring those notices can tell an industry participant that a government-owned technology is about to become exclusively licensed while the public notice window is still open.

See `workflows/08-federal-ip-and-expired-patent-radar.md`.
