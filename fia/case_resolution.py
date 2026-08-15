from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .db import Database


@dataclass(frozen=True)
class CaseResolutionStats:
    cases: int
    review_ready: int
    researching: int
    blocked: int
    budget_exhausted: int


TARGETS: dict[str, dict[str, Any]] = {
    "orphaned_business_asset": {
        "target_state": "ready_for_human_asset_disposition_review",
        "conditions": (
            "identity_corroborated",
            "dissolution_status_verified",
            "asset_disposition_path_researched",
        ),
    },
    "dissolved_company_ip": {
        "target_state": "ready_for_human_ip_title_and_commercial_review",
        "conditions": (
            "identity_corroborated",
            "patent_status_current",
            "patent_family_reviewed",
            "ip_disposition_path_researched",
        ),
    },
    "successor_entitlement_candidate": {
        "target_state": "ready_for_human_successor_entitlement_review",
        "conditions": (
            "court_record_verified",
            "successor_chain_evidence_present",
            "court_requirements_reviewed",
        ),
    },
    "royalty_metadata_mismatch": {
        "target_state": "ready_for_metadata_reconciliation_delivery",
        "conditions": (
            "independent_metadata_collected",
            "mlc_metadata_checked",
            "soundexchange_metadata_checked",
            "royalty_reconciliation_completed",
        ),
    },
    "lapsed_technology_reuse": {
        "target_state": "ready_for_human_freedom_to_operate_and_market_review",
        "conditions": (
            "patent_status_current",
            "patent_family_reviewed",
            "market_relevance_checked",
        ),
    },
    "high_value_cross_source": {
        "target_state": "ready_for_human_lane_selection",
        "conditions": (
            "identity_corroborated",
            "weakest_identity_edge_reviewed",
        ),
    },
    "identity_resolution_gap": {
        "target_state": "identity_corroborated_for_human_review",
        "conditions": ("identity_corroborated",),
    },
    "material_source_change": {
        "target_state": "source_change_explained_for_human_review",
        "conditions": ("material_change_reviewed",),
    },
}


# These gates are intentionally never auto-cleared by public-data research. They require the
# actual claimant/operator/attorney or other authorized human to make a jurisdiction-specific
# decision before outreach, contracting, purchase, filing, or claiming.
NON_AUTOMATABLE_GATES = {
    "human_review_required",
    "human_approval_before_outreach_or_filing",
    "entitlement_not_established",
    "court_entitlement_review_required",
    "rightsholder_entitlement_required",
    "no_third_party_royalty_claim",
    "case_specific_entitlement_and_compliance_review_required",
    "family_and_freedom_to_operate_review_required",
    "operator_registration_required",
    "signed_owner_agreement_required",
    "jurisdiction_review_required",
    "owner_entitlement_required",
    "purchase_and_title_review_required",
}


EFFORT_COST = {"low": 6.0, "medium": 12.0, "high": 22.0}
ACCESS_COST = {
    "public_api": 0.0,
    "api_key": 2.0,
    "account_api_key": 4.0,
    "public_manual": 4.0,
    "human_review": 6.0,
    "enrollment_required": 9.0,
    "manual_captcha": 11.0,
    "legal_review": 14.0,
}


TASK_TO_CONDITIONS: dict[str, tuple[str, ...]] = {
    "verify_source_record": ("source_record_verified",),
    "companies_house_profile": ("dissolution_status_verified",),
    "independent_identity_corroboration": ("identity_corroborated", "weakest_identity_edge_reviewed"),
    "successor_chain_research": ("successor_chain_evidence_present",),
    "court_record_verification": ("court_record_verified", "court_requirements_reviewed"),
    "dissolution_asset_disposition_review": ("asset_disposition_path_researched", "ip_disposition_path_researched"),
    "uspto_assignment_lookup": ("ip_disposition_path_researched",),
    "patent_status_check": ("patent_status_current",),
    "patent_family_review": ("patent_family_reviewed",),
    "mlc_recording_lookup": ("mlc_metadata_checked",),
    "soundexchange_rightsholder_lookup": ("soundexchange_metadata_checked",),
    "royalty_metadata_reconciliation": ("royalty_reconciliation_completed",),
    "market_relevance_check": ("market_relevance_checked",),
    "source_change_review": ("material_change_reviewed",),
}


