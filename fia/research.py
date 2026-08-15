from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import load_settings
from .db import Database
from .sources.companies_house import CompaniesHouseClient


@dataclass(frozen=True)
class ResearchStats:
    tasks: int
    anomalies_scanned: int
    stale_marked: int


@dataclass(frozen=True)
class TaskSpec:
    anomaly_id: int | None
    entity_id: int | None
    opportunity_id: int | None
    task_type: str
    title: str
    rationale: str
    target_type: str
    target_value: str
    expected_relation_type: str | None
    source_id: str | None
    source_url: str | None
    access_mode: str
    estimated_effort: str
    expected_uplift: float
    confidence: float
    priority_score: float
    resolves_blockers: tuple[str, ...]
    prerequisites: tuple[str, ...]
    blocks: tuple[str, ...]
    params: dict[str, Any]

    @property
    def fingerprint(self) -> str:
        raw = "|".join(
            [
                str(self.anomaly_id or ""),
                str(self.entity_id or ""),
                str(self.opportunity_id or ""),
                self.task_type,
                self.target_type,
                self.target_value,
                self.source_id or "",
            ]
        )
        return hashlib.sha256(raw.encode()).hexdigest()


TASK_CATALOG: tuple[dict[str, str], ...] = (
    {"task_type": "verify_source_record", "execution": "manual_or_source_specific", "description": "Re-open the authoritative record and verify it is current."},
    {"task_type": "companies_house_profile", "execution": "read_only_api", "description": "Fetch official company profile, prior names, status and office metadata."},
    {"task_type": "companies_house_filing_history", "execution": "read_only_api", "description": "Fetch filing history for dissolution/restoration/name-change evidence."},
    {"task_type": "companies_house_officers", "execution": "read_only_api", "description": "Fetch company officers as research pivots, not ownership proof."},
    {"task_type": "companies_house_psc", "execution": "read_only_api", "description": "Fetch persons with significant control as corporate-control evidence."},
    {"task_type": "companies_house_insolvency", "execution": "read_only_api", "description": "Fetch official insolvency data where available."},
    {"task_type": "companies_house_officer_appointments", "execution": "read_only_api", "description": "Follow an official officer identifier to other company appointments."},
    {"task_type": "uspto_assignment_lookup", "execution": "credential_gated", "description": "Trace patent assignment history through USPTO Open Data Portal."},
    {"task_type": "patent_status_check", "execution": "credential_or_manual", "description": "Re-check current patent/maintenance status."},
    {"task_type": "patent_family_review", "execution": "human_review", "description": "Map continuations/family members and surviving claims."},
    {"task_type": "successor_chain_research", "execution": "human_review", "description": "Build a documented merger/acquisition/assignment/restoration chain."},
    {"task_type": "court_record_verification", "execution": "manual_captcha_gate", "description": "Verify court-held funds through the court-permitted interface/export."},
    {"task_type": "dissolution_asset_disposition_review", "execution": "legal_review", "description": "Determine the jurisdictional disposition of residual company assets."},
    {"task_type": "independent_identity_corroboration", "execution": "human_review", "description": "Find a second authoritative identity signal."},
    {"task_type": "mlc_recording_lookup", "execution": "enrollment_gated", "description": "Use authorized MLC access for recording/work metadata."},
    {"task_type": "soundexchange_rightsholder_lookup", "execution": "public_manual", "description": "Check SoundExchange public rightsholder/creator status."},
    {"task_type": "royalty_metadata_reconciliation", "execution": "human_review", "description": "Produce a non-sensitive cross-system royalty metadata discrepancy report."},
    {"task_type": "market_relevance_check", "execution": "public_intelligence", "description": "Check current procurement/licensing/market demand for a technology."},
    {"task_type": "source_change_review", "execution": "human_review", "description": "Review a material source change and its commercial impact."},
)

EFFORT_PENALTY = {"low": 0.0, "medium": 4.0, "high": 9.0}
ACCESS_PENALTY = {
    "public_api": 0.0,
    "api_key": 2.0,
    "account_api_key": 4.0,
    "public_manual": 3.0,
    "human_review": 5.0,
    "enrollment_required": 7.0,
    "manual_captcha": 9.0,
    "legal_review": 10.0,
}


