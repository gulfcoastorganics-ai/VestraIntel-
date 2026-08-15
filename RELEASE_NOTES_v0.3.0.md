# Forgotten Asset Intelligence v0.3.0

## Added

- conservative entity-resolution engine;
- canonical nodes for Companies House company numbers, patent numbers, ISRCs, and exact normalized owner/entity names;
- evidence memberships between public records and entities;
- co-occurrence graph edges;
- organization-only fuzzy variant relations with human-review evidence;
- person-name fuzzy matching intentionally disabled;
- Companies House dissolved-company results can now be ingested as first-class intelligence records;
- entity graph CLI commands: `resolve`, `entities`, `relations`, `graph`;
- entity graph API endpoints;
- improved `company_number` extraction from JSON-style source fields;
- bounded fuzzy candidate generation and pathological-block suppression.

## Validation

- 12 tests passing;
- Python compilation passing;
- entity-resolution smoke flow passing;
- strong company-number join and organization-name variant behavior covered by tests.

## Safety / compliance boundary

The graph produces candidate relationships and provenance only. It does not automatically claim that two people/companies are legally identical, determine entitlement, contact owners, sign assignments, or submit claims.
