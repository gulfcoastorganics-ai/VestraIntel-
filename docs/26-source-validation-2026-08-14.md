# Source Validation — 2026-08-14

The v1.1 source scheduler was checked against current official documentation on 2026-08-14.

## California State Controller

Official public unclaimed-property records are downloadable in CSV archives, including a `$500 and up` dataset and a complete dataset. The Controller states that the files are updated every Thursday.

Source: https://www.sco.ca.gov/upd_download_property_records.html

Implementation: `weekly_bulk`; FIA chooses a Thursday-oriented refresh schedule. The source's published fact is the Thursday update; FIA does not assume an unpublished exact update hour.

## Companies House

Companies House provides an official Streaming API with real-time company-information changes. The company stream is `GET https://stream.companieshouse.gov.uk/companies`. A `timepoint` can resume from a previously received event, subject to validity/retention. Streaming requires a separately registered streaming key; REST API and streaming keys are not interchangeable.

Sources:
- https://developer-specs.company-information.service.gov.uk/streaming-api/guides/overview
- https://developer-specs.company-information.service.gov.uk/streaming-api/reference/company-information/stream
- https://developer-specs.company-information.service.gov.uk/streaming-api/guides/authentication

Implementation: bounded stream catch-up, persisted timepoint, only dissolved/ceased company-profile events normalized as discovery records. Quiet read timeout is treated as a successful bounded catch-up rather than an infinite wait.

## Federal Laboratory Consortium

FLC Business maintains a public Notice of Intent to License page with dated federal licensing notices. It included 2026 notices during validation.

Source: https://federallabs.org/flc-business/notice-of-intent-to-license

Implementation: public-page polling. FIA's default 12-hour check interval is an operator policy, not a claim that FLC publishes on a 12-hour schedule.

## USPTO Official Gazette

USPTO states that the Official Gazette for Patents is published weekly on Tuesday and provides the most recent weekly issues online.

Sources:
- https://www.uspto.gov/learning-and-resources/official-gazette
- https://www.uspto.gov/learning-and-resources/official-gazette/official-gazette-patents

Implementation: FIA derives the most recent Tuesday issue URL and ingests the notices table of contents with the existing patent-license/expiration parser.

## USPTO Open Data Portal

ODP requires a valid USPTO.gov account beginning June 18, 2026, and ODP APIs require API keys. The generic product-search endpoint is authenticated.

Source: https://data.uspto.gov/apis/bulk-data/search

Implementation: registered as a credential-gated source but disabled for generic autonomous refresh until a product-specific query is configured. FIA does not try to bypass sign-in or API-key requirements.
