from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from .db import Database
from .keying import classify_entity_name, normalize_name


@dataclass(frozen=True)
class ResearchFact:
    task_id: int
    source_id: str
    fact_type: str
    subject_entity_type: str
    subject_canonical_key: str
    subject_display_name: str
    relation_type: str | None
    object_entity_type: str | None
    object_canonical_key: str | None
    object_display_name: str | None
    confidence: float
    evidence: dict[str, Any]

    @property
    def fingerprint(self) -> str:
        payload = {
            "task_id": self.task_id,
            "source_id": self.source_id,
            "fact_type": self.fact_type,
            "subject_entity_type": self.subject_entity_type,
            "subject_canonical_key": self.subject_canonical_key,
            "relation_type": self.relation_type,
            "object_entity_type": self.object_entity_type,
            "object_canonical_key": self.object_canonical_key,
            "confidence": round(self.confidence, 6),
            "evidence": self.evidence,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FeedbackStats:
    tasks_scanned: int
    tasks_ingested: int
    tasks_unchanged: int
    facts_written: int
    errors: int


def _name_ref(name: str, *, kind: str | None = None) -> tuple[str, str, str] | None:
    display = str(name or "").strip()
    normalized = normalize_name(display)
    if len(normalized) < 3:
        return None
    entity_type = kind or classify_entity_name(display)
    return entity_type, f"name:{normalized}", display


def _company_ref(company_number: str, display: str | None = None) -> tuple[str, str, str]:
    number = str(company_number or "").strip().upper()
    return "organization", f"company_number:{number}", str(display or number)


def _address_ref(address: dict[str, Any]) -> tuple[str, str, str] | None:
    parts = [
        str(address.get(k) or "").strip()
        for k in ("premises", "address_line_1", "address_line_2", "locality", "region", "postal_code", "country")
    ]
    display = ", ".join(v for v in parts if v)
    key = normalize_name(display)
    if len(key) < 5:
        return None
    return "address", f"address:{key}", display


def _event_ref(prefix: str, stable_id: str, display: str) -> tuple[str, str, str]:
    safe = str(stable_id or "").strip()
    if not safe:
        safe = hashlib.sha256(display.encode("utf-8")).hexdigest()[:20]
    return "event", f"{prefix}:{safe}", display


def _fact(
    *,
    task_id: int,
    source_id: str,
    fact_type: str,
    subject: tuple[str, str, str],
    relation_type: str | None = None,
    object_: tuple[str, str, str] | None = None,
    confidence: float = 1.0,
    evidence: dict[str, Any] | None = None,
) -> ResearchFact:
    return ResearchFact(
        task_id=task_id,
        source_id=source_id,
        fact_type=fact_type,
        subject_entity_type=subject[0],
        subject_canonical_key=subject[1],
        subject_display_name=subject[2],
        relation_type=relation_type,
        object_entity_type=object_[0] if object_ else None,
        object_canonical_key=object_[1] if object_ else None,
        object_display_name=object_[2] if object_ else None,
        confidence=max(0.0, min(1.0, float(confidence))),
        evidence=evidence or {},
    )


def _company_number(task: dict[str, Any], result: dict[str, Any]) -> str:
    params = task.get("params") or {}
    return str(result.get("company_number") or params.get("company_number") or task.get("target_value") or "").strip().upper()


def _profile_facts(task: dict[str, Any], result: dict[str, Any]) -> list[ResearchFact]:
    number = _company_number(task, result)
    if not number:
        return []
    source_id = str(task.get("source_id") or "companies_house")
    company_name = str(result.get("company_name") or number).strip()
    subject = _company_ref(number, company_name)
    facts: list[ResearchFact] = []
    name_ref = _name_ref(company_name, kind="organization")
    if name_ref:
        facts.append(_fact(task_id=int(task["id"]), source_id=source_id, fact_type="official_company_name", subject=subject, relation_type="official_name_of", object_=name_ref, confidence=1.0, evidence={"company_status": result.get("company_status")}))

    address = result.get("registered_office_address")
    if isinstance(address, dict):
        addr_ref = _address_ref(address)
        if addr_ref:
            facts.append(_fact(task_id=int(task["id"]), source_id=source_id, fact_type="registered_office", subject=subject, relation_type="registered_office_at", object_=addr_ref, confidence=1.0, evidence={"postal_code": address.get("postal_code")}))

    for prior in result.get("previous_company_names") or []:
        if not isinstance(prior, dict):
            continue
        prior_ref = _name_ref(str(prior.get("name") or ""), kind="organization")
        if prior_ref:
            facts.append(_fact(task_id=int(task["id"]), source_id=source_id, fact_type="previous_company_name", subject=subject, relation_type="previous_company_name_of", object_=prior_ref, confidence=1.0, evidence={"effective_from": prior.get("effective_from"), "ceased_on": prior.get("ceased_on")}))

    status = str(result.get("company_status") or "").strip()
    if status:
        status_ref = ("status", f"company_status:{number}:{normalize_name(status)}", status)
        facts.append(_fact(task_id=int(task["id"]), source_id=source_id, fact_type="company_status", subject=subject, relation_type="has_company_status", object_=status_ref, confidence=1.0, evidence={"date_of_cessation": result.get("date_of_cessation")}))
    return facts


def _filing_facts(task: dict[str, Any], result: dict[str, Any]) -> list[ResearchFact]:
    number = _company_number(task, result)
    if not number:
        return []
    source_id = str(task.get("source_id") or "companies_house")
    subject = _company_ref(number)
    facts: list[ResearchFact] = []
    for index, item in enumerate(result.get("items") or []):
        if not isinstance(item, dict):
            continue
        tx = str(item.get("transaction_id") or f"{number}:{index}")
        description = str(item.get("description") or item.get("type") or "company filing")
        event = _event_ref("company_filing", tx, f"{item.get('date') or ''} {description}".strip())
        evidence = {
            "transaction_id": item.get("transaction_id"),
            "category": item.get("category"),
            "type": item.get("type"),
            "date": item.get("date"),
            "description": item.get("description"),
        }
        facts.append(_fact(task_id=int(task["id"]), source_id=source_id, fact_type="company_filing", subject=subject, relation_type="has_filing_event", object_=event, confidence=1.0, evidence=evidence))
    return facts


def _officer_facts(task: dict[str, Any], result: dict[str, Any]) -> list[ResearchFact]:
    number = _company_number(task, result)
    if not number:
        return []
    source_id = str(task.get("source_id") or "companies_house")
    company = _company_ref(number)
    facts: list[ResearchFact] = []
    for item in result.get("items") or []:
        if not isinstance(item, dict):
            continue
        ref = _name_ref(str(item.get("name") or ""))
        if not ref:
            continue
        links = item.get("links") if isinstance(item.get("links"), dict) else {}
        officer_link = str((links or {}).get("officer", {}).get("appointments") if isinstance((links or {}).get("officer"), dict) else "")
        officer_id = ""
        if "/officers/" in officer_link:
            officer_id = officer_link.split("/officers/", 1)[1].split("/", 1)[0]
        evidence = {
            "officer_role": item.get("officer_role"),
            "appointed_on": item.get("appointed_on"),
            "resigned_on": item.get("resigned_on"),
            "officer_id": officer_id or None,
            "appointments_url": officer_link or None,
        }
        facts.append(_fact(task_id=int(task["id"]), source_id=source_id, fact_type="company_officer", subject=company, relation_type="officer_of", object_=ref, confidence=0.96, evidence=evidence))
    return facts


def _psc_facts(task: dict[str, Any], result: dict[str, Any]) -> list[ResearchFact]:
    number = _company_number(task, result)
    if not number:
        return []
    source_id = str(task.get("source_id") or "companies_house")
    company = _company_ref(number)
    facts: list[ResearchFact] = []
    for item in result.get("items") or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        entity_type = "organization" if "corporate" in kind or "legal-person" in kind else "person"
        ref = _name_ref(str(item.get("name") or ""), kind=entity_type)
        if not ref:
            continue
        identification = item.get("identification") if isinstance(item.get("identification"), dict) else {}
        evidence = {
            "kind": kind,
            "natures_of_control": item.get("natures_of_control") or [],
            "notified_on": item.get("notified_on"),
            "ceased_on": item.get("ceased_on"),
            "registration_number": (identification or {}).get("registration_number"),
            "legal_authority": (identification or {}).get("legal_authority"),
            "country_registered": (identification or {}).get("country_registered"),
        }
        facts.append(_fact(task_id=int(task["id"]), source_id=source_id, fact_type="person_with_significant_control", subject=company, relation_type="controlled_by", object_=ref, confidence=0.98, evidence=evidence))
        reg = str((identification or {}).get("registration_number") or "").strip().upper()
        if reg:
            reg_ref = _company_ref(reg, ref[2])
            facts.append(_fact(task_id=int(task["id"]), source_id=source_id, fact_type="psc_registration_number", subject=ref, relation_type="identified_by_company_number", object_=reg_ref, confidence=0.95, evidence=evidence))
    return facts


def _insolvency_facts(task: dict[str, Any], result: dict[str, Any]) -> list[ResearchFact]:
    number = _company_number(task, result)
    if not number:
        return []
    source_id = str(task.get("source_id") or "companies_house")
    company = _company_ref(number)
    facts: list[ResearchFact] = []
    for index, case in enumerate(result.get("cases") or []):
        if not isinstance(case, dict):
            continue
        case_number = str(case.get("number") or f"{number}:{index}")
        case_type = str(case.get("type") or "insolvency case")
        event = _event_ref("insolvency_case", f"{number}:{case_number}", f"{case_type} {case_number}".strip())
        facts.append(_fact(task_id=int(task["id"]), source_id=source_id, fact_type="insolvency_case", subject=company, relation_type="has_insolvency_case", object_=event, confidence=1.0, evidence={"number": case.get("number"), "type": case.get("type"), "dates": case.get("dates") or []}))
        for practitioner in case.get("practitioners") or []:
            if not isinstance(practitioner, dict):
                continue
            ref = _name_ref(str(practitioner.get("name") or ""), kind="person")
            if ref:
                facts.append(_fact(task_id=int(task["id"]), source_id=source_id, fact_type="insolvency_practitioner", subject=event, relation_type="handled_by", object_=ref, confidence=0.96, evidence={"role": practitioner.get("role"), "address": practitioner.get("address")}))
    return facts


def _officer_appointments_facts(task: dict[str, Any], result: dict[str, Any]) -> list[ResearchFact]:
    source_id = str(task.get("source_id") or "companies_house")
    facts: list[ResearchFact] = []
    params = task.get("params") or {}
    officer_id = str(params.get("officer_id") or task.get("target_value") or "").strip()
    for item in result.get("items") or []:
        if not isinstance(item, dict):
            continue
        name_ref = _name_ref(str(item.get("name") or ""))
        company_number = str(item.get("appointed_to", {}).get("company_number") if isinstance(item.get("appointed_to"), dict) else "").strip().upper()
        company_name = str(item.get("appointed_to", {}).get("company_name") if isinstance(item.get("appointed_to"), dict) else company_number)
        if not name_ref or not company_number:
            continue
        company_ref = _company_ref(company_number, company_name)
        facts.append(_fact(task_id=int(task["id"]), source_id=source_id, fact_type="officer_appointment", subject=name_ref, relation_type="appointed_to_company", object_=company_ref, confidence=0.97, evidence={"officer_id": officer_id or None, "officer_role": item.get("officer_role"), "appointed_on": item.get("appointed_on"), "resigned_on": item.get("resigned_on")}))
    return facts


def _manual_facts(task: dict[str, Any], result: dict[str, Any]) -> list[ResearchFact]:
    facts: list[ResearchFact] = []
    source_id = str(task.get("source_id") or "manual_research")
    for raw in result.get("facts") or []:
        if not isinstance(raw, dict):
            continue
        subject = raw.get("subject") if isinstance(raw.get("subject"), dict) else {}
        object_ = raw.get("object") if isinstance(raw.get("object"), dict) else None
        subject_key = str(subject.get("canonical_key") or "").strip()
        subject_type = str(subject.get("entity_type") or "").strip()
        subject_display = str(subject.get("display_name") or subject_key).strip()
        if not subject_key or not subject_type:
            continue
        sref = (subject_type, subject_key, subject_display)
        oref = None
        if object_:
            object_key = str(object_.get("canonical_key") or "").strip()
            object_type = str(object_.get("entity_type") or "").strip()
            if object_key and object_type:
                oref = (object_type, object_key, str(object_.get("display_name") or object_key).strip())
        evidence = dict(raw.get("evidence") or {})
        evidence["manual_assertion"] = True
        evidence["review_required"] = True
        facts.append(_fact(task_id=int(task["id"]), source_id=source_id, fact_type=str(raw.get("fact_type") or "manual_research_fact"), subject=sref, relation_type=str(raw.get("relation_type") or "") or None, object_=oref, confidence=min(0.85, float(raw.get("confidence") or 0.7)), evidence=evidence))
    return facts


def extract_research_facts(task: dict[str, Any], result: dict[str, Any]) -> list[ResearchFact]:
    if result.get("not_found"):
        return []
    task_type = str(task.get("task_type") or "")
    parsers = {
        "companies_house_profile": _profile_facts,
        "companies_house_filing_history": _filing_facts,
        "companies_house_officers": _officer_facts,
        "companies_house_psc": _psc_facts,
        "companies_house_insolvency": _insolvency_facts,
        "companies_house_officer_appointments": _officer_appointments_facts,
    }
    facts = parsers[task_type](task, result) if task_type in parsers else []
    # A manual result can supplement any task type with explicitly structured facts.
    facts.extend(_manual_facts(task, result))
    dedup: dict[str, ResearchFact] = {fact.fingerprint: fact for fact in facts}
    return list(dedup.values())


def _result_fingerprint(result: Any) -> str:
    raw = json.dumps(result, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def assimilate_research_results(db: Database) -> FeedbackStats:
    """Normalize completed research results into durable graph facts.

    This function only records evidence. It never creates entitlement, executes outreach, files a
    claim, purchases an asset, or treats a manual assertion as verified ownership.
    """
    db.init()
    tasks_scanned = tasks_ingested = tasks_unchanged = facts_written = errors = 0
    now = datetime.now(timezone.utc).isoformat()
    with db.connect() as conn:
        rows = list(conn.execute("SELECT * FROM research_tasks WHERE state='completed' AND result_json IS NOT NULL ORDER BY id"))
        for row in rows:
            tasks_scanned += 1
            task = dict(row)
            for key, out_key, default in (
                ("params_json", "params", {}),
                ("result_json", "result", {}),
            ):
                try:
                    task[out_key] = json.loads(task.get(key) or json.dumps(default))
                except (json.JSONDecodeError, TypeError):
                    task[out_key] = default
            result = task["result"] if isinstance(task["result"], dict) else {"value": task["result"]}
            fingerprint = _result_fingerprint(result)
            prior = conn.execute("SELECT result_fingerprint FROM research_result_ingestions WHERE task_id=?", (int(row["id"]),)).fetchone()
            if prior and prior["result_fingerprint"] == fingerprint:
                tasks_unchanged += 1
                continue
            try:
                facts = extract_research_facts(task, result)
                conn.execute("DELETE FROM research_facts WHERE task_id=?", (int(row["id"]),))
                for fact in facts:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO research_facts(
                          fingerprint,task_id,source_id,fact_type,subject_entity_type,subject_canonical_key,
                          subject_display_name,relation_type,object_entity_type,object_canonical_key,
                          object_display_name,confidence,evidence_json,created_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            fact.fingerprint, fact.task_id, fact.source_id, fact.fact_type,
                            fact.subject_entity_type, fact.subject_canonical_key, fact.subject_display_name,
                            fact.relation_type, fact.object_entity_type, fact.object_canonical_key,
                            fact.object_display_name, fact.confidence,
                            json.dumps(fact.evidence, ensure_ascii=False, sort_keys=True, default=str), now,
                        ),
                    )
                conn.execute(
                    """
                    INSERT INTO research_result_ingestions(task_id,result_fingerprint,fact_count,status,error,ingested_at)
                    VALUES(?,?,?,'ingested',NULL,?)
                    ON CONFLICT(task_id) DO UPDATE SET result_fingerprint=excluded.result_fingerprint,
                      fact_count=excluded.fact_count,status='ingested',error=NULL,ingested_at=excluded.ingested_at
                    """,
                    (int(row["id"]), fingerprint, len(facts), now),
                )
                tasks_ingested += 1
                facts_written += len(facts)
            except Exception as exc:  # preserve an auditable per-task failure without hiding other results
                errors += 1
                conn.execute(
                    """
                    INSERT INTO research_result_ingestions(task_id,result_fingerprint,fact_count,status,error,ingested_at)
                    VALUES(?,?,0,'error',?,?)
                    ON CONFLICT(task_id) DO UPDATE SET result_fingerprint=excluded.result_fingerprint,
                      fact_count=0,status='error',error=excluded.error,ingested_at=excluded.ingested_at
                    """,
                    (int(row["id"]), fingerprint, f"{type(exc).__name__}: {exc}", now),
                )
        conn.commit()
    return FeedbackStats(tasks_scanned, tasks_ingested, tasks_unchanged, facts_written, errors)
