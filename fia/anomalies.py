from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from .db import Database


@dataclass(frozen=True)
class AnomalyStats:
    findings: int
    entities_scanned: int
    opportunity_findings: int


@dataclass(frozen=True)
class Finding:
    rule_id: str
    anomaly_type: str
    title: str
    summary: str
    entity_id: int | None
    primary_opportunity_id: int | None
    confidence: float
    severity_score: float
    commercial_score: float
    actionability_score: float
    evidence: list[dict[str, Any]]
    blocks: list[str]
    next_actions: list[str]
    opportunity_ids: list[int]
    source_ids: list[str]

    @property
    def fingerprint(self) -> str:
        payload = "|".join(
            [
                self.rule_id,
                str(self.entity_id or ""),
                ",".join(str(v) for v in sorted(self.opportunity_ids)),
                ",".join(sorted(self.source_ids)),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


RULE_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "rule_id": "dissolved_unclaimed_asset",
        "anomaly_type": "orphaned_business_asset",
        "description": "A dissolved company and an unclaimed-funds record resolve to the same entity.",
        "minimum_sources": 2,
        "human_gate": True,
    },
    {
        "rule_id": "dissolved_ip_signal",
        "anomaly_type": "dissolved_company_ip",
        "description": "A dissolved company resolves to a separate patent/IP signal.",
        "minimum_sources": 2,
        "human_gate": True,
    },
    {
        "rule_id": "bankruptcy_successor_signal",
        "anomaly_type": "successor_entitlement_candidate",
        "description": "A dissolved entity is linked to a bankruptcy-held or successor-claim payment signal.",
        "minimum_sources": 2,
        "human_gate": True,
    },
    {
        "rule_id": "royalty_reconciliation_signal",
        "anomaly_type": "royalty_metadata_mismatch",
        "description": "Independent royalty/rightsholder systems resolve to the same recording or rightsholder.",
        "minimum_sources": 2,
        "human_gate": True,
    },
    {
        "rule_id": "public_domain_technology_signal",
        "anomaly_type": "lapsed_technology_reuse",
        "description": "A maintenance-fee patent expiration is independently linked to a live commercial/technology signal.",
        "minimum_sources": 2,
        "human_gate": True,
    },
    {
        "rule_id": "cross_source_high_value_signal",
        "anomaly_type": "high_value_cross_source",
        "description": "A high-commercial-score entity is corroborated by three or more independent sources.",
        "minimum_sources": 3,
        "human_gate": True,
    },
    {
        "rule_id": "high_value_identity_gap",
        "anomaly_type": "identity_resolution_gap",
        "description": "A high-value record lacks independent identity corroboration and should be researched before action.",
        "minimum_sources": 1,
        "human_gate": True,
    },
    {
        "rule_id": "changed_high_value_record",
        "anomaly_type": "material_source_change",
        "description": "A commercially significant source record materially changed after initial ingestion.",
        "minimum_sources": 1,
        "human_gate": True,
    },
)


def _as_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


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


def _is_bankruptcy_signal(row: Any) -> bool:
    haystack = " ".join(
        str(row[key] or "")
        for key in ("source_id", "asset_class", "custodian", "title", "legal_model")
    ).lower()
    return "bankrupt" in haystack or row["legal_model"] == "successor_claim"


def _is_royalty_signal(row: Any) -> bool:
    haystack = f"{row['source_id']} {row['asset_class']} {row['title']}".lower()
    return any(token in haystack for token in ("royalty", "soundexchange", "mlc", "unmatched recording"))


def _is_mlc_signal(row: Any) -> bool:
    haystack = f"{row['source_id']} {row['asset_class']} {row['title']}".lower()
    return "mlc" in haystack or "unmatched recording" in haystack


def _is_soundexchange_signal(row: Any) -> bool:
    haystack = f"{row['source_id']} {row['asset_class']} {row['title']}".lower()
    return "soundexchange" in haystack or "unclaimed royalty" in haystack


