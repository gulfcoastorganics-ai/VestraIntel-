# Forgotten Asset Intelligence v0.7.0

## Added

- recursive research-result assimilation;
- durable `research_facts` and result-ingestion audit tables;
- Companies House profile, filing, officer, PSC, insolvency, and officer-appointment fact parsers;
- recursive officer -> appointment -> linked-company profile task expansion;
- `fia assimilate`, `fia facts`, `fia feedback-runs`, and `fia task-result-file`;
- `/api/research-facts` and `/api/research-feedback`;
- research evidence included in commercial identity/source corroboration;
- deterministic entity IDs across graph rebuilds;
- structured manual-fact import with conservative confidence/review flags.

## Changed

- `fia pipeline` now assimilates completed results before graph rebuild, commercial inference, anomaly detection, and next-wave planning;
- Companies House read-only executor now supports official officer appointment histories;
- user agent/version metadata updated to 0.7.0.

## Boundaries retained

- no claim filing;
- no claimant outreach;
- no CAPTCHA bypass;
- no automated legal entitlement conclusion;
- no automated acquisition/assignment execution;
- credential/enrollment-gated sources remain gated.
