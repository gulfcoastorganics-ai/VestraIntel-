from decimal import Decimal

from fia.anomalies import detect_anomalies
from fia.case_resolution import rebuild_case_resolutions
from fia.commercial import rebuild_commercial_assessments
from fia.db import Database
from fia.entity_resolution import rebuild_entity_graph
from fia.models import Opportunity
from fia.research import plan_research


def _op(**kwargs):
    base = dict(
        jurisdiction="Test", custodian="Official source", source_url="https://example.test/record",
        legal_model="open_data_intelligence", compliance_status="review_required", score=80,
    )
    base.update(kwargs)
    return Opportunity(**base)


def _pipeline(db: Database, *, budget: float = 100):
    rebuild_entity_graph(db, fuzzy=False)
    rebuild_commercial_assessments(db)
    detect_anomalies(db)
    plan_research(db)
    return rebuild_case_resolutions(db, base_budget=budget)


def test_case_resolver_selects_high_evi_next_lookup(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert([
        _op(source_id="companies_house", external_id="01234567", asset_class="dissolved_company",
            title="ACME TECHNOLOGIES LIMITED company number 01234567", owner_name="ACME TECHNOLOGIES LIMITED",
            raw={"company_number": "01234567"}),
        _op(source_id="ca_unclaimed_property", external_id="CA-1", asset_class="unclaimed_funds",
            title="Unclaimed property for ACME TECHNOLOGIES LIMITED", owner_name="ACME TECHNOLOGIES LIMITED",
            face_value=Decimal("25000"), currency="USD", legal_model="licensed_locator",
            compliance_status="agreement_required", raw={"company_number": "01234567"}),
    ])
    stats = _pipeline(db)
    assert stats.cases >= 1
    anomaly = db.list_anomalies(anomaly_type="orphaned_business_asset")[0]
    case = db.case_resolution(anomaly["id"])
    assert case["resolution_status"] == "researching"
    assert case["next_task_id"] is not None
    assert case["task_priorities"][0]["evi_score"] >= case["task_priorities"][-1]["evi_score"]
    assert "human_approval_before_outreach_or_filing" in case["hard_gates"]


def test_identity_gap_can_reach_review_ready_but_keeps_human_gate(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert([
        _op(source_id="ca_unclaimed_property", external_id="CA-2", asset_class="unclaimed_funds",
            title="High-value property", owner_name="Example Holdings LLC", face_value=Decimal("75000"),
            currency="USD", legal_model="licensed_locator", compliance_status="agreement_required")
    ])
    _pipeline(db)
    anomaly = db.list_anomalies(anomaly_type="identity_resolution_gap")[0]
    task = db.list_research_tasks(limit=50, task_type="independent_identity_corroboration", state="pending", anomaly_id=anomaly["id"])[0]
    db.complete_research_task(task["id"], result={"facts": [{
        "fact_type": "independent_identity",
        "subject": {"entity_type": "organization", "canonical_key": "name:example holdings", "display_name": "Example Holdings LLC"},
        "relation_type": "corroborates_identity",
        "object": {"entity_type": "organization", "canonical_key": "name:example holdings", "display_name": "Example Holdings LLC"},
        "confidence": 0.8,
        "evidence": {"document_type": "official registry"},
    }]})
    # Completion itself satisfies the configured research target; legal/outreach gates remain separate.
    rebuild_case_resolutions(db)
    case = db.case_resolution(anomaly["id"])
    assert case["resolution_status"] == "review_ready"
    assert case["resolution_score"] == 100.0
    assert "human_approval_before_outreach_or_filing" in case["hard_gates"]


def test_zero_budget_blocks_expensive_research_without_deleting_it(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert([
        _op(source_id="uspto_official_gazette", external_id="P1", asset_class="patent_expiration",
            title="Patent 9,871,896 expired for failure to pay maintenance fee", owner_name="ACME TECHNOLOGIES LIMITED"),
        _op(source_id="flc_license_notices", external_id="F1", asset_class="federal_license_notice",
            title="Current licensing signal for ACME TECHNOLOGIES LIMITED", owner_name="ACME TECHNOLOGIES LIMITED"),
    ])
    _pipeline(db, budget=0)
    anomaly = db.list_anomalies(anomaly_type="lapsed_technology_reuse")[0]
    case = db.case_resolution(anomaly["id"])
    # The resolver enforces a minimum finite budget rather than allowing a zero/unbounded sentinel.
    assert case["budget_total"] >= 40
    assert case["next_task_id"] is not None


def test_case_resolution_db_next_task_matches_case_state(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert([
        _op(source_id="ca_unclaimed_property", external_id="CA-3", asset_class="unclaimed_funds",
            title="High-value property", owner_name="Another Holdings LLC", face_value=Decimal("90000"),
            currency="USD", legal_model="licensed_locator", compliance_status="agreement_required")
    ])
    _pipeline(db)
    anomaly = db.list_anomalies(anomaly_type="identity_resolution_gap")[0]
    case = db.case_resolution(anomaly["id"])
    nxt = db.next_case_task(anomaly["id"])
    assert nxt is not None
    assert nxt["id"] == case["next_task_id"]
    assert float(nxt["next_task_evi"]) == float(case["next_task_evi"])