def _evidence_row(row: Any) -> dict[str, Any]:
    return {
        "opportunity_id": int(row["id"]),
        "source_id": str(row["source_id"]),
        "external_id": str(row["external_id"]),
        "asset_class": str(row["asset_class"]),
        "title": str(row["title"]),
        "owner_name": row["owner_name"],
        "jurisdiction": str(row["jurisdiction"]),
        "face_value": row["face_value"],
        "currency": row["currency"],
        "source_url": str(row["source_url"]),
        "commercial_score": float(row["commercial_score"] or 0),
        "actionability_score": float(row["actionability_score"] or 0),
    }


def _finding(
    *,
    rule_id: str,
    anomaly_type: str,
    title: str,
    summary: str,
    entity_id: int | None,
    rows: list[Any],
    confidence: float,
    severity: float,
    blocks: list[str],
    next_actions: list[str],
    primary_opportunity_id: int | None = None,
) -> Finding:
    commercial = max((float(r["commercial_score"] or 0) for r in rows), default=0.0)
    actionable = max((float(r["actionability_score"] or 0) for r in rows), default=0.0)
    source_ids = sorted({str(r["source_id"]) for r in rows})
    opportunity_ids = sorted({int(r["id"]) for r in rows})
    if primary_opportunity_id is None and opportunity_ids:
        primary_opportunity_id = opportunity_ids[0]
    return Finding(
        rule_id=rule_id,
        anomaly_type=anomaly_type,
        title=title,
        summary=summary,
        entity_id=entity_id,
        primary_opportunity_id=primary_opportunity_id,
        confidence=round(max(0.0, min(1.0, confidence)), 4),
        severity_score=round(max(0.0, min(100.0, severity)), 2),
        commercial_score=round(commercial, 2),
        actionability_score=round(actionable, 2),
        evidence=[_evidence_row(r) for r in rows],
        blocks=sorted(set(blocks + ["human_review_required"])),
        next_actions=list(dict.fromkeys(next_actions + ["human_approval_before_outreach_or_filing"])),
        opportunity_ids=opportunity_ids,
        source_ids=source_ids,
    )


def _entity_rows(conn, entity_id: int) -> list[Any]:
    return list(
        conn.execute(
            """
            SELECT DISTINCT o.*,c.lane,c.commercial_score,c.actionability_score,
                   c.evidence_confidence,c.independent_source_count,c.block_json
            FROM entity_memberships m
            JOIN opportunities o ON o.id=m.opportunity_id
            LEFT JOIN commercial_assessments c ON c.opportunity_id=o.id
            WHERE m.entity_id=?
            ORDER BY o.id
            """,
            (entity_id,),
        )
    )


def _entity_confidence(conn, entity_id: int) -> float:
    row = conn.execute("SELECT confidence FROM entities WHERE id=?", (entity_id,)).fetchone()
    return float(row["confidence"] if row else 0.0)


