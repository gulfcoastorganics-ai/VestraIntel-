from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from .db import Database


# Verified fee ceilings are intentionally source-specific. These are not generic legal advice;
# they are a machine-readable reflection of the official source rules validated for this release.
LOCATOR_FEE_CAPS: dict[str, Decimal] = {
    "ca_unclaimed_property": Decimal("0.10"),
    "ny_unclaimed_property": Decimal("0.15"),
}

LEGAL_PROFILE: dict[str, dict[str, Any]] = {
    "licensed_locator": {
        "lane": "locator_service",
        "recoverability": 16,
        "friction": 10,
        "acquisition": 2,
    },
    "successor_claim": {
        "lane": "successor_claim_review",
        "recoverability": 15,
        "friction": 6,
        "acquisition": 9,
    },
    "asset_purchase": {
        "lane": "asset_acquisition_review",
        "recoverability": 14,
        "friction": 8,
        "acquisition": 10,
    },
    "open_data_intelligence": {
        "lane": "intelligence_sale",
        "recoverability": 11,
        "friction": 16,
        "acquisition": 4,
    },
    "owner_or_heir_only": {
        "lane": "owner_entitlement_only",
        "recoverability": 4,
        "friction": 2,
        "acquisition": 0,
    },
    "manual_legal_review": {
        "lane": "legal_review_required",
        "recoverability": 5,
        "friction": 3,
        "acquisition": 3,
    },
}


@dataclass(frozen=True)
class CommercialStats:
    opportunities: int
    entities: int


def _value_score(face_value: Decimal | None) -> float:
    if face_value is None:
        return 3.0
    value = max(Decimal("0"), face_value)
    if value >= 1_000_000:
        return 20.0
    if value >= 250_000:
        return 18.0
    if value >= 50_000:
        return 15.0
    if value >= 10_000:
        return 12.0
    if value >= 1_000:
        return 8.0
    if value >= 100:
        return 4.0
    return 1.0


def _time_score(row: Any, *, today: date) -> float:
    deadline = row["claim_deadline"]
    if deadline:
        try:
            days = (date.fromisoformat(deadline[:10]) - today).days
        except ValueError:
            days = None
        if days is not None:
            if days < 0:
                return 0.0
            if days <= 7:
                return 18.0
            if days <= 30:
                return 16.0
            if days <= 90:
                return 13.0

    asset = row["asset_class"]
    if asset in {"unclaimed_funds", "unclaimed_estate"}:
        return 11.0
    if asset in {"federal_license_notice", "patent_license_offer"}:
        return 14.0
    if asset in {"dissolved_company", "dissolved_company_signal"}:
        return 8.0
    return 9.0


def _identity_context(conn, opportunity_id: int) -> tuple[float, int, bool, list[str]]:
    rows = list(
        conn.execute(
            """
            SELECT e.id,e.entity_type,e.confidence,m.match_method,m.confidence AS membership_confidence,
                   COUNT(DISTINCT o2.source_id) AS source_count
            FROM entity_memberships m
            JOIN entities e ON e.id=m.entity_id
            JOIN entity_memberships m2 ON m2.entity_id=e.id
            JOIN opportunities o2 ON o2.id=m2.opportunity_id
            WHERE m.opportunity_id=?
            GROUP BY e.id,e.entity_type,e.confidence,m.match_method,m.confidence
            """,
            (opportunity_id,),
        )
    )
    if not rows:
        return 0.35, 1, False, ["no_resolved_entity"]
    best_conf = max(float(r["membership_confidence"]) for r in rows)
    exact_identifier = any(r["match_method"] == "exact_identifier" for r in rows)
    entity_ids = sorted({int(r["id"]) for r in rows})
    placeholders = ",".join("?" for _ in entity_ids)
    source_names: set[str] = set()
    if entity_ids:
        for source in conn.execute(
            f"""
            SELECT DISTINCT o.source_id
            FROM entity_memberships m JOIN opportunities o ON o.id=m.opportunity_id
            WHERE m.entity_id IN ({placeholders})
            """,
            entity_ids,
        ):
            source_names.add(str(source["source_id"]))
        research_rows = list(conn.execute(
            f"""
            SELECT DISTINCT rf.source_id,rf.confidence
            FROM research_facts rf
            JOIN entities e ON (rf.subject_canonical_key=e.canonical_key OR rf.object_canonical_key=e.canonical_key)
            WHERE e.id IN ({placeholders})
            """,
            entity_ids,
        ))
        for research in research_rows:
            source_names.add(str(research["source_id"]))
            best_conf = max(best_conf, min(0.99, float(research["confidence"])))
    max_sources = max(1, len(source_names))
    reasons = ["exact_identifier"] if exact_identifier else ["resolved_name_evidence"]
    has_research_corroboration = bool(entity_ids and research_rows)
    if has_research_corroboration:
        reasons.append("research_result_corroboration")
    if max_sources >= 2:
        reasons.append("cross_source_entity")
    return best_conf, max_sources, exact_identifier, reasons