def _priority(anomaly: Any, uplift: float, effort: str, access: str) -> float:
    raw = (
        0.33 * float(anomaly["severity_score"] or 0)
        + 0.22 * float(anomaly["actionability_score"] or 0)
        + 0.15 * float(anomaly["confidence"] or 0) * 100
        + 0.30 * min(100.0, uplift * 4)
        - EFFORT_PENALTY.get(effort, 5.0)
        - ACCESS_PENALTY.get(access, 5.0)
    )
    return round(max(0.0, min(100.0, raw)), 2)


def _task(
    anomaly: Any,
    *,
    task_type: str,
    title: str,
    rationale: str,
    target_type: str,
    target_value: str,
    source_id: str | None = None,
    source_url: str | None = None,
    expected_relation_type: str | None = None,
    access: str = "human_review",
    effort: str = "medium",
    uplift: float = 12.0,
    resolves: tuple[str, ...] = (),
    prerequisites: tuple[str, ...] = (),
    blocks: tuple[str, ...] = (),
    params: dict[str, Any] | None = None,
    opportunity_id: int | None = None,
) -> TaskSpec:
    return TaskSpec(
        anomaly_id=int(anomaly["id"]) if anomaly["id"] is not None else None,
        entity_id=int(anomaly["entity_id"]) if anomaly["entity_id"] is not None else None,
        opportunity_id=opportunity_id,
        task_type=task_type,
        title=title,
        rationale=rationale,
        target_type=target_type,
        target_value=target_value,
        expected_relation_type=expected_relation_type,
        source_id=source_id,
        source_url=source_url,
        access_mode=access,
        estimated_effort=effort,
        expected_uplift=uplift,
        confidence=float(anomaly["confidence"] or 0),
        priority_score=_priority(anomaly, uplift, effort, access),
        resolves_blockers=tuple(sorted(set(resolves))),
        prerequisites=tuple(prerequisites),
        blocks=tuple(sorted(set(blocks))),
        params=params or {},
    )


def _identifiers(conn, entity_id: int | None) -> dict[str, list[str]]:
    found: dict[str, set[str]] = {"company_number": set(), "patent_number": set(), "isrc": set(), "name": set()}
    if not entity_id:
        return {k: [] for k in found}
    rows = conn.execute(
        """
        SELECT e.id,e.canonical_key,e.display_name FROM entities e WHERE e.id=?
        UNION
        SELECT other.id,other.canonical_key,other.display_name
        FROM entity_relations r
        JOIN entities other ON other.id=CASE WHEN r.left_entity_id=? THEN r.right_entity_id ELSE r.left_entity_id END
        WHERE r.left_entity_id=? OR r.right_entity_id=?
        """,
        (entity_id, entity_id, entity_id, entity_id),
    )
    for row in rows:
        key = str(row["canonical_key"])
        if key.startswith("company_number:"):
            found["company_number"].add(key.split(":", 1)[1])
        elif key.startswith("patent_number:"):
            found["patent_number"].add(key.split(":", 1)[1])
        elif key.startswith("isrc:"):
            found["isrc"].add(key.split(":", 1)[1])
        elif key.startswith("name:"):
            found["name"].add(str(row["display_name"]))
    return {k: sorted(v) for k, v in found.items()}


def _company_tasks(anomaly: Any, company_numbers: list[str]) -> list[TaskSpec]:
    tasks: list[TaskSpec] = []
    for number in company_numbers:
        common = dict(
            target_type="company_number",
            target_value=number,
            source_id="companies_house",
            source_url="https://developer.company-information.service.gov.uk/",
            access="api_key",
            params={"company_number": number},
        )
        tasks.extend(
            [
                _task(anomaly, **common, task_type="companies_house_profile", title=f"Fetch Companies House profile: {number}", rationale="Current status, prior names and office metadata can close identity and dissolution-history gaps.", expected_relation_type="official_company_profile", effort="low", uplift=14, resolves=("identity_not_independently_corroborated", "successor_or_restoration_path_required")),
                _task(anomaly, **common, task_type="companies_house_filing_history", title=f"Fetch filing history: {number}", rationale="Filings can reveal dissolution, restoration, name changes and corporate events relevant to succession.", expected_relation_type="corporate_event_history", effort="low", uplift=18, resolves=("successor_or_restoration_path_required", "chain_of_ownership_required")),
                _task(anomaly, **common, task_type="companies_house_psc", title=f"Fetch persons with significant control: {number}", rationale="PSC data supplies a high-signal corporate-control research pivot without establishing entitlement.", expected_relation_type="controlled_by", effort="low", uplift=15, resolves=("identity_not_independently_corroborated",)),
                _task(anomaly, **common, task_type="companies_house_officers", title=f"Fetch officers: {number}", rationale="Officer history can identify people/entities worth checking in a documented successor chain.", expected_relation_type="officer_of", effort="low", uplift=11),
                _task(anomaly, **common, task_type="companies_house_insolvency", title=f"Fetch insolvency status: {number}", rationale="Insolvency data can identify the proceeding or officeholder that controlled residual assets.", expected_relation_type="insolvency_path", effort="low", uplift=16, resolves=("successor_or_restoration_path_required",)),
            ]
        )
    return tasks