def _compound_findings(conn) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    entity_ids = [int(r["id"]) for r in conn.execute("SELECT id FROM entities ORDER BY id")]
    for entity_id in entity_ids:
        rows = _entity_rows(conn, entity_id)
        if not rows:
            continue
        sources = {str(r["source_id"]) for r in rows}
        classes = {str(r["asset_class"]) for r in rows}
        conf = _entity_confidence(conn, entity_id)
        display = conn.execute("SELECT display_name FROM entities WHERE id=?", (entity_id,)).fetchone()[0]

        dissolved = [r for r in rows if r["asset_class"] in {"dissolved_company", "dissolved_company_signal"}]
        unclaimed = [r for r in rows if r["asset_class"] in {"unclaimed_funds", "unclaimed_property"}]
        ip = [
            r
            for r in rows
            if r["asset_class"]
            in {"patent_license_offer", "patent_expiration", "federal_license_notice", "intellectual_property"}
        ]

        if dissolved and unclaimed and len(sources) >= 2:
            selected = dissolved + unclaimed
            findings.append(
                _finding(
                    rule_id="dissolved_unclaimed_asset",
                    anomaly_type="orphaned_business_asset",
                    title=f"Dissolved entity with unclaimed asset: {display}",
                    summary=(
                        "Independent public records connect a dissolved entity to unclaimed funds. "
                        "This is a successor/restoration/entitlement research lead, not proof that a third party owns the funds."
                    ),
                    entity_id=entity_id,
                    rows=selected,
                    confidence=min(0.99, conf + 0.04),
                    severity=86 + min(8, 2 * (len(sources) - 2)),
                    blocks=["successor_or_restoration_path_required", "entitlement_not_established"],
                    next_actions=[
                        "verify_current_dissolution_status",
                        "verify_unclaimed_asset_custodian_record",
                        "research_successor_merger_restoration_or_shareholder_chain",
                        "obtain_jurisdiction_specific_legal_review",
                    ],
                )
            )

        if dissolved and ip and len({str(r["source_id"]) for r in dissolved + ip}) >= 2:
            selected = dissolved + ip
            findings.append(
                _finding(
                    rule_id="dissolved_ip_signal",
                    anomaly_type="dissolved_company_ip",
                    title=f"Dissolved entity with separate IP signal: {display}",
                    summary=(
                        "A dissolved-company record correlates with an independent patent/IP signal. "
                        "Ownership, restoration, assignment, Crown/bona-vacantia status, and current enforceability must be verified."
                    ),
                    entity_id=entity_id,
                    rows=selected,
                    confidence=min(0.98, conf + 0.02),
                    severity=80 + min(10, len(ip) * 2),
                    blocks=["ip_title_review_required", "current_owner_not_established"],
                    next_actions=[
                        "verify_ip_identifier_and_current_status",
                        "trace_assignment_or_successor_chain",
                        "determine_dissolution_jurisdiction_and_asset_disposition",
                        "obtain_independent_valuation_before_any_acquisition",
                    ],
                )
            )

        bankruptcy = [r for r in rows if _is_bankruptcy_signal(r)]
        if dissolved and bankruptcy and len({str(r["source_id"]) for r in dissolved + bankruptcy}) >= 2:
            selected = dissolved + bankruptcy
            findings.append(
                _finding(
                    rule_id="bankruptcy_successor_signal",
                    anomaly_type="successor_entitlement_candidate",
                    title=f"Potential successor-claim chain: {display}",
                    summary=(
                        "A dissolved entity correlates with a bankruptcy-held/successor-claim signal. "
                        "Federal courts may recognize successor claimants through assignment, purchase, merger, acquisition, or succession, but documentation is required."
                    ),
                    entity_id=entity_id,
                    rows=selected,
                    confidence=min(0.99, conf + 0.03),
                    severity=90,
                    blocks=["chain_of_ownership_required", "court_entitlement_review_required"],
                    next_actions=[
                        "verify_court_unclaimed_funds_record",
                        "identify_owner_of_record",
                        "document_assignment_merger_acquisition_or_succession_chain",
                        "review_local_court_application_requirements",
                    ],
                )
            )

        royalty = [r for r in rows if _is_royalty_signal(r)]
        mlc = [r for r in royalty if _is_mlc_signal(r)]
        sx = [r for r in royalty if _is_soundexchange_signal(r)]
        if royalty and len({str(r["source_id"]) for r in royalty}) >= 2 and (mlc or sx):
            findings.append(
                _finding(
                    rule_id="royalty_reconciliation_signal",
                    anomaly_type="royalty_metadata_mismatch",
                    title=f"Cross-system royalty reconciliation lead: {display}",
                    summary=(
                        "Independent royalty/rightsholder data resolves to the same entity or recording. "
                        "The commercial lane is metadata reconciliation/intelligence; royalties remain payable only to the entitled rightsholder or permitted payee."
                    ),
                    entity_id=entity_id,
                    rows=royalty,
                    confidence=min(0.98, conf + 0.02),
                    severity=82,
                    blocks=["rightsholder_entitlement_required", "no_third_party_royalty_claim"],
                    next_actions=[
                        "verify_isrc_and_recording_metadata",
                        "compare_rightsholder_work_and_recording_metadata",
                        "prepare_non_sensitive_reconciliation_report",
                    ],
                )
            )

        expirations = [r for r in rows if r["asset_class"] == "patent_expiration"]
        live_signals = [
            r
            for r in rows
            if r["asset_class"]
            in {"federal_license_notice", "patent_license_offer", "contract_award", "market_signal"}
        ]
        if expirations and live_signals and len({str(r["source_id"]) for r in expirations + live_signals}) >= 2:
            selected = expirations + live_signals
            findings.append(
                _finding(
                    rule_id="public_domain_technology_signal",
                    anomaly_type="lapsed_technology_reuse",
                    title=f"Lapsed-patent technology with live commercial signal: {display}",
                    summary=(
                        "A maintenance-fee expiration is correlated with another live technology/commercial signal. "
                        "This is a research lead only because patents can sometimes be reinstated and other family claims may remain in force."
                    ),
                    entity_id=entity_id,
                    rows=selected,
                    confidence=min(0.98, conf + 0.01),
                    severity=78,
                    blocks=["patent_status_recheck_required", "family_and_freedom_to_operate_review_required"],
                    next_actions=[
                        "recheck_uspto_maintenance_and_reinstatement_status",
                        "map_patent_family_and_continuations",
                        "assess_current_market_relevance",
                        "obtain_freedom_to_operate_review_before_product_use",
                    ],
                )
            )

        best_commercial = max((float(r["commercial_score"] or 0) for r in rows), default=0.0)
        if len(sources) >= 3 and best_commercial >= 75:
            findings.append(
                _finding(
                    rule_id="cross_source_high_value_signal",
                    anomaly_type="high_value_cross_source",
                    title=f"High-value multi-source entity: {display}",
                    summary=(
                        f"The same resolved entity appears across {len(sources)} independent sources and has a commercial score of {best_commercial:.1f}. "
                        "This is a prioritization signal, not an entitlement conclusion."
                    ),
                    entity_id=entity_id,
                    rows=rows,
                    confidence=conf,
                    severity=min(96.0, 74.0 + len(sources) * 4.0),
                    blocks=["case_specific_entitlement_and_compliance_review_required"],
                    next_actions=[
                        "review_full_evidence_graph",
                        "identify_lowest_friction_lawful_commercial_lane",
                        "verify_each_source_record_independently",
                    ],
                )
            )

    return findings, len(entity_ids)


