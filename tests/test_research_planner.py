from decimal import Decimal

from fia.anomalies import detect_anomalies
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


def _pipeline(db: Database):
    rebuild_entity_graph(db, fuzzy=False)
    rebuild_commercial_assessments(db)
    detect_anomalies(db)
    return plan_research(db)


def test_orphaned_business_asset_plans_successor_and_company_tasks(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert([
        _op(source_id="companies_house", external_id="01234567", asset_class="dissolved_company",
            title="ACME TECHNOLOGIES LIMITED company number 01234567", owner_name="ACME TECHNOLOGIES LIMITED",
            raw={"company_number": "01234567"}),
        _op(source_id="ca_unclaimed_property", external_id="CA-1", asset_class="unclaimed_funds",
            title="Unclaimed property for ACME TECHNOLOGIES LIMITED", owner_name="ACME TECHNOLOGIES LIMITED",
            face_value=Decimal("25000"), currency="USD", legal_model="licensed_locator",
            compliance_status="agreement_required"),
    ])
    stats = _pipeline(db)
    assert stats.tasks > 0
    types = {r["task_type"] for r in db.list_research_tasks(limit=200, state="pending")}
    assert {"companies_house_profile", "companies_house_filing_history", "successor_chain_research", "dissolution_asset_disposition_review"} <= types


def test_lapsed_patent_plans_status_assignment_family_and_market_tasks(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert([
        _op(source_id="uspto_official_gazette", external_id="P1", asset_class="patent_expiration",
            title="Patent 9,871,896 expired for failure to pay maintenance fee", owner_name="ACME TECHNOLOGIES LIMITED"),
        _op(source_id="flc_license_notices", external_id="F1", asset_class="federal_license_notice",
            title="Current licensing signal for ACME TECHNOLOGIES LIMITED", owner_name="ACME TECHNOLOGIES LIMITED"),
    ])
    _pipeline(db)
    types = {r["task_type"] for r in db.list_research_tasks(limit=200, state="pending")}
    assert {"uspto_assignment_lookup", "patent_status_check", "patent_family_review", "market_relevance_check"} <= types


def test_completed_task_survives_replanning(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert([
        _op(source_id="ca_unclaimed_property", external_id="CA-2", asset_class="unclaimed_funds",
            title="High-value property", owner_name="Example Holdings LLC", face_value=Decimal("75000"),
            currency="USD", legal_model="licensed_locator", compliance_status="agreement_required")
    ])
    _pipeline(db)
    task = db.list_research_tasks(limit=100, task_type="independent_identity_corroboration", state="pending")[0]
    assert db.set_research_task_state(task["id"], "completed")
    plan_research(db)
    assert len(db.list_research_tasks(limit=100, task_type="independent_identity_corroboration", state="completed")) == 1


def test_empty_research_queue_has_empty_counts(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.init()
    assert db.research_task_counts() == {}