def _cross_source_score(source_count: int) -> float:
    if source_count >= 5:
        return 14.0
    if source_count == 4:
        return 12.0
    if source_count == 3:
        return 10.0
    if source_count == 2:
        return 7.0
    return 0.0


def _hard_blocks(row: Any, *, exact_identifier: bool, source_count: int) -> list[str]:
    blocks: list[str] = []
    status = row["compliance_status"]
    legal_model = row["legal_model"]
    if status in {"licensed_only", "registration_required"}:
        blocks.append("operator_registration_required")
    if status == "owner_only" or legal_model == "owner_or_heir_only":
        blocks.append("owner_entitlement_required")
    if status in {"agreement_required", "agreement_and_law_review"}:
        blocks.append("signed_owner_agreement_required")
    if status in {"law_review_required", "agreement_and_law_review", "review_required"}:
        blocks.append("jurisdiction_review_required")
    if legal_model == "successor_claim":
        blocks.append("chain_of_ownership_required")
    if legal_model == "asset_purchase":
        blocks.append("purchase_and_title_review_required")
    if not exact_identifier and source_count <= 1:
        blocks.append("identity_not_independently_corroborated")
    deadline = row["claim_deadline"]
    if deadline:
        try:
            if date.fromisoformat(deadline[:10]) < date.today():
                blocks.append("deadline_expired")
        except ValueError:
            blocks.append("deadline_parse_review")
    return sorted(set(blocks))


def _next_actions(row: Any, lane: str, blocks: list[str]) -> list[str]:
    actions = ["verify_source_record"]
    if "identity_not_independently_corroborated" in blocks:
        actions.append("obtain_second_independent_identity_signal")
    if lane == "locator_service":
        actions.extend(["confirm_operator_eligibility", "prepare_owner_agreement_only_after_review"])
    elif lane == "successor_claim_review":
        actions.extend(["verify_transferability", "document_chain_of_ownership"])
    elif lane == "asset_acquisition_review":
        actions.extend(["verify_title_and_transfer_rules", "obtain_independent_asset_valuation"])
    elif lane == "intelligence_sale":
        actions.extend(["validate_commercial_relevance", "package_non_sensitive_intelligence"])
    else:
        actions.append("route_to_legal_or_entitlement_review")
    actions.append("human_approval_before_outreach_or_filing")
    return list(dict.fromkeys(actions))


