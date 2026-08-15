# Workflow 05 — Music Royalty Match Intelligence

## Objective

Turn publicly/legitimately accessible music ownership and unmatched-recording metadata into evidence-backed reconciliation leads for creators, labels, publishers, managers and royalty administrators.

## Sources

- SoundExchange creator/rightsholder unclaimed-royalty search/list categories
- SoundExchange ISRC/search resources where permitted
- The MLC Public Search API
- The MLC Bulk Data Access program
- The MLC Distributor Unmatched Recordings Portal for eligible distributors
- client-provided catalog exports and identifiers

## Record model

- artist_display_name
- performer_legal_or_registered_name (only when lawfully/publicly sourced)
- sound_recording_owner
- recording_title
- musical_work_title
- ISRC
- ISWC
- label
- publisher
- writers
- release/product identifiers
- source_system
- mismatch_type
- candidate_match
- evidence
- confidence
- owner_authorization_status
- remediation_path

## Matching sequence

1. exact identifier match
2. normalized exact title + artist/writer match
3. label/publisher corroboration
4. fuzzy title/name candidate generation
5. release-date/catalog-number corroboration
6. human review
7. client/rightsholder confirmation

Never turn a fuzzy candidate directly into an ownership assertion.

## Monetization

- fixed-fee catalog leakage audit
- per-verified-match cleanup fee
- monthly catalog monitoring
- B2B lead/data licensing to authorized rights administrators
- contingency recovery only after counsel confirms the applicable agreement/licensing/representation rules

## Fast launch experiment

Create a 100-record sample, identify 10 high-confidence reconciliation candidates, and sell the **research result**, not the claim. The initial goal is proving someone will pay for improved metadata and reduced royalty leakage.
