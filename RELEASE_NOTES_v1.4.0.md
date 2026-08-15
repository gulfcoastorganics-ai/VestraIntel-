# Forgotten Asset Intelligence v1.4.0

## Discovery-of-discovery

v1.4 adds a portal fingerprinting and connector-proposal subsystem above the v1.3 dataset miner.

### Added

- `fia/portal_discovery.py`
- persistent `portal_candidates` table
- persistent `portal_discovery_runs` audit table
- CKAN fingerprinting and connector proposal
- passive Socrata/SODA fingerprinting with SODA3 credential note
- ArcGIS Portal / Hub public-search fingerprinting
- DCAT/RDF metadata discovery
- bounded read-only SPARQL endpoint confirmation when explicitly advertised
- RSS/Atom feed discovery
- generic machine-readable bulk-download discovery
- connector-priority scoring
- analyst state persistence across rediscovery
- source-candidate → portal-origin expansion using landing, metadata and resource URLs

### New CLI

```text
fia portal-technologies
fia portal-discover
fia portal-candidates
fia portal-candidate
fia portal-candidate-state
fia portal-discovery-runs
```

### New API

```text
GET /api/portal-discovery/technologies
GET /api/portal-discovery/candidates
GET /api/portal-discovery/candidates/{id}
GET /api/portal-discovery/runs
```

### Boundaries

- read-only GET fingerprinting only;
- no credentials are discovered or bypassed;
- no CAPTCHA bypass;
- no SPARQL updates;
- no active Socrata SODA3 query during platform fingerprinting;
- no new connector is activated without analyst approval;
- public availability is not treated as a license for commercial reuse.

### Validation

- 70 tests passing
- Python compilation passing
- v1.3 database migration path exercised through schema initialization
- CLI discovery commands load
- FastAPI portal-discovery routes smoke-tested
