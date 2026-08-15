from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from .db import Database


@dataclass(frozen=True)
class EconomicsStats:
    cases: int
    economically_ranked: int
    unknown_value: int


# Planning assumptions only. They are deliberately editable and are not representations of
# guaranteed payout times, market prices, or legal recovery percentages.
DEFAULT_TIME_TO_VALUE_DAYS: dict[str, float] = {
    "locator_service": 45.0,
    "successor_claim_review": 90.0,
    "asset_acquisition_review": 120.0,
    "intelligence_sale": 14.0,
    "owner_entitlement_only": 60.0,
    "legal_review_required": 90.0,
}

EFFORT_HOURS = {"low": 0.35, "medium": 1.25, "high": 3.5}
ACCESS_SUCCESS = {
    "public_api": 0.93,
    "api_key": 0.88,
    "account_api_key": 0.82,
    "public_manual": 0.72,
    "human_review": 0.62,
    "enrollment_required": 0.52,
    "manual_captcha": 0.42,
    "legal_review": 0.38,
}
ACCESS_CASH_COST = {
    "public_api": 0.0,
    "api_key": 0.0,
    "account_api_key": 0.0,
    "public_manual": 0.0,
    "human_review": 25.0,
    "enrollment_required": 10.0,
    "manual_captcha": 0.0,
    "legal_review": 125.0,
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


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _case_revenue_reference(
    conn,
    anomaly: Any,
    *,
    default_intelligence_value: float,
    unknown_capture_rate: float,
) -> tuple[float | None, str | None, str, dict[str, Any]]:
    opportunity_ids = [int(v) for v in _json_list(anomaly["opportunity_ids_json"]) if str(v).isdigit()]
    if not opportunity_ids:
        return None, None, "unknown", {"reason": "no_linked_opportunities"}

    placeholders = ",".join("?" for _ in opportunity_ids)
    rows = list(conn.execute(
        f"""
        SELECT o.id,o.face_value,o.currency,o.legal_model,o.source_id,
               c.lane,c.gross_fee_ceiling,c.fee_cap_percent,c.commercial_score,c.actionability_score
        FROM opportunities o
        LEFT JOIN commercial_assessments c ON c.opportunity_id=o.id
        WHERE o.id IN ({placeholders})
        """,
        opportunity_ids,
    ))
    if not rows:
        return None, None, "unknown", {"reason": "linked_opportunities_missing"}

    fee_by_currency: dict[str, Decimal] = {}
    face_by_currency: dict[str, Decimal] = {}
    lanes: set[str] = set()
    for row in rows:
        lane = str(row["lane"] or "")
        if lane:
            lanes.add(lane)
        currency = str(row["currency"] or "")
        fee = _decimal(row["gross_fee_ceiling"])
        face = _decimal(row["face_value"])
        if currency and fee is not None and fee > 0:
            fee_by_currency[currency] = fee_by_currency.get(currency, Decimal("0")) + fee
        if currency and face is not None and face > 0:
            face_by_currency[currency] = face_by_currency.get(currency, Decimal("0")) + face

    if len(fee_by_currency) == 1:
        currency, amount = next(iter(fee_by_currency.items()))
        return float(amount), currency, "verified_fee_ceiling", {
            "fee_ceiling_by_currency": {currency: str(amount)},
            "lanes": sorted(lanes),
        }
    if len(fee_by_currency) > 1:
        return None, "MULTI", "mixed_currency_fee_ceiling", {
            "fee_ceiling_by_currency": {k: str(v) for k, v in sorted(fee_by_currency.items())},
            "lanes": sorted(lanes),
        }

    if lanes and lanes <= {"intelligence_sale"} and not face_by_currency:
        return float(default_intelligence_value), "USD", "planning_assumption:intelligence_sale", {
            "assumed_value": float(default_intelligence_value),
            "lanes": sorted(lanes),
        }

    # For acquisition/successor/legal-review lanes, face value is not revenue. A configurable
    # capture-rate assumption converts it to a planning reference only; the basis stays explicit.
    if len(face_by_currency) == 1 and lanes & {"successor_claim_review", "asset_acquisition_review", "legal_review_required"}:
        currency, face = next(iter(face_by_currency.items()))
        assumed = face * Decimal(str(max(0.0, min(1.0, unknown_capture_rate))))
        return float(assumed), currency, "planning_assumption:capture_rate", {
            "face_value": str(face),
            "capture_rate": float(unknown_capture_rate),
            "lanes": sorted(lanes),
        }

    return None, (next(iter(face_by_currency)) if len(face_by_currency) == 1 else None), "unknown", {
        "face_value_by_currency": {k: str(v) for k, v in sorted(face_by_currency.items())},
        "lanes": sorted(lanes),
    }


def _viability_probability(anomaly: Any, hard_gates: list[str], resolution_score: float) -> float:
    actionability = float(anomaly["actionability_score"] or 0) / 100.0
    confidence = float(anomaly["confidence"] or 0)
    progress = max(0.0, min(1.0, resolution_score / 100.0))
    base = 0.10 + 0.40 * actionability + 0.28 * confidence + 0.22 * progress
    gate_penalty = min(0.45, 0.045 * len(hard_gates))
    return round(max(0.03, min(0.95, base - gate_penalty)), 4)


def _time_discount(days: float) -> float:
    # Hyperbolic discount keeps long-horizon cases visible without pretending future cash equals
    # immediate cash. 30 days halves the timing component.
    return round(1.0 / (1.0 + max(0.0, days) / 30.0), 4)


def _task_probability(task: Any, unresolved_conditions: set[str], evi_rationale: dict[str, Any]) -> float:
    coverage = len(set(evi_rationale.get("condition_coverage", [])) & unresolved_conditions)
    access = ACCESS_SUCCESS.get(str(task["access_mode"]), 0.60)
    uplift = min(1.0, max(0.0, float(task["expected_uplift"] or 0) / 100.0))
    confidence = min(1.0, max(0.0, float(task["confidence"] or 0)))
    effort_penalty = {"low": 0.0, "medium": 0.04, "high": 0.09}.get(str(task["estimated_effort"]), 0.04)
    raw = 0.10 + 0.26 * uplift + 0.22 * confidence + 0.26 * access + min(0.18, coverage * 0.09) - effort_penalty
    return round(max(0.05, min(0.95, raw)), 4)


def _research_cost(task: Any, hourly_research_cost: float) -> float:
    hours = EFFORT_HOURS.get(str(task["estimated_effort"]), 1.25)
    cash = ACCESS_CASH_COST.get(str(task["access_mode"]), 10.0)
    return round(max(0.0, hours * max(0.0, hourly_research_cost) + cash), 2)


def rebuild_case_economics(
    db: Database,
    *,
    hourly_research_cost: float = 25.0,
    default_intelligence_value: float = 250.0,
    unknown_capture_rate: float = 0.05,
) -> EconomicsStats:
    """Build planning economics for active cases and their pending research tasks.

    Monetary figures are decision-support assumptions/reference ceilings only. They do not establish
    ownership, entitlement, claim value, acquisition price, or guaranteed revenue.
    """
    db.init()
    now = datetime.now(timezone.utc).isoformat()
    cases_ranked = 0
    unknown_value = 0

    with db.connect() as conn:
        rows = list(conn.execute(
            """
            SELECT c.*,a.*
            FROM case_resolution_states c JOIN anomaly_findings a ON a.id=c.anomaly_id
            WHERE a.state IN ('open','confirmed')
            ORDER BY a.severity_score DESC,a.id
            """
        ))
        active_ids = {int(r["anomaly_id"]) for r in rows}
        if active_ids:
            placeholders = ",".join("?" for _ in active_ids)
            conn.execute(f"DELETE FROM case_task_economics WHERE anomaly_id NOT IN ({placeholders})", tuple(active_ids))
            conn.execute(f"DELETE FROM case_economic_states WHERE anomaly_id NOT IN ({placeholders})", tuple(active_ids))
        else:
            conn.execute("DELETE FROM case_task_economics")
            conn.execute("DELETE FROM case_economic_states")

        for case in rows:
            anomaly_id = int(case["anomaly_id"])
            hard_gates = [str(v) for v in _json_list(case["hard_gates_json"])]
            unresolved = {str(v) for v in _json_list(case["unresolved_conditions_json"])}
            revenue, currency, revenue_basis, revenue_detail = _case_revenue_reference(
                conn,
                case,
                default_intelligence_value=default_intelligence_value,
                unknown_capture_rate=unknown_capture_rate,
            )
            if revenue is None:
                unknown_value += 1

            lane_row = conn.execute(
                """
                SELECT c.lane,COUNT(*) AS n
                FROM commercial_assessments c
                JOIN opportunities o ON o.id=c.opportunity_id
                WHERE o.id IN (
                  SELECT value FROM json_each(?)
                )
                GROUP BY c.lane ORDER BY n DESC,c.lane LIMIT 1
                """,
                (case["opportunity_ids_json"],),
            ).fetchone()
            lane = str(lane_row["lane"]) if lane_row else "legal_review_required"
            time_days = DEFAULT_TIME_TO_VALUE_DAYS.get(lane, 90.0)
            t_discount = _time_discount(time_days)
            viability = _viability_probability(case, hard_gates, float(case["resolution_score"] or 0))
            regulatory_factor = round(max(0.35, 1.0 - min(0.60, 0.075 * len(hard_gates))), 4)
            expected_case_value = round((revenue or 0.0) * viability * t_discount * regulatory_factor, 2)

            # Adaptive research budget grows with probability-adjusted case value but remains finite.
            recommended_budget = round(
                max(25.0, min(1500.0, 25.0 + expected_case_value * 0.18 + float(case["commercial_score"] or 0) * 0.75)),
                2,
            )

            conn.execute("DELETE FROM case_task_economics WHERE anomaly_id=?", (anomaly_id,))
            task_rows = list(conn.execute(
                """
                SELECT t.*,p.evi_score,p.eligible,p.rationale_json
                FROM research_tasks t
                LEFT JOIN case_task_priorities p ON p.task_id=t.id AND p.anomaly_id=t.anomaly_id
                WHERE t.anomaly_id=? AND t.state IN ('pending','in_progress')
                ORDER BY COALESCE(p.evi_score,0) DESC,t.priority_score DESC,t.id
                """,
                (anomaly_id,),
            ))
            ranked: list[tuple[float, int]] = []
            for task in task_rows:
                try:
                    evi_detail = json.loads(task["rationale_json"] or "{}")
                except (json.JSONDecodeError, TypeError):
                    evi_detail = {}
                p_resolve = _task_probability(task, unresolved, evi_detail)
                research_cost = _research_cost(task, hourly_research_cost)
                if revenue is None:
                    # Unknown-value cases still use commercial/EVI proxies, but are prevented from
                    # masquerading as dollar-valued expected returns.
                    incremental_value = 0.0
                    economic_score = round(
                        min(100.0, float(task["evi_score"] or 0) * 0.55 + float(case["commercial_score"] or 0) * 0.25 + p_resolve * 20.0),
                        2,
                    )
                else:
                    incremental_value = round(revenue * viability * p_resolve * t_discount * regulatory_factor, 2)
                    roi_component = incremental_value / max(1.0, incremental_value + research_cost)
                    economic_score = round(
                        min(100.0, 100.0 * roi_component * (0.72 + 0.28 * (float(task["evi_score"] or 0) / 100.0))),
                        2,
                    )
                economically_eligible = bool(
                    task["eligible"] if task["eligible"] is not None else 1
                ) and research_cost <= recommended_budget and economic_score > 0
                rationale = {
                    "revenue_basis": revenue_basis,
                    "revenue_reference": revenue,
                    "currency": currency,
                    "case_viability_probability": viability,
                    "task_resolution_probability": p_resolve,
                    "time_to_value_days_assumption": time_days,
                    "time_discount": t_discount,
                    "regulatory_factor": regulatory_factor,
                    "research_cost_assumption": research_cost,
                    "hourly_research_cost_assumption": hourly_research_cost,
                    "expected_incremental_value": incremental_value if revenue is not None else None,
                    "information_value_score": float(task["evi_score"] or 0),
                    "planning_only": True,
                }
                conn.execute(
                    """
                    INSERT INTO case_task_economics(
                      anomaly_id,task_id,resolve_probability,research_cost,time_discount,
                      expected_incremental_value,economic_score,eligible,rationale_json,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(anomaly_id,task_id) DO UPDATE SET
                      resolve_probability=excluded.resolve_probability,research_cost=excluded.research_cost,
                      time_discount=excluded.time_discount,expected_incremental_value=excluded.expected_incremental_value,
                      economic_score=excluded.economic_score,eligible=excluded.eligible,
                      rationale_json=excluded.rationale_json,updated_at=excluded.updated_at
                    """,
                    (
                        anomaly_id, int(task["id"]), p_resolve, research_cost, t_discount,
                        incremental_value if revenue is not None else None, economic_score,
                        1 if economically_eligible else 0, json.dumps(rationale, sort_keys=True), now,
                    ),
                )
                if economically_eligible:
                    ranked.append((economic_score, int(task["id"])))

            ranked.sort(reverse=True)
            best_score, best_task_id = (ranked[0] if ranked else (None, None))
            status = "economically_ranked" if best_task_id is not None else (
                "research_complete" if case["resolution_status"] == "review_ready" else "no_economic_task"
            )
            if revenue is None:
                status = "value_unknown" if best_task_id is not None else status
            assumptions = {
                "hourly_research_cost": hourly_research_cost,
                "default_intelligence_value": default_intelligence_value,
                "unknown_capture_rate": unknown_capture_rate,
                "time_to_value_days": time_days,
                "revenue_detail": revenue_detail,
                "planning_only": True,
            }
            conn.execute(
                """
                INSERT INTO case_economic_states(
                  anomaly_id,lane,economic_status,revenue_reference,currency,revenue_basis,
                  viability_probability,time_to_value_days,time_discount,regulatory_factor,
                  expected_case_value,recommended_research_budget,best_task_id,best_task_economic_score,
                  assumptions_json,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(anomaly_id) DO UPDATE SET
                  lane=excluded.lane,economic_status=excluded.economic_status,
                  revenue_reference=excluded.revenue_reference,currency=excluded.currency,
                  revenue_basis=excluded.revenue_basis,viability_probability=excluded.viability_probability,
                  time_to_value_days=excluded.time_to_value_days,time_discount=excluded.time_discount,
                  regulatory_factor=excluded.regulatory_factor,expected_case_value=excluded.expected_case_value,
                  recommended_research_budget=excluded.recommended_research_budget,best_task_id=excluded.best_task_id,
                  best_task_economic_score=excluded.best_task_economic_score,assumptions_json=excluded.assumptions_json,
                  updated_at=excluded.updated_at
                """,
                (
                    anomaly_id,lane,status,revenue,currency,revenue_basis,viability,time_days,t_discount,
                    regulatory_factor,expected_case_value,recommended_budget,best_task_id,best_score,
                    json.dumps(assumptions, sort_keys=True),now,
                ),
            )
            if best_task_id is not None:
                cases_ranked += 1

        conn.commit()

    return EconomicsStats(cases=len(rows), economically_ranked=cases_ranked, unknown_value=unknown_value)