def _patent_tasks(anomaly: Any, patent_numbers: list[str]) -> list[TaskSpec]:
    tasks: list[TaskSpec] = []
    for patent in patent_numbers:
        tasks.extend(
            [
                _task(anomaly, task_type="uspto_assignment_lookup", title=f"Trace patent assignments: {patent}", rationale="Assignment history is the missing edge between the IP record and a present owner/successor.", target_type="patent_number", target_value=patent, source_id="uspto_open_data", source_url="https://data.uspto.gov/", expected_relation_type="assigned_to", access="account_api_key", effort="medium", uplift=22, resolves=("ip_title_review_required", "current_owner_not_established", "chain_of_ownership_required"), params={"patent_number": patent}),
                _task(anomaly, task_type="patent_status_check", title=f"Re-check patent status: {patent}", rationale="A maintenance-fee lapse can sometimes be reversed and must be checked before public-domain inference.", target_type="patent_number", target_value=patent, source_id="uspto_open_data", source_url="https://data.uspto.gov/", expected_relation_type="current_patent_status", access="account_api_key", effort="low", uplift=19, resolves=("patent_status_recheck_required",), params={"patent_number": patent}),
                _task(anomaly, task_type="patent_family_review", title=f"Map surviving patent family: {patent}", rationale="Continuations or related claims may survive even when one patent lapses.", target_type="patent_number", target_value=patent, source_id="uspto_open_data", source_url="https://data.uspto.gov/", expected_relation_type="patent_family_member", access="human_review", effort="high", uplift=17, resolves=("family_and_freedom_to_operate_review_required",), params={"patent_number": patent}),
            ]
        )
    return tasks