def _opportunity_findings(conn) -> list[Finding]:
    findings: list[Finding] = []
    rows = list(
        conn.execute(
            """
            SELECT o.*,c.lane,c.commercial_score,c.actionability_score,c.evidence_confidence,
                   c.independent_source_count,c.block_json,
                   v.change_count,v.last_changed_at
            FROM opportunities o
            LEFT JOIN commercial_assessments c ON c.opportunity_id=o.id
            LEFT JOIN opportunity_versions v ON v.source_id=o.source_id AND v.external_id=o.external_id
            ORDER BY o.id
            """
        )
    )
    for row in rows:
        value = _as_decimal(row["face_value"])
        source_count = int(row["independent_source_count"] or 1)
        blocks = _json_list(row["block_json"])
        commercial = float(row["commercial_score"] or 0)

        if value is not None and value >= Decimal("10000") and source_count <= 1 and "identity_not_independently_corroborated" in blocks:
            findings.append(
                _finding(
                    rule_id="high_value_identity_gap",
                    anomaly_type="identity_resolution_gap",
                    title=f"High-value record needs identity corroboration: {row['title']}",
                    summary=(
                        "The source reports a material face value but the current graph has only one independent identity source. "
                        "Prioritize corroboration before outreach, acquisition, or filing."
                    ),
                    entity_id=None,
                    rows=[row],
                    confidence=float(row["evidence_confidence"] or 0.35),
                    severity=min(92.0, 65.0 + float(min(value, Decimal("250000")) / Decimal("10000"))),
                    blocks=["identity_not_independently_corroborated"],
                    next_actions=["obtain_second_independent_identity_signal", "verify_owner_or_successor_identity"],
                    primary_opportunity_id=int(row["id"]),
                )
            )

        if int(row["change_count"] or 0) > 0 and commercial >= 70:
            findings.append(
                _finding(
                    rule_id="changed_high_value_record",
                    anomaly_type="material_source_change",
                    title=f"Material source record changed: {row['title']}",
                    summary=(
                        "A commercially significant record changed after initial ingestion. "
                        "Re-verify the official record before relying on prior entitlement, value, deadline, or ownership assumptions."
                    ),
                    entity_id=None,
                    rows=[row],
                    confidence=float(row["evidence_confidence"] or 0.7),
                    severity=min(95.0, 70.0 + min(20.0, int(row["change_count"]) * 5.0)),
                    blocks=["source_record_reverification_required"],
                    next_actions=["compare_current_and_prior_source_record", "recompute_case_after_verification"],
                    primary_opportunity_id=int(row["id"]),
                )
            )
    return findings