RELATION_TO_CONDITIONS: dict[str, tuple[str, ...]] = {
    "official_name_of": ("identity_corroborated",),
    "corroborates_identity": ("identity_corroborated", "weakest_identity_edge_reviewed"),
    "has_company_status": ("dissolution_status_verified",),
    "successor_of": ("successor_chain_evidence_present", "asset_disposition_path_researched"),
    "merged_into": ("successor_chain_evidence_present", "asset_disposition_path_researched"),
    "acquired_by": ("successor_chain_evidence_present", "asset_disposition_path_researched"),
    "assigned_to": ("successor_chain_evidence_present", "asset_disposition_path_researched", "ip_disposition_path_researched"),
    "restored_as": ("successor_chain_evidence_present", "asset_disposition_path_researched"),
    "court_owner_of_record": ("court_record_verified",),
    "current_patent_status": ("patent_status_current",),
    "recording_to_work": ("mlc_metadata_checked", "independent_metadata_collected"),
    "recording_rightsholder": ("soundexchange_metadata_checked", "independent_metadata_collected"),
    "metadata_discrepancy_resolved": ("royalty_reconciliation_completed",),
    "current_market_signal": ("market_relevance_checked",),
    "source_change_explained": ("material_change_reviewed",),
}


def _json_list(value: Any) -> list[Any]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value))
    except (json.JSONDecodeError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _entity_source_count(conn, entity_id: int | None) -> int:
    if not entity_id:
        return 0
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT source_id) AS n FROM (
          SELECT o.source_id AS source_id
          FROM entity_memberships m JOIN opportunities o ON o.id=m.opportunity_id
          WHERE m.entity_id=?
          UNION ALL
          SELECT rf.source_id AS source_id
          FROM research_facts rf
          JOIN entities e ON rf.subject_canonical_key=e.canonical_key OR rf.object_canonical_key=e.canonical_key
          WHERE e.id=?
        )
        """,
        (entity_id, entity_id),
    ).fetchone()
    return int(row["n"] or 0) if row else 0


def _completed_task_types(conn, anomaly_id: int) -> set[str]:
    return {
        str(row["task_type"])
        for row in conn.execute(
            "SELECT task_type FROM research_tasks WHERE anomaly_id=? AND state='completed'",
            (anomaly_id,),
        )
    }


def _fact_relations(conn, anomaly_id: int) -> set[str]:
    rows = conn.execute(
        """
        SELECT rf.fact_type,rf.relation_type
        FROM research_facts rf JOIN research_tasks rt ON rt.id=rf.task_id
        WHERE rt.anomaly_id=? AND rf.confidence>=0.70
        """,
        (anomaly_id,),
    )
    values: set[str] = set()
    for row in rows:
        if row["fact_type"]:
            values.add(str(row["fact_type"]))
        if row["relation_type"]:
            values.add(str(row["relation_type"]))
    return values


def _satisfied_conditions(conn, anomaly: Any, target_conditions: tuple[str, ...]) -> set[str]:
    anomaly_id = int(anomaly["id"])
    entity_id = int(anomaly["entity_id"]) if anomaly["entity_id"] is not None else None
    satisfied: set[str] = set()

    if _entity_source_count(conn, entity_id) >= 2:
        satisfied.update({"identity_corroborated", "independent_metadata_collected"})

    for task_type in _completed_task_types(conn, anomaly_id):
        satisfied.update(TASK_TO_CONDITIONS.get(task_type, ()))

    for relation in _fact_relations(conn, anomaly_id):
        satisfied.update(RELATION_TO_CONDITIONS.get(relation, ()))

    # Identity corroboration requires a second source or an explicit reviewed task/fact; merely
    # completing a company profile from the same source is not enough by itself.
    if _entity_source_count(conn, entity_id) < 2:
        identity_evidence = bool(
            {"independent_identity_corroboration"} & _completed_task_types(conn, anomaly_id)
            or {"corroborates_identity"} & _fact_relations(conn, anomaly_id)
        )
        if not identity_evidence:
            satisfied.discard("identity_corroborated")

    return satisfied & set(target_conditions)


def _task_cost(row: Any) -> float:
    return round(
        EFFORT_COST.get(str(row["estimated_effort"]), 12.0)
        + ACCESS_COST.get(str(row["access_mode"]), 6.0),
        2,
    )


def _task_evi(
    row: Any,
    *,
    anomaly: Any,
    unresolved: set[str],
    current_sources: set[str],
    completed_types: set[str],
) -> tuple[float, dict[str, Any]]:
    task_conditions = set(TASK_TO_CONDITIONS.get(str(row["task_type"]), ()))
    blocker_coverage = len(task_conditions & unresolved)
    resolves = set(_json_list(row["resolves_blockers_json"]))
    anomaly_blocks = set(_json_list(anomaly["block_json"]))
    declared_blocker_coverage = len(resolves & anomaly_blocks)

    information_gain = min(40.0, float(row["expected_uplift"] or 0) * 1.55)
    blocker_gain = min(28.0, blocker_coverage * 12.0 + declared_blocker_coverage * 4.0)
    severity_gain = float(anomaly["severity_score"] or 0) * 0.10
    actionability_gain = float(anomaly["actionability_score"] or 0) * 0.06
    novelty_bonus = 0.0
    if row["source_id"] and str(row["source_id"]) not in current_sources:
        novelty_bonus += 7.0
    if str(row["task_type"]) not in completed_types:
        novelty_bonus += 3.0

    prerequisites = set(_json_list(row["prerequisites_json"]))
    prerequisite_penalty = 0.0
    if prerequisites:
        # Prerequisites are semantic labels in v0.6/v0.7. Until a matching evidence state is
        # present, keep the task visible but lower its rank instead of inventing completion.
        prerequisite_penalty = min(12.0, 4.0 * len(prerequisites))

    cost = _task_cost(row)
    raw = information_gain + blocker_gain + severity_gain + actionability_gain + novelty_bonus - cost - prerequisite_penalty
    evi = round(max(0.0, min(100.0, raw)), 2)
    detail = {
        "information_gain": round(information_gain, 2),
        "condition_coverage": sorted(task_conditions & unresolved),
        "declared_blocker_coverage": sorted(resolves & anomaly_blocks),
        "novelty_bonus": round(novelty_bonus, 2),
        "execution_cost": cost,
        "prerequisite_penalty": round(prerequisite_penalty, 2),
    }
    return evi, detail


def rebuild_case_resolutions(db: Database, *, base_budget: float = 100.0) -> CaseResolutionStats:
    """Rank the next highest-value research lookup for every active anomaly.

    This is an information-planning layer only. A `review_ready` case means the configured research
    conditions have been met; it does not establish legal ownership, entitlement, authority to
    contact anyone, or authority to file a claim.
    """
    db.init()
    now = datetime.now(timezone.utc).isoformat()
    counts = {"review_ready": 0, "researching": 0, "blocked": 0, "budget_exhausted": 0}

    with db.connect() as conn:
        anomalies = list(conn.execute(
            "SELECT * FROM anomaly_findings WHERE state IN ('open','confirmed') ORDER BY severity_score DESC,id"
        ))
        active_ids = {int(a["id"]) for a in anomalies}
        if active_ids:
            placeholders = ",".join("?" for _ in active_ids)
            conn.execute(f"DELETE FROM case_task_priorities WHERE anomaly_id NOT IN ({placeholders})", tuple(active_ids))
            conn.execute(f"DELETE FROM case_resolution_states WHERE anomaly_id NOT IN ({placeholders})", tuple(active_ids))
        else:
            conn.execute("DELETE FROM case_task_priorities")
            conn.execute("DELETE FROM case_resolution_states")

        for anomaly in anomalies:
            anomaly_id = int(anomaly["id"])
            target = TARGETS.get(str(anomaly["anomaly_type"]), {
                "target_state": "ready_for_human_case_review",
                "conditions": ("source_record_verified",),
            })
            conditions = tuple(target["conditions"])
            satisfied = _satisfied_conditions(conn, anomaly, conditions)
            unresolved = set(conditions) - satisfied
            anomaly_blocks = set(_json_list(anomaly["block_json"]))
            hard_gates = sorted(anomaly_blocks & NON_AUTOMATABLE_GATES | {"human_approval_before_outreach_or_filing"})

            entity_sources: set[str] = set(_json_list(anomaly["source_ids_json"]))
            completed_types = _completed_task_types(conn, anomaly_id)
            tasks = list(conn.execute(
                """
                SELECT * FROM research_tasks
                WHERE anomaly_id=? AND state IN ('pending','in_progress','completed')
                ORDER BY priority_score DESC,id
                """,
                (anomaly_id,),
            ))

            completed_cost = sum(_task_cost(t) for t in tasks if t["state"] == "completed")
            # Give high-commercial/high-severity cases somewhat more research room while keeping a
            # finite default budget that prevents runaway recursive expansion.
            budget_total = round(
                max(40.0, base_budget + float(anomaly["commercial_score"] or 0) * 0.20 + float(anomaly["severity_score"] or 0) * 0.10),
                2,
            )
            budget_spent = round(completed_cost, 2)
            budget_remaining = round(max(0.0, budget_total - budget_spent), 2)

            conn.execute("DELETE FROM case_task_priorities WHERE anomaly_id=?", (anomaly_id,))
            ranked: list[tuple[float, float, Any, dict[str, Any]]] = []
            for row in tasks:
                if row["state"] not in {"pending", "in_progress"}:
                    continue
                evi, detail = _task_evi(
                    row,
                    anomaly=anomaly,
                    unresolved=unresolved,
                    current_sources=entity_sources,
                    completed_types=completed_types,
                )
                cost = float(detail["execution_cost"])
                eligible = bool(evi > 0 and cost <= budget_remaining)
                ranked.append((evi, cost, row, detail | {"eligible": eligible}))

            ranked.sort(key=lambda item: (item[0], float(item[2]["priority_score"] or 0)), reverse=True)
            next_task_id: int | None = None
            next_task_evi: float | None = None
            rank = 0
            for evi, cost, row, detail in ranked:
                rank += 1
                eligible = bool(detail["eligible"])
                if next_task_id is None and eligible:
                    next_task_id = int(row["id"])
                    next_task_evi = evi
                conn.execute(
                    """
                    INSERT INTO case_task_priorities(
                      anomaly_id,task_id,evi_score,execution_cost,rank,eligible,rationale_json,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(anomaly_id,task_id) DO UPDATE SET
                      evi_score=excluded.evi_score,execution_cost=excluded.execution_cost,
                      rank=excluded.rank,eligible=excluded.eligible,rationale_json=excluded.rationale_json,
                      updated_at=excluded.updated_at
                    """,
                    (anomaly_id, int(row["id"]), evi, cost, rank, 1 if eligible else 0,
                     json.dumps(detail, ensure_ascii=False, sort_keys=True), now),
                )

            if not unresolved:
                status = "review_ready"
            elif budget_remaining <= 0.0:
                status = "budget_exhausted"
            elif next_task_id is not None:
                status = "researching"
            else:
                status = "blocked"
            counts[status] += 1

            resolution_score = 100.0 if not conditions else round(100.0 * len(satisfied) / len(conditions), 2)
            evidence_score = round(min(100.0, float(anomaly["confidence"] or 0) * 70 + len(entity_sources) * 7.5), 2)
            conn.execute(
                """
                INSERT INTO case_resolution_states(
                  anomaly_id,target_state,resolution_status,resolution_score,evidence_score,
                  budget_total,budget_spent,budget_remaining,next_task_id,next_task_evi,
                  satisfied_conditions_json,unresolved_conditions_json,hard_gates_json,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(anomaly_id) DO UPDATE SET
                  target_state=excluded.target_state,resolution_status=excluded.resolution_status,
                  resolution_score=excluded.resolution_score,evidence_score=excluded.evidence_score,
                  budget_total=excluded.budget_total,budget_spent=excluded.budget_spent,
                  budget_remaining=excluded.budget_remaining,next_task_id=excluded.next_task_id,
                  next_task_evi=excluded.next_task_evi,satisfied_conditions_json=excluded.satisfied_conditions_json,
                  unresolved_conditions_json=excluded.unresolved_conditions_json,hard_gates_json=excluded.hard_gates_json,
                  updated_at=excluded.updated_at
                """,
                (
                    anomaly_id, str(target["target_state"]), status, resolution_score, evidence_score,
                    budget_total, budget_spent, budget_remaining, next_task_id, next_task_evi,
                    json.dumps(sorted(satisfied)), json.dumps(sorted(unresolved)), json.dumps(hard_gates), now,
                ),
            )

        conn.commit()

    return CaseResolutionStats(
        cases=len(anomalies),
        review_ready=counts["review_ready"],
        researching=counts["researching"],
        blocked=counts["blocked"],
        budget_exhausted=counts["budget_exhausted"],
    )