def rebuild_commercial_assessments(db: Database, *, today: date | None = None) -> CommercialStats:
    """Derive commercial rankings from existing public records and the resolved evidence graph.

    Scores prioritize research triage only. They never establish ownership, entitlement, or permission
    to contact a person. Any action remains behind the project's human/compliance gates.
    """
    today = today or date.today()
    db.init()
    now = datetime.now(timezone.utc).isoformat()
    with db.connect() as conn:
        conn.execute("DELETE FROM commercial_assessments")
        rows = list(conn.execute("SELECT * FROM opportunities ORDER BY id"))
        for row in rows:
            identity_conf, source_count, exact_identifier, identity_reasons = _identity_context(
                conn, int(row["id"])
            )
            profile = LEGAL_PROFILE.get(row["legal_model"], LEGAL_PROFILE["manual_legal_review"])
            face_value = Decimal(row["face_value"]) if row["face_value"] not in (None, "") else None
            value_score = _value_score(face_value)
            identity_score = round(identity_conf * 14.0, 2)
            cross_score = _cross_source_score(source_count)
            recoverability_score = float(profile["recoverability"])
            friction_score = float(profile["friction"])
            acquisition_score = float(profile["acquisition"])
            time_score = _time_score(row, today=today)
            source_quality_score = 8.0  # All current ingest adapters are official/public-source adapters.

            total = min(
                100.0,
                value_score
                + identity_score
                + cross_score
                + recoverability_score
                + friction_score
                + acquisition_score
                + time_score
                + source_quality_score,
            )
            blocks = _hard_blocks(
                row, exact_identifier=exact_identifier, source_count=source_count
            )
            if "deadline_expired" in blocks:
                total = min(total, 20.0)
            lane = str(profile["lane"])
            reason_codes = list(identity_reasons)
            reason_codes.extend(
                [
                    f"legal_model:{row['legal_model']}",
                    f"source_count:{source_count}",
                    f"asset_class:{row['asset_class']}",
                ]
            )
            if face_value is not None:
                reason_codes.append("known_face_value")
            fee_cap = LOCATOR_FEE_CAPS.get(row["source_id"])
            fee_ceiling = face_value * fee_cap if face_value is not None and fee_cap else None
            actionability = max(0.0, total - min(30.0, 6.0 * len(blocks)))

            conn.execute(
                """
                INSERT INTO commercial_assessments(
                  opportunity_id,lane,commercial_score,actionability_score,evidence_confidence,
                  independent_source_count,value_score,identity_score,cross_source_score,
                  recoverability_score,time_to_money_score,regulatory_friction_score,
                  acquisition_score,fee_cap_percent,gross_fee_ceiling,currency,
                  reason_json,block_json,next_action_json,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    int(row["id"]),
                    lane,
                    round(total, 2),
                    round(actionability, 2),
                    round(identity_conf, 4),
                    source_count,
                    value_score,
                    identity_score,
                    cross_score,
                    recoverability_score,
                    time_score,
                    friction_score,
                    acquisition_score,
                    float(fee_cap * 100) if fee_cap else None,
                    str(fee_ceiling.quantize(Decimal("0.01"))) if fee_ceiling is not None else None,
                    row["currency"],
                    json.dumps(reason_codes, sort_keys=True),
                    json.dumps(blocks, sort_keys=True),
                    json.dumps(_next_actions(row, lane, blocks)),
                    now,
                ),
            )

        conn.execute("DELETE FROM entity_commercial_summaries")
        entity_ids = [int(r["id"]) for r in conn.execute("SELECT id FROM entities ORDER BY id")]
        entity_count = 0
        for entity_id in entity_ids:
            linked = list(
                conn.execute(
                    """
                    SELECT DISTINCT o.id,o.source_id,o.asset_class,o.jurisdiction,o.face_value,o.currency,
                           c.lane,c.commercial_score,c.actionability_score,c.gross_fee_ceiling
                    FROM entity_memberships m
                    JOIN opportunities o ON o.id=m.opportunity_id
                    JOIN commercial_assessments c ON c.opportunity_id=o.id
                    WHERE m.entity_id=?
                    """,
                    (entity_id,),
                )
            )
            if not linked:
                continue
            sources = sorted({str(r["source_id"]) for r in linked})
            classes = sorted({str(r["asset_class"]) for r in linked})
            jurisdictions = sorted({str(r["jurisdiction"]) for r in linked})
            lanes: dict[str, int] = {}
            values: dict[str, Decimal] = {}
            fees: dict[str, Decimal] = {}
            for r in linked:
                lanes[str(r["lane"])] = lanes.get(str(r["lane"]), 0) + 1
                if r["face_value"] not in (None, "") and r["currency"]:
                    values[str(r["currency"])] = values.get(str(r["currency"]), Decimal("0")) + Decimal(str(r["face_value"]))
                if r["gross_fee_ceiling"] not in (None, "") and r["currency"]:
                    fees[str(r["currency"])] = fees.get(str(r["currency"]), Decimal("0")) + Decimal(str(r["gross_fee_ceiling"]))
            best = max(float(r["commercial_score"]) for r in linked)
            best_actionable = max(float(r["actionability_score"]) for r in linked)
            breadth_bonus = min(8.0, max(0, len(sources) - 1) * 2.0 + max(0, len(classes) - 1))
            entity_score = min(100.0, best + breadth_bonus)
            primary_lane = sorted(lanes.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            conn.execute(
                """
                INSERT INTO entity_commercial_summaries(
                  entity_id,commercial_score,actionability_score,primary_lane,opportunity_count,
                  source_count,asset_classes_json,jurisdictions_json,value_by_currency_json,
                  fee_ceiling_by_currency_json,lane_mix_json,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    entity_id,
                    round(entity_score, 2),
                    round(best_actionable, 2),
                    primary_lane,
                    len(linked),
                    len(sources),
                    json.dumps(classes),
                    json.dumps(jurisdictions),
                    json.dumps({k: str(v.quantize(Decimal("0.01"))) for k, v in values.items()}, sort_keys=True),
                    json.dumps({k: str(v.quantize(Decimal("0.01"))) for k, v in fees.items()}, sort_keys=True),
                    json.dumps(lanes, sort_keys=True),
                    now,
                ),
            )
            entity_count += 1
        conn.commit()
        return CommercialStats(opportunities=len(rows), entities=entity_count)
