from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Iterable
from datetime import datetime, timezone
from dataclasses import dataclass

from .models import Opportunity
from .keying import extract_keys

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS opportunities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id TEXT NOT NULL,
  external_id TEXT NOT NULL,
  asset_class TEXT NOT NULL,
  title TEXT NOT NULL,
  owner_name TEXT,
  jurisdiction TEXT NOT NULL,
  custodian TEXT NOT NULL,
  face_value TEXT,
  currency TEXT,
  published_at TEXT,
  claim_deadline TEXT,
  source_url TEXT NOT NULL,
  legal_model TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'discovered',
  compliance_status TEXT NOT NULL DEFAULT 'review_required',
  score REAL NOT NULL DEFAULT 0,
  notes TEXT,
  raw_json TEXT,
  ingested_at TEXT NOT NULL,
  UNIQUE(source_id, external_id)
);
CREATE INDEX IF NOT EXISTS idx_opportunities_score ON opportunities(score DESC);
CREATE INDEX IF NOT EXISTS idx_opportunities_asset_class ON opportunities(asset_class);
CREATE INDEX IF NOT EXISTS idx_opportunities_jurisdiction ON opportunities(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities(status);
CREATE TABLE IF NOT EXISTS opportunity_keys (
  opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
  key_type TEXT NOT NULL,
  key_value TEXT NOT NULL,
  PRIMARY KEY (opportunity_id, key_type, key_value)
);
CREATE INDEX IF NOT EXISTS idx_opportunity_keys_value ON opportunity_keys(key_type, key_value);
CREATE TABLE IF NOT EXISTS source_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id TEXT NOT NULL,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  status TEXT NOT NULL DEFAULT 'running',
  record_count INTEGER NOT NULL DEFAULT 0,
  new_count INTEGER NOT NULL DEFAULT 0,
  changed_count INTEGER NOT NULL DEFAULT 0,
  unchanged_count INTEGER NOT NULL DEFAULT 0,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_source_runs_source ON source_runs(source_id, id DESC);
CREATE TABLE IF NOT EXISTS opportunity_versions (
  source_id TEXT NOT NULL,
  external_id TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  last_changed_at TEXT,
  change_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(source_id, external_id)
);
CREATE INDEX IF NOT EXISTS idx_versions_changed ON opportunity_versions(last_changed_at DESC);

CREATE TABLE IF NOT EXISTS entities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_type TEXT NOT NULL,
  canonical_key TEXT NOT NULL,
  display_name TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(entity_type, canonical_key)
);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE TABLE IF NOT EXISTS entity_memberships (
  entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  match_method TEXT NOT NULL,
  confidence REAL NOT NULL,
  evidence_json TEXT NOT NULL,
  PRIMARY KEY(entity_id, opportunity_id, role)
);
CREATE INDEX IF NOT EXISTS idx_entity_membership_opportunity ON entity_memberships(opportunity_id);
CREATE TABLE IF NOT EXISTS entity_relations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  left_entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  right_entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  relation_type TEXT NOT NULL,
  confidence REAL NOT NULL,
  evidence_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(left_entity_id, right_entity_id, relation_type)
);
CREATE INDEX IF NOT EXISTS idx_entity_relations_type ON entity_relations(relation_type, confidence DESC);
CREATE TABLE IF NOT EXISTS commercial_assessments (
  opportunity_id INTEGER PRIMARY KEY REFERENCES opportunities(id) ON DELETE CASCADE,
  lane TEXT NOT NULL,
  commercial_score REAL NOT NULL,
  actionability_score REAL NOT NULL,
  evidence_confidence REAL NOT NULL,
  independent_source_count INTEGER NOT NULL DEFAULT 1,
  value_score REAL NOT NULL,
  identity_score REAL NOT NULL,
  cross_source_score REAL NOT NULL,
  recoverability_score REAL NOT NULL,
  time_to_money_score REAL NOT NULL,
  regulatory_friction_score REAL NOT NULL,
  acquisition_score REAL NOT NULL,
  fee_cap_percent REAL,
  gross_fee_ceiling TEXT,
  currency TEXT,
  reason_json TEXT NOT NULL,
  block_json TEXT NOT NULL,
  next_action_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_commercial_score ON commercial_assessments(commercial_score DESC);
CREATE INDEX IF NOT EXISTS idx_commercial_actionability ON commercial_assessments(actionability_score DESC);
CREATE INDEX IF NOT EXISTS idx_commercial_lane ON commercial_assessments(lane);
CREATE TABLE IF NOT EXISTS entity_commercial_summaries (
  entity_id INTEGER PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
  commercial_score REAL NOT NULL,
  actionability_score REAL NOT NULL,
  primary_lane TEXT NOT NULL,
  opportunity_count INTEGER NOT NULL,
  source_count INTEGER NOT NULL,
  asset_classes_json TEXT NOT NULL,
  jurisdictions_json TEXT NOT NULL,
  value_by_currency_json TEXT NOT NULL,
  fee_ceiling_by_currency_json TEXT NOT NULL,
  lane_mix_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entity_commercial_score ON entity_commercial_summaries(commercial_score DESC);

CREATE TABLE IF NOT EXISTS anomaly_findings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fingerprint TEXT NOT NULL UNIQUE,
  rule_id TEXT NOT NULL,
  anomaly_type TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL,
  primary_opportunity_id INTEGER REFERENCES opportunities(id) ON DELETE SET NULL,
  confidence REAL NOT NULL,
  severity_score REAL NOT NULL,
  commercial_score REAL NOT NULL,
  actionability_score REAL NOT NULL,
  evidence_json TEXT NOT NULL,
  block_json TEXT NOT NULL,
  next_action_json TEXT NOT NULL,
  opportunity_ids_json TEXT NOT NULL,
  source_ids_json TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'open',
  first_detected_at TEXT NOT NULL,
  last_detected_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_anomaly_severity ON anomaly_findings(severity_score DESC);
CREATE INDEX IF NOT EXISTS idx_anomaly_type ON anomaly_findings(anomaly_type, severity_score DESC);
CREATE INDEX IF NOT EXISTS idx_anomaly_state ON anomaly_findings(state, severity_score DESC);
CREATE TABLE IF NOT EXISTS research_tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fingerprint TEXT NOT NULL UNIQUE,
  anomaly_id INTEGER REFERENCES anomaly_findings(id) ON DELETE SET NULL,
  entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL,
  opportunity_id INTEGER REFERENCES opportunities(id) ON DELETE SET NULL,
  task_type TEXT NOT NULL,
  title TEXT NOT NULL,
  rationale TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_value TEXT NOT NULL,
  expected_relation_type TEXT,
  source_id TEXT,
  source_url TEXT,
  access_mode TEXT NOT NULL,
  estimated_effort TEXT NOT NULL,
  expected_uplift REAL NOT NULL,
  confidence REAL NOT NULL,
  priority_score REAL NOT NULL,
  resolves_blockers_json TEXT NOT NULL,
  prerequisites_json TEXT NOT NULL,
  block_json TEXT NOT NULL,
  params_json TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'pending',
  result_json TEXT,
  first_planned_at TEXT NOT NULL,
  last_planned_at TEXT NOT NULL,
  completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_research_priority ON research_tasks(state, priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_research_type ON research_tasks(task_type, state, priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_research_anomaly ON research_tasks(anomaly_id, priority_score DESC);
CREATE TABLE IF NOT EXISTS research_result_ingestions (
  task_id INTEGER PRIMARY KEY REFERENCES research_tasks(id) ON DELETE CASCADE,
  result_fingerprint TEXT NOT NULL,
  fact_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  error TEXT,
  ingested_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fingerprint TEXT NOT NULL UNIQUE,
  task_id INTEGER NOT NULL REFERENCES research_tasks(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL,
  fact_type TEXT NOT NULL,
  subject_entity_type TEXT NOT NULL,
  subject_canonical_key TEXT NOT NULL,
  subject_display_name TEXT NOT NULL,
  relation_type TEXT,
  object_entity_type TEXT,
  object_canonical_key TEXT,
  object_display_name TEXT,
  confidence REAL NOT NULL,
  evidence_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_research_facts_subject ON research_facts(subject_canonical_key,source_id);
CREATE INDEX IF NOT EXISTS idx_research_facts_object ON research_facts(object_canonical_key,source_id);
CREATE INDEX IF NOT EXISTS idx_research_facts_relation ON research_facts(relation_type,confidence DESC);
CREATE TABLE IF NOT EXISTS case_resolution_states (
  anomaly_id INTEGER PRIMARY KEY REFERENCES anomaly_findings(id) ON DELETE CASCADE,
  target_state TEXT NOT NULL,
  resolution_status TEXT NOT NULL,
  resolution_score REAL NOT NULL,
  evidence_score REAL NOT NULL,
  budget_total REAL NOT NULL,
  budget_spent REAL NOT NULL,
  budget_remaining REAL NOT NULL,
  next_task_id INTEGER REFERENCES research_tasks(id) ON DELETE SET NULL,
  next_task_evi REAL,
  satisfied_conditions_json TEXT NOT NULL,
  unresolved_conditions_json TEXT NOT NULL,
  hard_gates_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_case_resolution_status ON case_resolution_states(resolution_status,resolution_score DESC);
CREATE INDEX IF NOT EXISTS idx_case_resolution_next_task ON case_resolution_states(next_task_id);
CREATE TABLE IF NOT EXISTS case_task_priorities (
  anomaly_id INTEGER NOT NULL REFERENCES anomaly_findings(id) ON DELETE CASCADE,
  task_id INTEGER NOT NULL REFERENCES research_tasks(id) ON DELETE CASCADE,
  evi_score REAL NOT NULL,
  execution_cost REAL NOT NULL,
  rank INTEGER NOT NULL,
  eligible INTEGER NOT NULL DEFAULT 1,
  rationale_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(anomaly_id,task_id)
);
CREATE INDEX IF NOT EXISTS idx_case_task_evi ON case_task_priorities(anomaly_id,eligible,evi_score DESC);
CREATE TABLE IF NOT EXISTS case_economic_states (
  anomaly_id INTEGER PRIMARY KEY REFERENCES anomaly_findings(id) ON DELETE CASCADE,
  lane TEXT NOT NULL,
  economic_status TEXT NOT NULL,
  revenue_reference REAL,
  currency TEXT,
  revenue_basis TEXT NOT NULL,
  viability_probability REAL NOT NULL,
  time_to_value_days REAL NOT NULL,
  time_discount REAL NOT NULL,
  regulatory_factor REAL NOT NULL,
  expected_case_value REAL NOT NULL,
  recommended_research_budget REAL NOT NULL,
  best_task_id INTEGER REFERENCES research_tasks(id) ON DELETE SET NULL,
  best_task_economic_score REAL,
  assumptions_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_case_economic_value ON case_economic_states(expected_case_value DESC);
CREATE INDEX IF NOT EXISTS idx_case_economic_task ON case_economic_states(best_task_id);
CREATE TABLE IF NOT EXISTS case_task_economics (
  anomaly_id INTEGER NOT NULL REFERENCES anomaly_findings(id) ON DELETE CASCADE,
  task_id INTEGER NOT NULL REFERENCES research_tasks(id) ON DELETE CASCADE,
  resolve_probability REAL NOT NULL,
  research_cost REAL NOT NULL,
  time_discount REAL NOT NULL,
  expected_incremental_value REAL,
  economic_score REAL NOT NULL,
  eligible INTEGER NOT NULL DEFAULT 1,
  rationale_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(anomaly_id,task_id)
);
CREATE INDEX IF NOT EXISTS idx_case_task_economic ON case_task_economics(anomaly_id,eligible,economic_score DESC);
CREATE TABLE IF NOT EXISTS scheduler_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  status TEXT NOT NULL DEFAULT 'running',
  planning_cost_spent REAL NOT NULL DEFAULT 0,
  completed_tasks INTEGER NOT NULL DEFAULT 0,
  stop_reason TEXT,
  config_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scheduler_runs_status ON scheduler_runs(status,id DESC);
CREATE TABLE IF NOT EXISTS scheduler_steps (
  run_id INTEGER NOT NULL REFERENCES scheduler_runs(id) ON DELETE CASCADE,
  step_index INTEGER NOT NULL,
  anomaly_id INTEGER REFERENCES anomaly_findings(id) ON DELETE SET NULL,
  task_id INTEGER REFERENCES research_tasks(id) ON DELETE SET NULL,
  task_type TEXT NOT NULL,
  economic_score REAL NOT NULL DEFAULT 0,
  expected_case_value REAL NOT NULL DEFAULT 0,
  planning_cost REAL NOT NULL DEFAULT 0,
  state TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  PRIMARY KEY(run_id,step_index)
);
CREATE INDEX IF NOT EXISTS idx_scheduler_steps_run ON scheduler_steps(run_id,step_index);
CREATE TABLE IF NOT EXISTS source_sync_states (
  source_id TEXT PRIMARY KEY,
  mode TEXT NOT NULL,
  cadence_label TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  last_attempt_at TEXT,
  last_success_at TEXT,
  next_due_at TEXT,
  cursor TEXT,
  etag TEXT,
  last_modified TEXT,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  last_status TEXT NOT NULL DEFAULT 'never_run',
  last_error TEXT,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_source_sync_due ON source_sync_states(enabled,next_due_at);
CREATE TABLE IF NOT EXISTS source_sync_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id TEXT NOT NULL,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  status TEXT NOT NULL DEFAULT 'running',
  record_count INTEGER NOT NULL DEFAULT 0,
  new_count INTEGER NOT NULL DEFAULT 0,
  changed_count INTEGER NOT NULL DEFAULT 0,
  unchanged_count INTEGER NOT NULL DEFAULT 0,
  cursor_before TEXT,
  cursor_after TEXT,
  error TEXT,
  detail_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY(source_id) REFERENCES source_sync_states(source_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_source_sync_events_source ON source_sync_events(source_id,id DESC);
CREATE TABLE IF NOT EXISTS monetization_routes (
  target_type TEXT NOT NULL,
  target_id INTEGER NOT NULL,
  route_id TEXT NOT NULL,
  route_score REAL NOT NULL,
  revenue_model TEXT NOT NULL,
  prerequisites_json TEXT NOT NULL,
  prohibitions_json TEXT NOT NULL,
  reason_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(target_type,target_id)
);
CREATE INDEX IF NOT EXISTS idx_monetization_routes_route ON monetization_routes(route_id,route_score DESC);
CREATE TABLE IF NOT EXISTS source_candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  catalog_id TEXT NOT NULL,
  external_id TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  publisher TEXT,
  jurisdiction TEXT NOT NULL,
  landing_url TEXT,
  metadata_url TEXT,
  access_level TEXT,
  license TEXT,
  formats_json TEXT NOT NULL DEFAULT '[]',
  keywords_json TEXT NOT NULL DEFAULT '[]',
  modified_at TEXT,
  update_frequency TEXT,
  asset_density_score REAL NOT NULL DEFAULT 0,
  machine_readability_score REAL NOT NULL DEFAULT 0,
  access_score REAL NOT NULL DEFAULT 0,
  legal_reuse_score REAL NOT NULL DEFAULT 0,
  freshness_score REAL NOT NULL DEFAULT 0,
  novelty_score REAL NOT NULL DEFAULT 0,
  monetization_fit_score REAL NOT NULL DEFAULT 0,
  overall_score REAL NOT NULL DEFAULT 0,
  monetization_route TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'discovered',
  reason_json TEXT NOT NULL DEFAULT '[]',
  raw_json TEXT NOT NULL DEFAULT '{}',
  discovered_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(catalog_id, external_id)
);
CREATE INDEX IF NOT EXISTS idx_source_candidates_score ON source_candidates(state,overall_score DESC);
CREATE INDEX IF NOT EXISTS idx_source_candidates_route ON source_candidates(monetization_route,overall_score DESC);
CREATE INDEX IF NOT EXISTS idx_source_candidates_catalog ON source_candidates(catalog_id,overall_score DESC);
CREATE TABLE IF NOT EXISTS source_mining_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  status TEXT NOT NULL DEFAULT 'running',
  catalogs_json TEXT NOT NULL,
  queries_json TEXT NOT NULL,
  config_json TEXT NOT NULL,
  seen_count INTEGER NOT NULL DEFAULT 0,
  saved_count INTEGER NOT NULL DEFAULT 0,
  above_threshold_count INTEGER NOT NULL DEFAULT 0,
  errors_json TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_source_mining_runs_status ON source_mining_runs(status,id DESC);
CREATE TABLE IF NOT EXISTS portal_candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  canonical_url TEXT NOT NULL UNIQUE,
  host TEXT NOT NULL,
  portal_type TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0,
  connector_priority_score REAL NOT NULL DEFAULT 0,
  access_level TEXT NOT NULL DEFAULT 'unknown',
  state TEXT NOT NULL DEFAULT 'discovered',
  capabilities_json TEXT NOT NULL DEFAULT '[]',
  evidence_json TEXT NOT NULL DEFAULT '[]',
  connector_spec_json TEXT NOT NULL DEFAULT '{}',
  source_candidate_ids_json TEXT NOT NULL DEFAULT '[]',
  asset_signal_score REAL NOT NULL DEFAULT 0,
  discovered_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_portal_candidates_type ON portal_candidates(state,portal_type,connector_priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_portal_candidates_host ON portal_candidates(host);
CREATE TABLE IF NOT EXISTS portal_discovery_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  status TEXT NOT NULL DEFAULT 'running',
  seeds_json TEXT NOT NULL DEFAULT '[]',
  config_json TEXT NOT NULL DEFAULT '{}',
  probed_count INTEGER NOT NULL DEFAULT 0,
  saved_count INTEGER NOT NULL DEFAULT 0,
  errors_json TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_portal_discovery_runs_status ON portal_discovery_runs(status,id DESC);
"""


@dataclass(frozen=True)
class UpsertStats:
    total: int = 0
    new: int = 0
    changed: int = 0
    unchanged: int = 0


def _fingerprint(item: Opportunity) -> str:
    record = item.as_record()
    record.pop("ingested_at", None)
    record.pop("score", None)
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(source_runs)")}
            for name in ("new_count", "changed_count", "unchanged_count"):
                if name not in columns:
                    conn.execute(f"ALTER TABLE source_runs ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")
            conn.commit()

    def upsert(self, opportunities: Iterable[Opportunity]) -> int:
        return self.upsert_with_stats(opportunities).total

    def upsert_with_stats(self, opportunities: Iterable[Opportunity]) -> UpsertStats:
        self.init()
        total = new_count = changed_count = unchanged_count = 0
        sql = """
        INSERT INTO opportunities (
          source_id, external_id, asset_class, title, owner_name, jurisdiction, custodian,
          face_value, currency, published_at, claim_deadline, source_url, legal_model,
          status, compliance_status, score, notes, raw_json, ingested_at
        ) VALUES (
          :source_id, :external_id, :asset_class, :title, :owner_name, :jurisdiction, :custodian,
          :face_value, :currency, :published_at, :claim_deadline, :source_url, :legal_model,
          :status, :compliance_status, :score, :notes, :raw_json, :ingested_at
        )
        ON CONFLICT(source_id, external_id) DO UPDATE SET
          asset_class=excluded.asset_class,
          title=excluded.title,
          owner_name=excluded.owner_name,
          jurisdiction=excluded.jurisdiction,
          custodian=excluded.custodian,
          face_value=excluded.face_value,
          currency=excluded.currency,
          published_at=excluded.published_at,
          claim_deadline=excluded.claim_deadline,
          source_url=excluded.source_url,
          legal_model=excluded.legal_model,
          score=excluded.score,
          notes=excluded.notes,
          raw_json=excluded.raw_json,
          ingested_at=excluded.ingested_at
        """
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            for item in opportunities:
                fingerprint = _fingerprint(item)
                version = conn.execute(
                    "SELECT fingerprint FROM opportunity_versions WHERE source_id=? AND external_id=?",
                    (item.source_id, item.external_id),
                ).fetchone()
                if version is None:
                    new_count += 1
                    conn.execute(
                        "INSERT INTO opportunity_versions(source_id,external_id,fingerprint,first_seen_at,last_seen_at) VALUES(?,?,?,?,?)",
                        (item.source_id, item.external_id, fingerprint, now, now),
                    )
                elif version["fingerprint"] != fingerprint:
                    changed_count += 1
                    conn.execute(
                        "UPDATE opportunity_versions SET fingerprint=?,last_seen_at=?,last_changed_at=?,change_count=change_count+1 WHERE source_id=? AND external_id=?",
                        (fingerprint, now, now, item.source_id, item.external_id),
                    )
                else:
                    unchanged_count += 1
                    conn.execute(
                        "UPDATE opportunity_versions SET last_seen_at=? WHERE source_id=? AND external_id=?",
                        (now, item.source_id, item.external_id),
                    )

                record = item.as_record()
                record["raw_json"] = json.dumps(record.pop("raw"), ensure_ascii=False, default=str)
                conn.execute(sql, record)
                row = conn.execute(
                    "SELECT id FROM opportunities WHERE source_id=? AND external_id=?",
                    (item.source_id, item.external_id),
                ).fetchone()
                if row:
                    opportunity_id = int(row["id"])
                    conn.execute("DELETE FROM opportunity_keys WHERE opportunity_id=?", (opportunity_id,))
                    raw_text = json.dumps(item.raw or {}, ensure_ascii=False, default=str)
                    for key_type, key_value in set(extract_keys(
                        title=item.title, owner_name=item.owner_name, raw_text=raw_text
                    )):
                        conn.execute(
                            "INSERT OR IGNORE INTO opportunity_keys(opportunity_id,key_type,key_value) VALUES(?,?,?)",
                            (opportunity_id, key_type, key_value),
                        )
                total += 1
            conn.commit()
        return UpsertStats(total=total, new=new_count, changed=changed_count, unchanged=unchanged_count)

    def list_opportunities(
        self,
        *,
        limit: int = 100,
        asset_class: str | None = None,
        jurisdiction: str | None = None,
        min_score: float | None = None,
    ) -> list[sqlite3.Row]:
        self.init()
        where: list[str] = []
        params: list[object] = []
        if asset_class:
            where.append("asset_class = ?")
            params.append(asset_class)
        if jurisdiction:
            where.append("jurisdiction = ?")
            params.append(jurisdiction)
        if min_score is not None:
            where.append("score >= ?")
            params.append(min_score)
        clause = " WHERE " + " AND ".join(where) if where else ""
        sql = f"SELECT * FROM opportunities{clause} ORDER BY score DESC, id DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            return list(conn.execute(sql, params))
    def begin_run(self, source_id: str) -> int:
        self.init()
        started_at = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO source_runs(source_id,started_at,status) VALUES(?,?,?)",
                (source_id, started_at, "running"),
            )
            conn.commit()
            return int(cur.lastrowid)

    def finish_run(self, run_id: int, *, record_count: int = 0, new_count: int = 0, changed_count: int = 0, unchanged_count: int = 0, error: str | None = None) -> None:
        self.init()
        completed_at = datetime.now(timezone.utc).isoformat()
        status = "failed" if error else "completed"
        with self.connect() as conn:
            conn.execute(
                "UPDATE source_runs SET completed_at=?,status=?,record_count=?,new_count=?,changed_count=?,unchanged_count=?,error=? WHERE id=?",
                (completed_at, status, record_count, new_count, changed_count, unchanged_count, error, run_id),
            )
            conn.commit()

    def list_runs(self, *, limit: int = 100) -> list[sqlite3.Row]:
        self.init()
        with self.connect() as conn:
            return list(conn.execute(
                "SELECT * FROM source_runs ORDER BY id DESC LIMIT ?", (limit,)
            ))

    def recent_changes(self, *, limit: int = 100) -> list[sqlite3.Row]:
        self.init()
        sql = """
        SELECT v.source_id, v.external_id, v.first_seen_at, v.last_seen_at,
               v.last_changed_at, v.change_count, o.asset_class, o.title, o.jurisdiction,
               o.source_url, o.score, o.compliance_status
        FROM opportunity_versions v
        JOIN opportunities o ON o.source_id=v.source_id AND o.external_id=v.external_id
        WHERE v.last_changed_at IS NOT NULL
        ORDER BY v.last_changed_at DESC
        LIMIT ?
        """
        with self.connect() as conn:
            return list(conn.execute(sql, (limit,)))

    def collisions(self, *, limit: int = 100) -> list[sqlite3.Row]:
        self.init()
        sql = """
        SELECT k.key_type, k.key_value, COUNT(DISTINCT o.source_id) AS source_count,
               COUNT(*) AS record_count, GROUP_CONCAT(DISTINCT o.source_id) AS sources
        FROM opportunity_keys k
        JOIN opportunities o ON o.id = k.opportunity_id
        GROUP BY k.key_type, k.key_value
        HAVING COUNT(DISTINCT o.source_id) > 1
        ORDER BY source_count DESC, record_count DESC
        LIMIT ?
        """
        with self.connect() as conn:
            return list(conn.execute(sql, (limit,)))

    def list_entities(self, *, limit: int = 100, min_sources: int = 1, entity_type: str | None = None) -> list[sqlite3.Row]:
        self.init()
        where = ["1=1"]
        params: list[object] = []
        if entity_type:
            where.append("e.entity_type=?")
            params.append(entity_type)
        params.extend([min_sources, limit])
        sql = f"""
        SELECT e.id,e.entity_type,e.canonical_key,e.display_name,e.confidence,
               COUNT(DISTINCT m.opportunity_id) AS opportunity_count,
               COUNT(DISTINCT o.source_id) AS source_count,
               GROUP_CONCAT(DISTINCT o.source_id) AS sources,
               MAX(o.score) AS max_opportunity_score
        FROM entities e
        LEFT JOIN entity_memberships m ON m.entity_id=e.id
        LEFT JOIN opportunities o ON o.id=m.opportunity_id
        WHERE {' AND '.join(where)}
        GROUP BY e.id
        HAVING COUNT(DISTINCT o.source_id) >= ?
        ORDER BY source_count DESC,max_opportunity_score DESC,e.confidence DESC,e.id DESC
        LIMIT ?
        """
        with self.connect() as conn:
            return list(conn.execute(sql, params))

    def list_entity_relations(
        self, *, limit: int = 100, relation_type: str | None = None, min_confidence: float = 0
    ) -> list[sqlite3.Row]:
        self.init()
        where = ["r.confidence >= ?"]
        params: list[object] = [min_confidence]
        if relation_type:
            where.append("r.relation_type=?")
            params.append(relation_type)
        params.append(limit)
        sql = f"""
        SELECT r.id,r.relation_type,r.confidence,r.evidence_json,
               l.id AS left_id,l.entity_type AS left_type,l.display_name AS left_name,
               rr.id AS right_id,rr.entity_type AS right_type,rr.display_name AS right_name
        FROM entity_relations r
        JOIN entities l ON l.id=r.left_entity_id
        JOIN entities rr ON rr.id=r.right_entity_id
        WHERE {' AND '.join(where)}
        ORDER BY r.confidence DESC,r.id DESC
        LIMIT ?
        """
        with self.connect() as conn:
            return list(conn.execute(sql, params))

    def entity_graph(self, entity_id: int) -> dict[str, object] | None:
        self.init()
        with self.connect() as conn:
            entity = conn.execute("SELECT * FROM entities WHERE id=?", (entity_id,)).fetchone()
            if entity is None:
                return None
            memberships = list(conn.execute(
                """
                SELECT m.role,m.match_method,m.confidence,m.evidence_json,
                       o.id AS opportunity_id,o.source_id,o.external_id,o.asset_class,o.title,
                       o.owner_name,o.jurisdiction,o.source_url,o.score,o.compliance_status
                FROM entity_memberships m JOIN opportunities o ON o.id=m.opportunity_id
                WHERE m.entity_id=? ORDER BY o.score DESC,o.id DESC
                """,
                (entity_id,),
            ))
            relations = list(conn.execute(
                """
                SELECT r.relation_type,r.confidence,r.evidence_json,
                       CASE WHEN r.left_entity_id=? THEN rr.id ELSE l.id END AS other_id,
                       CASE WHEN r.left_entity_id=? THEN rr.entity_type ELSE l.entity_type END AS other_type,
                       CASE WHEN r.left_entity_id=? THEN rr.display_name ELSE l.display_name END AS other_name
                FROM entity_relations r
                JOIN entities l ON l.id=r.left_entity_id
                JOIN entities rr ON rr.id=r.right_entity_id
                WHERE r.left_entity_id=? OR r.right_entity_id=?
                ORDER BY r.confidence DESC,r.id DESC
                """,
                (entity_id, entity_id, entity_id, entity_id, entity_id),
            ))
            return {
                "entity": dict(entity),
                "memberships": [dict(row) for row in memberships],
                "relations": [dict(row) for row in relations],
            }

    def list_commercial_assessments(
        self, *, limit: int = 100, min_score: float = 0, lane: str | None = None, jurisdiction: str | None = None
    ) -> list[sqlite3.Row]:
        self.init()
        where = ["c.commercial_score >= ?"]
        params: list[object] = [min_score]
        if lane:
            where.append("c.lane=?")
            params.append(lane)
        if jurisdiction:
            where.append("o.jurisdiction=?")
            params.append(jurisdiction)
        params.append(limit)
        sql = f"""
        SELECT o.id AS opportunity_id,o.source_id,o.external_id,o.asset_class,o.title,o.owner_name,
               o.jurisdiction,o.custodian,o.face_value,o.currency,o.source_url,o.legal_model,
               o.compliance_status,o.score AS discovery_score,c.*
        FROM commercial_assessments c JOIN opportunities o ON o.id=c.opportunity_id
        WHERE {' AND '.join(where)}
        ORDER BY c.actionability_score DESC,c.commercial_score DESC,o.id DESC LIMIT ?
        """
        with self.connect() as conn:
            return list(conn.execute(sql, params))

    def commercial_case(self, opportunity_id: int) -> dict[str, object] | None:
        self.init()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT o.*,c.lane,c.commercial_score,c.actionability_score,c.evidence_confidence,
                       c.independent_source_count,c.value_score,c.identity_score,c.cross_source_score,
                       c.recoverability_score,c.time_to_money_score,c.regulatory_friction_score,
                       c.acquisition_score,c.fee_cap_percent,c.gross_fee_ceiling,c.reason_json,
                       c.block_json,c.next_action_json,c.updated_at AS assessed_at
                FROM opportunities o JOIN commercial_assessments c ON c.opportunity_id=o.id
                WHERE o.id=?
                """,
                (opportunity_id,),
            ).fetchone()
            if row is None:
                return None
            entities = list(conn.execute(
                """
                SELECT e.id,e.entity_type,e.display_name,e.confidence,m.role,m.match_method,m.confidence AS membership_confidence
                FROM entity_memberships m JOIN entities e ON e.id=m.entity_id
                WHERE m.opportunity_id=? ORDER BY m.confidence DESC,e.id
                """,
                (opportunity_id,),
            ))
            result = dict(row)
            for key in ("reason_json", "block_json", "next_action_json"):
                result[key[:-5] if key.endswith('_json') else key] = json.loads(result.pop(key))
            result["entities"] = [dict(r) for r in entities]
            return result

    def list_entity_commercial_summaries(
        self, *, limit: int = 100, min_score: float = 0, min_sources: int = 1
    ) -> list[sqlite3.Row]:
        self.init()
        sql = """
        SELECT e.id AS entity_id,e.entity_type,e.display_name,e.confidence,
               s.commercial_score,s.actionability_score,s.primary_lane,s.opportunity_count,s.source_count,
               s.asset_classes_json,s.jurisdictions_json,s.value_by_currency_json,
               s.fee_ceiling_by_currency_json,s.lane_mix_json,s.updated_at
        FROM entity_commercial_summaries s JOIN entities e ON e.id=s.entity_id
        WHERE s.commercial_score>=? AND s.source_count>=?
        ORDER BY s.actionability_score DESC,s.commercial_score DESC,s.source_count DESC,e.id DESC
        LIMIT ?
        """
        with self.connect() as conn:
            return list(conn.execute(sql, (min_score, min_sources, limit)))

    def list_anomalies(
        self,
        *,
        limit: int = 100,
        min_severity: float = 0,
        anomaly_type: str | None = None,
        state: str | None = "open",
    ) -> list[sqlite3.Row]:
        self.init()
        where = ["severity_score >= ?"]
        params: list[object] = [min_severity]
        if anomaly_type:
            where.append("anomaly_type=?")
            params.append(anomaly_type)
        if state:
            where.append("state=?")
            params.append(state)
        params.append(limit)
        sql = f"""
        SELECT id,fingerprint,rule_id,anomaly_type,title,summary,entity_id,primary_opportunity_id,
               confidence,severity_score,commercial_score,actionability_score,state,
               source_ids_json,opportunity_ids_json,first_detected_at,last_detected_at
        FROM anomaly_findings
        WHERE {' AND '.join(where)}
        ORDER BY severity_score DESC,commercial_score DESC,confidence DESC,id DESC
        LIMIT ?
        """
        with self.connect() as conn:
            return list(conn.execute(sql, params))

    def anomaly_case(self, anomaly_id: int) -> dict[str, object] | None:
        self.init()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM anomaly_findings WHERE id=?", (anomaly_id,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            for key, out_key in (
                ("evidence_json", "evidence"),
                ("block_json", "blocks"),
                ("next_action_json", "next_actions"),
                ("opportunity_ids_json", "opportunity_ids"),
                ("source_ids_json", "source_ids"),
            ):
                try:
                    result[out_key] = json.loads(result.pop(key))
                except (json.JSONDecodeError, TypeError):
                    result[out_key] = []
            if result.get("entity_id"):
                result["entity"] = self.entity_graph(int(result["entity_id"]))
            return result

    def set_anomaly_state(self, anomaly_id: int, state: str) -> bool:
        if state not in {"open", "dismissed", "confirmed", "stale"}:
            raise ValueError("state must be one of: open, dismissed, confirmed, stale")
        self.init()
        with self.connect() as conn:
            cur = conn.execute("UPDATE anomaly_findings SET state=? WHERE id=?", (state, anomaly_id))
            conn.commit()
            return cur.rowcount > 0

    def list_research_tasks(
        self, *, limit: int = 100, min_priority: float = 0, task_type: str | None = None,
        state: str | None = "pending", anomaly_id: int | None = None
    ) -> list[sqlite3.Row]:
        self.init()
        where = ["priority_score >= ?"]
        params: list[object] = [min_priority]
        if task_type:
            where.append("task_type=?")
            params.append(task_type)
        if state:
            where.append("state=?")
            params.append(state)
        if anomaly_id is not None:
            where.append("anomaly_id=?")
            params.append(anomaly_id)
        params.append(limit)
        sql = f"""
        SELECT id,anomaly_id,entity_id,opportunity_id,task_type,title,target_type,target_value,
               expected_relation_type,source_id,source_url,access_mode,estimated_effort,expected_uplift,
               confidence,priority_score,state,first_planned_at,last_planned_at,completed_at
        FROM research_tasks WHERE {' AND '.join(where)}
        ORDER BY priority_score DESC,expected_uplift DESC,id ASC LIMIT ?
        """
        with self.connect() as conn:
            return list(conn.execute(sql, params))

    def research_task_case(self, task_id: int) -> dict[str, object] | None:
        self.init()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM research_tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            for key, out_key, default in (
                ("resolves_blockers_json", "resolves_blockers", []),
                ("prerequisites_json", "prerequisites", []),
                ("block_json", "blocks", []),
                ("params_json", "params", {}),
                ("result_json", "result", None),
            ):
                value = result.pop(key, None)
                if value in (None, ""):
                    result[out_key] = default
                    continue
                try:
                    result[out_key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    result[out_key] = value
            if result.get("anomaly_id"):
                anomaly = conn.execute(
                    "SELECT id,anomaly_type,title,severity_score,commercial_score,actionability_score,state FROM anomaly_findings WHERE id=?",
                    (int(result["anomaly_id"]),),
                ).fetchone()
                result["anomaly"] = dict(anomaly) if anomaly else None
            return result

    def set_research_task_state(self, task_id: int, state: str) -> bool:
        if state not in {"pending", "in_progress", "completed", "dismissed", "blocked", "stale"}:
            raise ValueError("state must be one of: pending, in_progress, completed, dismissed, blocked, stale")
        self.init()
        completed_at = datetime.now(timezone.utc).isoformat() if state == "completed" else None
        with self.connect() as conn:
            cur = conn.execute(
                "UPDATE research_tasks SET state=?, completed_at=CASE WHEN ? IS NOT NULL THEN ? ELSE completed_at END WHERE id=?",
                (state, completed_at, completed_at, task_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def complete_research_task(self, task_id: int, *, result: object) -> bool:
        self.init()
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            cur = conn.execute(
                "UPDATE research_tasks SET state='completed', result_json=?, completed_at=? WHERE id=?",
                (json.dumps(result, ensure_ascii=False, sort_keys=True, default=str), now, task_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def research_task_counts(self) -> dict[str, int]:
        self.init()
        with self.connect() as conn:
            rows = conn.execute("SELECT state,COUNT(*) AS n FROM research_tasks GROUP BY state")
            return {str(r["state"]): int(r["n"]) for r in rows}


    def list_research_facts(
        self, *, limit: int = 100, source_id: str | None = None,
        relation_type: str | None = None, task_id: int | None = None
    ) -> list[sqlite3.Row]:
        self.init()
        where = ["1=1"]
        params: list[object] = []
        if source_id:
            where.append("source_id=?")
            params.append(source_id)
        if relation_type:
            where.append("relation_type=?")
            params.append(relation_type)
        if task_id is not None:
            where.append("task_id=?")
            params.append(task_id)
        params.append(limit)
        sql = f"""
        SELECT id,task_id,source_id,fact_type,subject_entity_type,subject_canonical_key,
               subject_display_name,relation_type,object_entity_type,object_canonical_key,
               object_display_name,confidence,evidence_json,created_at
        FROM research_facts WHERE {' AND '.join(where)}
        ORDER BY confidence DESC,id DESC LIMIT ?
        """
        with self.connect() as conn:
            return list(conn.execute(sql, params))

    def list_research_result_ingestions(self, *, limit: int = 100) -> list[sqlite3.Row]:
        self.init()
        with self.connect() as conn:
            return list(conn.execute(
                """
                SELECT r.task_id,t.task_type,t.title,r.result_fingerprint,r.fact_count,
                       r.status,r.error,r.ingested_at
                FROM research_result_ingestions r
                JOIN research_tasks t ON t.id=r.task_id
                ORDER BY r.ingested_at DESC,r.task_id DESC LIMIT ?
                """,
                (limit,),
            ))
    def list_case_resolutions(
        self, *, limit: int = 100, status: str | None = None, min_resolution: float = 0
    ) -> list[sqlite3.Row]:
        self.init()
        where = ["c.resolution_score >= ?"]
        params: list[object] = [min_resolution]
        if status:
            where.append("c.resolution_status=?")
            params.append(status)
        params.append(limit)
        sql = f"""
        SELECT c.*,a.anomaly_type,a.title,a.severity_score,a.commercial_score,a.actionability_score,a.state AS anomaly_state,
               t.task_type AS next_task_type,t.title AS next_task_title,t.access_mode AS next_task_access
        FROM case_resolution_states c
        JOIN anomaly_findings a ON a.id=c.anomaly_id
        LEFT JOIN research_tasks t ON t.id=c.next_task_id
        WHERE {' AND '.join(where)}
        ORDER BY c.resolution_score DESC,COALESCE(c.next_task_evi,0) DESC,a.severity_score DESC
        LIMIT ?
        """
        with self.connect() as conn:
            return list(conn.execute(sql, params))

    def case_resolution(self, anomaly_id: int) -> dict[str, object] | None:
        self.init()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT c.*,a.anomaly_type,a.title,a.summary,a.severity_score,a.commercial_score,
                       a.actionability_score,a.confidence,a.state AS anomaly_state
                FROM case_resolution_states c JOIN anomaly_findings a ON a.id=c.anomaly_id
                WHERE c.anomaly_id=?
                """,
                (anomaly_id,),
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            for key,out_key in (
                ("satisfied_conditions_json","satisfied_conditions"),
                ("unresolved_conditions_json","unresolved_conditions"),
                ("hard_gates_json","hard_gates"),
            ):
                try:
                    result[out_key] = json.loads(result.pop(key))
                except (json.JSONDecodeError,TypeError):
                    result[out_key] = []
            priorities = []
            for p in conn.execute(
                """
                SELECT p.*,t.task_type,t.title,t.access_mode,t.estimated_effort,t.state AS task_state
                FROM case_task_priorities p JOIN research_tasks t ON t.id=p.task_id
                WHERE p.anomaly_id=? ORDER BY p.rank ASC
                """,
                (anomaly_id,),
            ):
                item = dict(p)
                try:
                    item["rationale"] = json.loads(item.pop("rationale_json"))
                except (json.JSONDecodeError,TypeError):
                    item["rationale"] = {}
                item["eligible"] = bool(item["eligible"])
                priorities.append(item)
            result["task_priorities"] = priorities
            return result

    def list_case_economics(
        self, *, limit: int = 100, min_expected_value: float = 0, status: str | None = None
    ) -> list[sqlite3.Row]:
        self.init()
        where = ["e.expected_case_value >= ?"]
        params: list[object] = [min_expected_value]
        if status:
            where.append("e.economic_status=?")
            params.append(status)
        params.append(limit)
        sql = f"""
        SELECT e.*,a.anomaly_type,a.title,a.severity_score,a.commercial_score,a.actionability_score,
               c.resolution_status,c.resolution_score,t.task_type AS best_task_type,t.title AS best_task_title
        FROM case_economic_states e
        JOIN anomaly_findings a ON a.id=e.anomaly_id
        JOIN case_resolution_states c ON c.anomaly_id=e.anomaly_id
        LEFT JOIN research_tasks t ON t.id=e.best_task_id
        WHERE {' AND '.join(where)}
        ORDER BY e.expected_case_value DESC,COALESCE(e.best_task_economic_score,0) DESC,a.severity_score DESC
        LIMIT ?
        """
        with self.connect() as conn:
            return list(conn.execute(sql, params))

    def case_economics(self, anomaly_id: int) -> dict[str, object] | None:
        self.init()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT e.*,a.anomaly_type,a.title,a.summary,a.severity_score,a.commercial_score,
                       a.actionability_score,c.resolution_status,c.resolution_score,c.hard_gates_json
                FROM case_economic_states e
                JOIN anomaly_findings a ON a.id=e.anomaly_id
                JOIN case_resolution_states c ON c.anomaly_id=e.anomaly_id
                WHERE e.anomaly_id=?
                """,
                (anomaly_id,),
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            try:
                result["assumptions"] = json.loads(result.pop("assumptions_json"))
            except (json.JSONDecodeError, TypeError):
                result["assumptions"] = {}
            try:
                result["hard_gates"] = json.loads(result.pop("hard_gates_json"))
            except (json.JSONDecodeError, TypeError):
                result["hard_gates"] = []
            tasks=[]
            for t in conn.execute(
                """
                SELECT e.*,r.task_type,r.title,r.access_mode,r.estimated_effort,r.state AS task_state
                FROM case_task_economics e JOIN research_tasks r ON r.id=e.task_id
                WHERE e.anomaly_id=? ORDER BY e.economic_score DESC,r.id
                """,
                (anomaly_id,),
            ):
                item=dict(t)
                item["eligible"]=bool(item["eligible"])
                try:
                    item["rationale"]=json.loads(item.pop("rationale_json"))
                except (json.JSONDecodeError,TypeError):
                    item["rationale"]={}
                tasks.append(item)
            result["task_economics"]=tasks
            return result

    def next_economic_task(self, anomaly_id: int) -> dict[str, object] | None:
        self.init()
        with self.connect() as conn:
            row=conn.execute(
                """
                SELECT e.anomaly_id,e.revenue_reference,e.currency,e.revenue_basis,e.expected_case_value,
                       e.recommended_research_budget,e.best_task_economic_score,te.resolve_probability,
                       te.research_cost,te.expected_incremental_value,t.*
                FROM case_economic_states e
                JOIN research_tasks t ON t.id=e.best_task_id
                JOIN case_task_economics te ON te.anomaly_id=e.anomaly_id AND te.task_id=t.id
                WHERE e.anomaly_id=?
                """,
                (anomaly_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    def next_case_task(self, anomaly_id: int) -> dict[str, object] | None:
        self.init()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT c.anomaly_id,c.next_task_evi,c.budget_remaining,t.*
                FROM case_resolution_states c JOIN research_tasks t ON t.id=c.next_task_id
                WHERE c.anomaly_id=?
                """,
                (anomaly_id,),
            ).fetchone()
            if row is None:
                return None
            return dict(row)

    def begin_scheduler_run(self, config: dict[str, object]) -> int:
        self.init()
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO scheduler_runs(started_at,status,config_json) VALUES(?,'running',?)",
                (now, json.dumps(config, sort_keys=True, default=str)),
            )
            conn.commit()
            return int(cur.lastrowid)

    def finish_scheduler_run(
        self, run_id: int, *, status: str, planning_cost_spent: float,
        completed_tasks: int, stop_reason: str
    ) -> None:
        self.init()
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                """UPDATE scheduler_runs SET completed_at=?,status=?,planning_cost_spent=?,
                   completed_tasks=?,stop_reason=? WHERE id=?""",
                (now, status, planning_cost_spent, completed_tasks, stop_reason, run_id),
            )
            conn.commit()

    def add_scheduler_step(
        self, *, run_id: int, step_index: int, anomaly_id: int | None, task_id: int | None,
        task_type: str, economic_score: float, expected_case_value: float,
        planning_cost: float, state: str, detail: dict[str, object]
    ) -> None:
        self.init()
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO scheduler_steps(
                   run_id,step_index,anomaly_id,task_id,task_type,economic_score,
                   expected_case_value,planning_cost,state,detail_json,started_at,completed_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,NULL)""",
                (run_id, step_index, anomaly_id, task_id, task_type, economic_score,
                 expected_case_value, planning_cost, state,
                 json.dumps(detail, sort_keys=True, default=str), now),
            )
            conn.commit()

    def finish_scheduler_step(
        self, *, run_id: int, step_index: int, state: str, detail: dict[str, object]
    ) -> None:
        self.init()
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                "UPDATE scheduler_steps SET state=?,detail_json=?,completed_at=? WHERE run_id=? AND step_index=?",
                (state, json.dumps(detail, sort_keys=True, default=str), now, run_id, step_index),
            )
            conn.commit()

    def list_scheduler_runs(self, *, limit: int = 100) -> list[sqlite3.Row]:
        self.init()
        with self.connect() as conn:
            return list(conn.execute(
                "SELECT * FROM scheduler_runs ORDER BY id DESC LIMIT ?", (limit,)
            ))

    def scheduler_run(self, run_id: int) -> dict[str, object] | None:
        self.init()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM scheduler_runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            try:
                result["config"] = json.loads(result.pop("config_json"))
            except (json.JSONDecodeError, TypeError):
                result["config"] = {}
            steps=[]
            for step in conn.execute(
                "SELECT * FROM scheduler_steps WHERE run_id=? ORDER BY step_index", (run_id,)
            ):
                item=dict(step)
                try:
                    item["detail"] = json.loads(item.pop("detail_json"))
                except (json.JSONDecodeError, TypeError):
                    item["detail"]={}
                steps.append(item)
            result["steps"] = steps
            return result

    def list_scheduler_steps(self, *, limit: int = 100, run_id: int | None = None) -> list[sqlite3.Row]:
        self.init()
        with self.connect() as conn:
            if run_id is None:
                return list(conn.execute(
                    "SELECT * FROM scheduler_steps ORDER BY run_id DESC,step_index DESC LIMIT ?", (limit,)
                ))
            return list(conn.execute(
                "SELECT * FROM scheduler_steps WHERE run_id=? ORDER BY step_index LIMIT ?", (run_id,limit)
            ))



    def ensure_source_sync_state(self, source_id: str, *, mode: str, cadence_label: str, enabled: bool = True) -> None:
        self.init()
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO source_sync_states(source_id,mode,cadence_label,enabled,updated_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(source_id) DO UPDATE SET mode=excluded.mode,cadence_label=excluded.cadence_label,
                   enabled=excluded.enabled,updated_at=excluded.updated_at""",
                (source_id, mode, cadence_label, 1 if enabled else 0, now),
            )
            conn.commit()

    def source_sync_state(self, source_id: str) -> dict[str, object] | None:
        self.init()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM source_sync_states WHERE source_id=?", (source_id,)).fetchone()
            return dict(row) if row is not None else None

    def begin_source_sync_event(self, source_id: str, *, cursor_before: str | None = None, detail: dict[str, object] | None = None) -> int:
        self.init()
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                "UPDATE source_sync_states SET last_attempt_at=?,last_status='running',updated_at=? WHERE source_id=?",
                (now, now, source_id),
            )
            cur = conn.execute(
                """INSERT INTO source_sync_events(source_id,started_at,status,cursor_before,detail_json)
                   VALUES(?,?,'running',?,?)""",
                (source_id, now, cursor_before, json.dumps(detail or {}, sort_keys=True, default=str)),
            )
            conn.commit()
            return int(cur.lastrowid)

    def finish_source_sync_event(
        self, event_id: int, *, status: str, record_count: int = 0, new_count: int = 0,
        changed_count: int = 0, unchanged_count: int = 0, cursor_after: str | None = None,
        next_due_at: str | None = None, error: str | None = None, detail: dict[str, object] | None = None
    ) -> None:
        self.init()
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            row = conn.execute("SELECT source_id FROM source_sync_events WHERE id=?", (event_id,)).fetchone()
            if row is None:
                raise ValueError(f"Unknown source sync event: {event_id}")
            source_id = str(row['source_id'])
            conn.execute(
                """UPDATE source_sync_events SET completed_at=?,status=?,record_count=?,new_count=?,changed_count=?,
                   unchanged_count=?,cursor_after=?,error=?,detail_json=? WHERE id=?""",
                (now, status, record_count, new_count, changed_count, unchanged_count, cursor_after, error,
                 json.dumps(detail or {}, sort_keys=True, default=str), event_id),
            )
            if status == 'completed':
                conn.execute(
                    """UPDATE source_sync_states SET last_success_at=?,next_due_at=?,cursor=COALESCE(?,cursor),
                       consecutive_failures=0,last_status='completed',last_error=NULL,updated_at=? WHERE source_id=?""",
                    (now, next_due_at, cursor_after, now, source_id),
                )
            else:
                conn.execute(
                    """UPDATE source_sync_states SET next_due_at=?,consecutive_failures=consecutive_failures+1,
                       last_status=?,last_error=?,updated_at=? WHERE source_id=?""",
                    (next_due_at, status, error, now, source_id),
                )
            conn.commit()

    def list_monetization_routes(
        self, *, limit: int = 100, route_id: str | None = None, target_type: str | None = None,
        min_score: float = 0.0
    ) -> list[sqlite3.Row]:
        self.init()
        sql = "SELECT * FROM monetization_routes WHERE route_score>=?"
        args: list[object] = [min_score]
        if route_id:
            sql += " AND route_id=?"
            args.append(route_id)
        if target_type:
            sql += " AND target_type=?"
            args.append(target_type)
        sql += " ORDER BY route_score DESC,target_type,target_id LIMIT ?"
        args.append(limit)
        with self.connect() as conn:
            return list(conn.execute(sql, tuple(args)))

    def monetization_route(self, target_type: str, target_id: int) -> dict[str, object] | None:
        self.init()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM monetization_routes WHERE target_type=? AND target_id=?",
                (target_type, target_id),
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            for key in ("prerequisites_json", "prohibitions_json", "reason_json"):
                out = key.replace("_json", "")
                try:
                    result[out] = json.loads(result.pop(key))
                except (json.JSONDecodeError, TypeError):
                    result[out] = []
            if target_type == "opportunity":
                source = conn.execute(
                    "SELECT * FROM opportunities WHERE id=?", (target_id,)
                ).fetchone()
            else:
                source = conn.execute(
                    "SELECT * FROM anomaly_findings WHERE id=?", (target_id,)
                ).fetchone()
            result["target"] = dict(source) if source is not None else None
            return result

    def list_source_sync_states(self, *, limit: int = 100) -> list[sqlite3.Row]:
        self.init()
        with self.connect() as conn:
            return list(conn.execute(
                "SELECT * FROM source_sync_states ORDER BY COALESCE(next_due_at,'') ASC,source_id LIMIT ?", (limit,)
            ))

    def list_source_sync_events(self, *, limit: int = 100, source_id: str | None = None) -> list[sqlite3.Row]:
        self.init()
        with self.connect() as conn:
            if source_id is None:
                return list(conn.execute(
                    "SELECT * FROM source_sync_events ORDER BY id DESC LIMIT ?", (limit,)
                ))
            return list(conn.execute(
                "SELECT * FROM source_sync_events WHERE source_id=? ORDER BY id DESC LIMIT ?",
                (source_id, limit),
            ))

    def upsert_source_candidates(self, candidates) -> int:
        self.init()
        now = datetime.now(timezone.utc).isoformat()
        count = 0
        sql = """
        INSERT INTO source_candidates (
          catalog_id,external_id,title,description,publisher,jurisdiction,landing_url,metadata_url,
          access_level,license,formats_json,keywords_json,modified_at,update_frequency,
          asset_density_score,machine_readability_score,access_score,legal_reuse_score,freshness_score,
          novelty_score,monetization_fit_score,overall_score,monetization_route,reason_json,raw_json,
          discovered_at,updated_at
        ) VALUES (
          :catalog_id,:external_id,:title,:description,:publisher,:jurisdiction,:landing_url,:metadata_url,
          :access_level,:license,:formats_json,:keywords_json,:modified_at,:update_frequency,
          :asset_density_score,:machine_readability_score,:access_score,:legal_reuse_score,:freshness_score,
          :novelty_score,:monetization_fit_score,:overall_score,:monetization_route,:reason_json,:raw_json,
          :discovered_at,:updated_at
        )
        ON CONFLICT(catalog_id,external_id) DO UPDATE SET
          title=excluded.title,description=excluded.description,publisher=excluded.publisher,
          jurisdiction=excluded.jurisdiction,landing_url=excluded.landing_url,metadata_url=excluded.metadata_url,
          access_level=excluded.access_level,license=excluded.license,formats_json=excluded.formats_json,
          keywords_json=excluded.keywords_json,modified_at=excluded.modified_at,update_frequency=excluded.update_frequency,
          asset_density_score=excluded.asset_density_score,machine_readability_score=excluded.machine_readability_score,
          access_score=excluded.access_score,legal_reuse_score=excluded.legal_reuse_score,
          freshness_score=excluded.freshness_score,novelty_score=excluded.novelty_score,
          monetization_fit_score=excluded.monetization_fit_score,overall_score=excluded.overall_score,
          monetization_route=excluded.monetization_route,reason_json=excluded.reason_json,raw_json=excluded.raw_json,
          updated_at=excluded.updated_at
        """
        with self.connect() as conn:
            for candidate in candidates:
                record = candidate.as_record() if hasattr(candidate, 'as_record') else dict(candidate)
                record['discovered_at'] = now
                record['updated_at'] = now
                conn.execute(sql, record)
                count += 1
            conn.commit()
        return count

    def list_source_candidates(
        self, *, limit: int = 100, min_score: float = 0, catalog_id: str | None = None,
        route: str | None = None, state: str | None = 'discovered'
    ) -> list[sqlite3.Row]:
        self.init()
        where = ['overall_score>=?']
        args: list[object] = [min_score]
        if catalog_id:
            where.append('catalog_id=?')
            args.append(catalog_id)
        if route:
            where.append('monetization_route=?')
            args.append(route)
        if state:
            where.append('state=?')
            args.append(state)
        args.append(limit)
        sql = f"SELECT * FROM source_candidates WHERE {' AND '.join(where)} ORDER BY overall_score DESC,id DESC LIMIT ?"
        with self.connect() as conn:
            return list(conn.execute(sql, tuple(args)))

    def source_candidate(self, candidate_id: int) -> dict[str, object] | None:
        self.init()
        with self.connect() as conn:
            row = conn.execute('SELECT * FROM source_candidates WHERE id=?', (candidate_id,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            for key in ('formats_json','keywords_json','reason_json','raw_json'):
                try:
                    result[key.replace('_json','')] = json.loads(result.pop(key))
                except (json.JSONDecodeError, TypeError):
                    result[key.replace('_json','')] = [] if key != 'raw_json' else {}
            return result

    def set_source_candidate_state(self, candidate_id: int, state: str) -> bool:
        allowed = {'discovered','approved','rejected','watch','archived'}
        if state not in allowed:
            raise ValueError(f"state must be one of: {', '.join(sorted(allowed))}")
        self.init()
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            cur = conn.execute('UPDATE source_candidates SET state=?,updated_at=? WHERE id=?', (state,now,candidate_id))
            conn.commit()
            return cur.rowcount > 0

    def begin_source_mining_run(self, *, catalogs, queries, config) -> int:
        self.init()
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO source_mining_runs(started_at,catalogs_json,queries_json,config_json) VALUES(?,?,?,?)",
                (now,json.dumps(list(catalogs)),json.dumps(list(queries)),json.dumps(config,sort_keys=True,default=str)),
            )
            conn.commit()
            return int(cur.lastrowid)

    def finish_source_mining_run(
        self, run_id: int, *, status: str, seen_count: int, saved_count: int,
        above_threshold_count: int, errors
    ) -> None:
        self.init()
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                """UPDATE source_mining_runs SET completed_at=?,status=?,seen_count=?,saved_count=?,
                   above_threshold_count=?,errors_json=? WHERE id=?""",
                (now,status,seen_count,saved_count,above_threshold_count,json.dumps(list(errors),sort_keys=True),run_id),
            )
            conn.commit()

    def list_source_mining_runs(self, *, limit: int = 100) -> list[sqlite3.Row]:
        self.init()
        with self.connect() as conn:
            return list(conn.execute('SELECT * FROM source_mining_runs ORDER BY id DESC LIMIT ?', (limit,)))

    def upsert_portal_candidates(self, candidates) -> int:
        self.init()
        now = datetime.now(timezone.utc).isoformat()
        sql = """
        INSERT INTO portal_candidates (
          canonical_url,host,portal_type,confidence,connector_priority_score,access_level,
          capabilities_json,evidence_json,connector_spec_json,source_candidate_ids_json,asset_signal_score,
          discovered_at,updated_at
        ) VALUES (
          :canonical_url,:host,:portal_type,:confidence,:connector_priority_score,:access_level,
          :capabilities_json,:evidence_json,:connector_spec_json,:source_candidate_ids_json,:asset_signal_score,
          :discovered_at,:updated_at
        )
        ON CONFLICT(canonical_url) DO UPDATE SET
          host=excluded.host,portal_type=excluded.portal_type,confidence=excluded.confidence,
          connector_priority_score=excluded.connector_priority_score,access_level=excluded.access_level,
          capabilities_json=excluded.capabilities_json,evidence_json=excluded.evidence_json,
          connector_spec_json=excluded.connector_spec_json,source_candidate_ids_json=excluded.source_candidate_ids_json,
          asset_signal_score=excluded.asset_signal_score,updated_at=excluded.updated_at
        """
        count = 0
        with self.connect() as conn:
            for candidate in candidates:
                record = candidate.as_record() if hasattr(candidate, 'as_record') else dict(candidate)
                record['discovered_at'] = now
                record['updated_at'] = now
                conn.execute(sql, record)
                count += 1
            conn.commit()
        return count

    def list_portal_candidates(
        self, *, limit: int = 100, min_score: float = 0, portal_type: str | None = None,
        state: str | None = 'discovered'
    ) -> list[sqlite3.Row]:
        self.init()
        where = ['connector_priority_score>=?']
        args: list[object] = [min_score]
        if portal_type:
            where.append('portal_type=?')
            args.append(portal_type)
        if state:
            where.append('state=?')
            args.append(state)
        args.append(limit)
        sql = f"SELECT * FROM portal_candidates WHERE {' AND '.join(where)} ORDER BY connector_priority_score DESC,id DESC LIMIT ?"
        with self.connect() as conn:
            return list(conn.execute(sql, tuple(args)))

    def portal_candidate(self, candidate_id: int) -> dict[str, object] | None:
        self.init()
        with self.connect() as conn:
            row = conn.execute('SELECT * FROM portal_candidates WHERE id=?', (candidate_id,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            for key in ('capabilities_json','evidence_json','connector_spec_json','source_candidate_ids_json'):
                fallback = {} if key == 'connector_spec_json' else []
                try:
                    result[key.replace('_json','')] = json.loads(result.pop(key))
                except (json.JSONDecodeError, TypeError):
                    result[key.replace('_json','')] = fallback
            return result

    def set_portal_candidate_state(self, candidate_id: int, state: str) -> bool:
        allowed = {'discovered','approved','rejected','watch','archived'}
        if state not in allowed:
            raise ValueError(f"state must be one of: {', '.join(sorted(allowed))}")
        self.init()
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            cur = conn.execute('UPDATE portal_candidates SET state=?,updated_at=? WHERE id=?', (state,now,candidate_id))
            conn.commit()
            return cur.rowcount > 0

    def begin_portal_discovery_run(self, *, seeds, config) -> int:
        self.init()
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            cur = conn.execute(
                'INSERT INTO portal_discovery_runs(started_at,seeds_json,config_json) VALUES(?,?,?)',
                (now,json.dumps(list(seeds)),json.dumps(config,sort_keys=True,default=str)),
            )
            conn.commit()
            return int(cur.lastrowid)

    def finish_portal_discovery_run(self, run_id: int, *, status: str, probed_count: int, saved_count: int, errors) -> None:
        self.init()
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                'UPDATE portal_discovery_runs SET completed_at=?,status=?,probed_count=?,saved_count=?,errors_json=? WHERE id=?',
                (now,status,probed_count,saved_count,json.dumps(list(errors),sort_keys=True),run_id),
            )
            conn.commit()

    def list_portal_discovery_runs(self, *, limit: int = 100) -> list[sqlite3.Row]:
        self.init()
        with self.connect() as conn:
            return list(conn.execute('SELECT * FROM portal_discovery_runs ORDER BY id DESC LIMIT ?', (limit,)))

