# Release Notes — v0.6.0

## Added

- Persistent second-hop research task queue.
- Missing-edge planning from anomaly findings.
- Priority scoring by severity, actionability, evidence confidence, information uplift, effort, and access friction.
- Task states with audit persistence: pending, in-progress, completed, dismissed, blocked, stale.
- Expected graph relation and blocker-resolution metadata per task.
- Companies House read-only research execution for profile, filing history, officers, PSC and insolvency endpoints.
- Research task catalog and CLI/API surfaces.
- Dashboard count for pending research tasks.

## New CLI

```text
fia plan
fia research-task-types
fia tasks
fia task <id>
fia task-state <id> <state>
fia task-execute <id>
```

`fia pipeline` now runs entity resolution → commercial inference → anomaly detection → research planning.

## New API

```text
GET /api/research-task-types
GET /api/research-tasks
GET /api/research-tasks/{task_id}
```

## Safety/compliance boundary

Only whitelisted read-only Companies House API tasks can be executed automatically. Bankruptcy/CAPTCHA work, legal conclusions, claimant outreach, assignments/purchases, USPTO account-gated tasks and MLC enrollment-gated tasks remain manual/gated.

## Validation

- Python compilation: PASS
- Unit tests: 26 passed
- Synthetic end-to-end pipeline: PASS
- Research queue ordering: PASS
- FastAPI research endpoints: PASS
- Read-only Companies House path tests: PASS
