# FIA v1.3.0 Release Notes

## Source Discovery Mining

FIA now searches official government/open-data metadata catalogs for previously unknown candidate datasets. Candidates are scored and stored separately from operational asset records.

### New commands

- `fia source-catalogs`
- `fia source-mine`
- `fia source-candidates`
- `fia source-candidate <id>`
- `fia source-candidate-state <id> <state>`
- `fia source-mining-runs`

### New API

- `GET /api/source-discovery/catalogs`
- `GET /api/source-discovery/candidates`
- `GET /api/source-discovery/candidates/{id}`
- `GET /api/source-discovery/runs`

### Scoring dimensions

- asset-density language
- machine-readable formats
- public/access status
- explicit license/reuse metadata
- freshness
- low-popularity/novelty signal when a catalog exposes it
- monetization-route fit

The score prioritizes investigation. It does not establish ownership, legality, commercial value, or authority to use a dataset.
