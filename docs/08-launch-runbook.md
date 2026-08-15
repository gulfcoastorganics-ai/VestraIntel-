# Launch runbook

## Phase 0 — local setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
fia init-db
pytest
```

## Phase 1 — ingest public intelligence

```bash
fia ingest uk-estates
fia ingest flc
# Supply a verified Official Gazette notices TOC URL for the issue you want to ingest:
fia ingest uspto --url https://patentsgazette.uspto.gov/week02/OG/TOC.htm
fia rank --limit 50
fia serve
```

Open `http://127.0.0.1:8787`.

## Phase 2 — source access

1. Request the New York owner-name file only after deciding whether/when to operate under its location-service-provider rules.
2. Enroll in The MLC Data Access Hub for Public Search API/Bulk Data if the music-rights branch is pursued.
3. Create a Companies House API key and store it only in `COMPANIES_HOUSE_API_KEY`.
4. Keep court/CAPTCHA systems manual unless the custodian publishes an authorized machine interface.

## Phase 3 — first monetizable products

Prioritize products that sell **derived intelligence** and do not require you to hold claimant funds:

- Federal technology / license-intent alert feed.
- Patent available-for-license and expiration radar.
- Dissolved-company asset candidate research for professional buyers/counsel.
- Music metadata reconciliation leads after authorized MLC/SoundExchange access is established.
- Unclaimed-property research software/data services for licensed finders rather than direct claimant representation where licensing is burdensome.

## Review gate

No opportunity becomes `actionable` merely because its score is high. Before outreach or transaction activity, record:

- authoritative source refreshed;
- lawful entitlement or acquisition theory;
- jurisdiction and governing rules;
- licensing/registration status;
- fee/assignment cap;
- identity/ownership evidence required;
- economics and time to recovery;
- written counsel/regulator decision where the rule is unclear.