def detect_anomalies(db: Database) -> AnomalyStats:
    """Detect compound anomalies from already-ingested official/public records.

    Findings are research triage signals only. The engine never infers ownership or entitlement from
    correlation and never authorizes automated claimant outreach, claim filing, or asset acquisition.
    """
    db.init()
    now = datetime.now(timezone.utc).isoformat()
    with db.connect() as conn:
        compound, entities_scanned = _compound_findings(conn)
        per_opportunity = _opportunity_findings(conn)
        findings = compound + per_opportunity

        # Findings that disappear from the current evidence graph become stale. Confirmed/dismissed
        # analyst decisions are preserved for auditability.
        conn.execute("UPDATE anomaly_findings SET state='stale' WHERE state='open'")
        for finding in findings:
            conn.execute(
                """
                INSERT INTO anomaly_findings(
                  fingerprint,rule_id,anomaly_type,title,summary,entity_id,primary_opportunity_id,
                  confidence,severity_score,commercial_score,actionability_score,evidence_json,
                  block_json,next_action_json,opportunity_ids_json,source_ids_json,state,
                  first_detected_at,last_detected_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                  title=excluded.title,summary=excluded.summary,entity_id=excluded.entity_id,
                  primary_opportunity_id=excluded.primary_opportunity_id,confidence=excluded.confidence,
                  severity_score=excluded.severity_score,commercial_score=excluded.commercial_score,
                  actionability_score=excluded.actionability_score,evidence_json=excluded.evidence_json,
                  block_json=excluded.block_json,next_action_json=excluded.next_action_json,
                  opportunity_ids_json=excluded.opportunity_ids_json,source_ids_json=excluded.source_ids_json,
                  state=CASE WHEN anomaly_findings.state IN ('dismissed','confirmed')
                             THEN anomaly_findings.state ELSE 'open' END,
                  last_detected_at=excluded.last_detected_at
                """,
                (
                    finding.fingerprint,
                    finding.rule_id,
                    finding.anomaly_type,
                    finding.title,
                    finding.summary,
                    finding.entity_id,
                    finding.primary_opportunity_id,
                    finding.confidence,
                    finding.severity_score,
                    finding.commercial_score,
                    finding.actionability_score,
                    json.dumps(finding.evidence, ensure_ascii=False, sort_keys=True),
                    json.dumps(finding.blocks, sort_keys=True),
                    json.dumps(finding.next_actions, sort_keys=True),
                    json.dumps(finding.opportunity_ids),
                    json.dumps(finding.source_ids),
                    "open",
                    now,
                    now,
                ),
            )
        conn.commit()
        return AnomalyStats(
            findings=len(findings),
            entities_scanned=entities_scanned,
            opportunity_findings=len(per_opportunity),
        )