def _plan_one(conn, anomaly: Any) -> list[TaskSpec]:
    tasks: list[TaskSpec] = []
    anomaly_type = str(anomaly["anomaly_type"])
    ids = _identifiers(conn, int(anomaly["entity_id"]) if anomaly["entity_id"] else None)
    evidence = json.loads(anomaly["evidence_json"] or "[]")

    # Cheapest safeguard: re-open every authoritative source record in the finding.
    for ev in evidence:
        sid = str(ev.get("source_id") or "")
        external = str(ev.get("external_id") or "")
        if not sid or not external:
            continue
        tasks.append(
            _task(
                anomaly,
                task_type="verify_source_record",
                title=f"Verify source record: {sid} / {external}",
                rationale="Confirm the authoritative record still exists and materially matches stored evidence.",
                target_type="source_record",
                target_value=f"{sid}:{external}",
                source_id=sid,
                source_url=str(ev.get("source_url") or "") or None,
                access="manual_captcha" if sid == "us_bankruptcy_unclaimed" else "public_manual",
                effort="low",
                uplift=8,
                opportunity_id=int(ev["opportunity_id"]) if ev.get("opportunity_id") else None,
                params={"external_id": external},
            )
        )

    display = ids["name"][0] if ids["name"] else str(anomaly["title"])

    if anomaly_type in {"orphaned_business_asset", "dissolved_company_ip", "successor_entitlement_candidate"}:
        tasks += _company_tasks(anomaly, ids["company_number"])
    if anomaly_type in {"dissolved_company_ip", "lapsed_technology_reuse"}:
        tasks += _patent_tasks(anomaly, ids["patent_number"])

    if anomaly_type == "orphaned_business_asset":
        tasks += [
            _task(anomaly, task_type="successor_chain_research", title=f"Research successor/restoration chain: {display}", rationale="The case becomes actionable only if a documented owner/successor/restoration pathway exists.", target_type="entity", target_value=display, expected_relation_type="successor_of", access="human_review", effort="high", uplift=25, resolves=("successor_or_restoration_path_required", "entitlement_not_established", "chain_of_ownership_required")),
            _task(anomaly, task_type="dissolution_asset_disposition_review", title=f"Review residual-asset law: {display}", rationale="Determine whether residual assets passed to a sovereign, shareholder, liquidator, successor or restored entity.", target_type="entity", target_value=display, expected_relation_type="residual_asset_disposition", access="legal_review", effort="high", uplift=20, resolves=("successor_or_restoration_path_required", "entitlement_not_established")),
        ]
    elif anomaly_type == "dissolved_company_ip":
        tasks.append(_task(anomaly, task_type="dissolution_asset_disposition_review", title=f"Review dissolved-company IP disposition: {display}", rationale="Determine whether the IP passed by assignment, restoration, liquidation or bona vacantia before any acquisition decision.", target_type="entity", target_value=display, expected_relation_type="ip_disposition", access="legal_review", effort="high", uplift=22, resolves=("ip_title_review_required", "current_owner_not_established")))
    elif anomaly_type == "successor_entitlement_candidate":
        tasks += [
            _task(anomaly, task_type="court_record_verification", title=f"Verify court-held funds record: {display}", rationale="Court records control the owner-of-record identity and local application requirements.", target_type="entity", target_value=display, source_id="us_bankruptcy_unclaimed", source_url="https://ucf.uscourts.gov/", expected_relation_type="court_owner_of_record", access="manual_captcha", effort="medium", uplift=18, resolves=("court_entitlement_review_required",)),
            _task(anomaly, task_type="successor_chain_research", title=f"Build chain of ownership: {display}", rationale="Bankruptcy courts require documentation sufficient to establish succession or transfer from the owner of record.", target_type="entity", target_value=display, expected_relation_type="successor_of", access="human_review", effort="high", uplift=28, resolves=("chain_of_ownership_required", "court_entitlement_review_required"), prerequisites=("verify_owner_of_record",)),
        ]
    elif anomaly_type == "royalty_metadata_mismatch":
        for isrc in ids["isrc"]:
            tasks += [
                _task(anomaly, task_type="mlc_recording_lookup", title=f"Check MLC metadata: {isrc}", rationale="Authorized MLC data can explain work/recording ownership mismatches.", target_type="isrc", target_value=isrc, source_id="mlc_data", source_url="https://www.themlc.com/dataprograms", expected_relation_type="recording_to_work", access="enrollment_required", effort="low", uplift=18, resolves=("rightsholder_entitlement_required",), params={"isrc": isrc}),
                _task(anomaly, task_type="soundexchange_rightsholder_lookup", title=f"Check SoundExchange status: {isrc}", rationale="A public creator/rightsholder check provides an independent reconciliation signal.", target_type="isrc", target_value=isrc, source_id="soundexchange_unclaimed", source_url="https://www.soundexchange.com/what-we-do/for-artists-labels-and-producers/", expected_relation_type="recording_rightsholder", access="public_manual", effort="low", uplift=14, resolves=("rightsholder_entitlement_required",), params={"isrc": isrc}),
            ]
        tasks.append(_task(anomaly, task_type="royalty_metadata_reconciliation", title=f"Reconcile royalty metadata: {display}", rationale="Combine independent work, recording and rightsholder metadata into a discrepancy report without claiming royalties.", target_type="entity", target_value=display, expected_relation_type="metadata_discrepancy_resolved", access="human_review", effort="medium", uplift=22, prerequisites=("collect_independent_metadata",), blocks=("no_third_party_royalty_claim",)))
    elif anomaly_type == "lapsed_technology_reuse":
        tasks.append(_task(anomaly, task_type="market_relevance_check", title=f"Check current market demand: {display}", rationale="A lapsed technology is only commercially interesting if independent market/procurement signals show current demand.", target_type="entity", target_value=display, source_id="usaspending", source_url="https://api.usaspending.gov/", expected_relation_type="current_market_signal", access="public_api", effort="medium", uplift=15))
    elif anomaly_type == "identity_resolution_gap":
        tasks.append(_task(anomaly, task_type="independent_identity_corroboration", title=f"Find second authoritative identity signal: {display}", rationale="Material value exists but the graph lacks enough independent identity evidence for safe action.", target_type="entity", target_value=display, expected_relation_type="corroborates_identity", access="human_review", effort="medium", uplift=26, resolves=("identity_not_independently_corroborated",)))
    elif anomaly_type == "material_source_change":
        tasks.append(_task(anomaly, task_type="source_change_review", title=f"Review material source change: {display}", rationale="A changed high-value record may alter urgency, ownership, availability or the best commercial lane.", target_type="entity", target_value=display, expected_relation_type="source_change_explained", access="human_review", effort="low", uplift=13))
    elif anomaly_type == "high_value_cross_source":
        tasks.append(_task(anomaly, task_type="independent_identity_corroboration", title=f"Validate weakest identity edge: {display}", rationale="Confirm the weakest identity edge before choosing the commercial lane.", target_type="entity", target_value=display, expected_relation_type="corroborates_identity", access="human_review", effort="medium", uplift=18))

    return tasks


