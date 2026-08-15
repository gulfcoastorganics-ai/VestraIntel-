# Source Validation — 2026-08-14

## U.S. Data.gov

Current Catalog API documentation identifies v4 at `https://api.gsa.gov/technology/datagov/v4/`. Automated requests require an api.data.gov key in the `X-Api-Key` header. `DEMO_KEY` exists only for exploration and is explicitly described as unsuitable for automated/production use. FIA therefore requires `DATA_GOV_API_KEY` for this miner.

## UK data.gov.uk

Current National Data Library guidance documents the CKAN-compatible directory API under `https://data.gov.uk/api/action/`, including `package_search`; the guidance states no API key and no rate limit are required. FIA uses the read-only metadata search only.

## Canada Open Government

The Government of Canada publishes an Open Government API providing live read-only access to the CKAN portion of the public Open Government Portal without an API key. FIA uses only public read operations.

## data.europa.eu

The European Data Portal documents a Hub Search API for metadata discovery and states that Search API actions are read-only. FIA uses the `/search` metadata endpoint and does not assume access to restricted repository actions.

## Operational policy

A catalog result is only a candidate source. FIA does not infer that all linked distributions are public, reusable, commercially exploitable, or legally appropriate. Distribution/license/access metadata is retained for human review.