def _recursive_fact_tasks(conn, anomaly: Any) -> list[TaskSpec]:
    """Generate bounded follow-up tasks from already-assimilated research facts."""
    tasks: list[TaskSpec] = []
    anomaly_id = int(anomaly["id"])
    rows = list(conn.execute(
        """
        SELECT rf.fact_type,rf.object_canonical_key,rf.object_display_name,rf.evidence_json,rt.task_type
        FROM research_facts rf JOIN research_tasks rt ON rt.id=rf.task_id
        WHERE rt.anomaly_id=? ORDER BY rf.id
        """,
        (anomaly_id,),
    ))
    seen_officers: set[str] = set()
    seen_companies: set[str] = set()
    for row in rows:
        try:
            evidence = json.loads(row["evidence_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            evidence = {}
        if row["fact_type"] == "company_officer":
            officer_id = str(evidence.get("officer_id") or "").strip()
            if officer_id and officer_id not in seen_officers:
                seen_officers.add(officer_id)
                tasks.append(_task(
                    anomaly,
                    task_type="companies_house_officer_appointments",
                    title=f"Follow officer appointments: {row['object_display_name'] or officer_id}",
                    rationale="Official appointment history can reveal successor, related, or restored companies worth corroborating. It is a research pivot, not ownership proof.",
                    target_type="officer_id", target_value=officer_id,
                    source_id="companies_house", source_url="https://developer.company-information.service.gov.uk/",
                    expected_relation_type="appointed_to_company", access="api_key", effort="low", uplift=12,
                    params={"officer_id": officer_id},
                ))
        elif row["fact_type"] in {"officer_appointment", "psc_registration_number"}:
            key = str(row["object_canonical_key"] or "")
            if key.startswith("company_number:"):
                number = key.split(":", 1)[1].strip().upper()
                # Companies House numbers are 8 characters, commonly 8 digits or a two-letter prefix + 6 digits.
                if len(number) == 8 and number.isalnum() and number not in seen_companies:
                    seen_companies.add(number)
                    tasks.append(_task(
                        anomaly,
                        task_type="companies_house_profile",
                        title=f"Corroborate linked company profile: {number}",
                        rationale="A prior research result surfaced another UK company identifier. Fetch its official profile before treating the relationship as meaningful.",
                        target_type="company_number", target_value=number,
                        source_id="companies_house", source_url="https://developer.company-information.service.gov.uk/",
                        expected_relation_type="official_company_profile", access="api_key", effort="low", uplift=13,
                        params={"company_number": number},
                    ))
    return tasks


def plan_research(db: Database, *, include_confirmed: bool = True) -> ResearchStats:
    """Generate a persistent ranked research queue. No outreach, claim, filing, purchase or bypass occurs."""
    db.init()
    now = datetime.now(timezone.utc).isoformat()
    with db.connect() as conn:
        states = ("open", "confirmed") if include_confirmed else ("open",)
        placeholders = ",".join("?" for _ in states)
        anomalies = list(conn.execute(f"SELECT * FROM anomaly_findings WHERE state IN ({placeholders}) ORDER BY severity_score DESC,id", states))
        planned: list[TaskSpec] = []
        for anomaly in anomalies:
            planned += _plan_one(conn, anomaly)
            planned += _recursive_fact_tasks(conn, anomaly)

        stale = conn.execute("UPDATE research_tasks SET state='stale', last_planned_at=? WHERE state IN ('pending','blocked')", (now,)).rowcount
        for t in planned:
            conn.execute(
                """
                INSERT INTO research_tasks(
                  fingerprint,anomaly_id,entity_id,opportunity_id,task_type,title,rationale,target_type,target_value,
                  expected_relation_type,source_id,source_url,access_mode,estimated_effort,expected_uplift,confidence,
                  priority_score,resolves_blockers_json,prerequisites_json,block_json,params_json,state,result_json,
                  first_planned_at,last_planned_at,completed_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',NULL,?,?,NULL)
                ON CONFLICT(fingerprint) DO UPDATE SET
                  title=excluded.title,rationale=excluded.rationale,expected_relation_type=excluded.expected_relation_type,
                  source_id=excluded.source_id,source_url=excluded.source_url,access_mode=excluded.access_mode,
                  estimated_effort=excluded.estimated_effort,expected_uplift=excluded.expected_uplift,
                  confidence=excluded.confidence,priority_score=excluded.priority_score,
                  resolves_blockers_json=excluded.resolves_blockers_json,prerequisites_json=excluded.prerequisites_json,
                  block_json=excluded.block_json,params_json=excluded.params_json,
                  state=CASE WHEN research_tasks.state IN ('completed','dismissed','in_progress') THEN research_tasks.state ELSE 'pending' END,
                  last_planned_at=excluded.last_planned_at
                """,
                (
                    t.fingerprint, t.anomaly_id, t.entity_id, t.opportunity_id, t.task_type, t.title, t.rationale,
                    t.target_type, t.target_value, t.expected_relation_type, t.source_id, t.source_url, t.access_mode,
                    t.estimated_effort, t.expected_uplift, t.confidence, t.priority_score,
                    json.dumps(t.resolves_blockers), json.dumps(t.prerequisites), json.dumps(t.blocks),
                    json.dumps(t.params, sort_keys=True), now, now,
                ),
            )
        conn.commit()
    return ResearchStats(tasks=len(planned), anomalies_scanned=len(anomalies), stale_marked=stale)


def execute_task(db: Database, task_id: int) -> dict[str, Any]:
    """Execute only whitelisted read-only Companies House API tasks."""
    case = db.research_task_case(task_id)
    if case is None:
        raise ValueError(f"Unknown research task id: {task_id}")
    task_type = str(case["task_type"])
    allowed = {"companies_house_profile", "companies_house_filing_history", "companies_house_officers", "companies_house_psc", "companies_house_insolvency", "companies_house_officer_appointments"}
    if task_type not in allowed:
        raise ValueError(f"Task type {task_type!r} is not auto-executable; use its official/manual review path")
    settings = load_settings()
    if not settings.companies_house_api_key:
        raise ValueError("Set COMPANIES_HOUSE_API_KEY before executing Companies House research tasks")
    params = case.get("params") or {}
    company_number = str(params.get("company_number") or case["target_value"])
    officer_id = str(params.get("officer_id") or case["target_value"])
    with httpx.Client(timeout=30, headers={"User-Agent": "ForgottenAssetIntelligence/1.0"}) as client:
        ch = CompaniesHouseClient(settings.companies_house_api_key, client)
        methods = {
            "companies_house_profile": ch.company_profile,
            "companies_house_filing_history": ch.filing_history,
            "companies_house_officers": ch.officers,
            "companies_house_psc": ch.persons_with_significant_control,
            "companies_house_insolvency": ch.insolvency,
            "companies_house_officer_appointments": ch.officer_appointments,
        }
        try:
            target = officer_id if task_type == "companies_house_officer_appointments" else company_number
            result = methods[task_type](target)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                result = {
                    "company_number": company_number if task_type != "companies_house_officer_appointments" else None,
                    "officer_id": officer_id if task_type == "companies_house_officer_appointments" else None,
                    "task_type": task_type,
                    "not_found": True,
                    "http_status": 404,
                    "meaning": "No resource returned by the official read-only endpoint; treat as negative evidence, not an error-derived entitlement conclusion.",
                }
            else:
                raise
    db.complete_research_task(task_id, result=result)
    return result
