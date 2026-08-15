from decimal import Decimal

from fia.anomalies import detect_anomalies
from fia.commercial import rebuild_commercial_assessments
from fia.db import Database
from fia.entity_resolution import rebuild_entity_graph
from fia.feedback import assimilate_research_results
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
    assimilate_research_results(db)
    rebuild_entity_graph(db, fuzzy=False)
    rebuild_commercial_assessments(db)
    detect_anomalies(db)
    return plan_research(db)


def _seed_cross_source_company(db: Database):
    db.upsert([
        _op(source_id="companies_house", external_id="01234567", asset_class="dissolved_company",
            title="ACME TECHNOLOGIES LIMITED company number 01234567", owner_name="ACME TECHNOLOGIES LIMITED",
            raw={"company_number": "01234567"}),
        _op(source_id="ca_unclaimed_property", external_id="CA-1", asset_class="unclaimed_funds",
            title="Unclaimed property for ACME TECHNOLOGIES LIMITED company number 01234567",
            owner_name="ACME TECHNOLOGIES LIMITED", face_value=Decimal("25000"), currency="USD",
            legal_model="licensed_locator", compliance_status="agreement_required",
            raw={"company_number": "01234567"}),
    ])
    _pipeline(db)


def test_completed_profile_result_becomes_graph_evidence(tmp_path):
    db = Database(tmp_path / "fia.db")
    _seed_cross_source_company(db)
    task = db.list_research_tasks(limit=100, task_type="companies_house_profile", state="pending")[0]
    db.complete_research_task(task["id"], result={
        "company_number": "01234567",
        "company_name": "ACME TECHNOLOGIES LIMITED",
        "company_status": "dissolved",
        "registered_office_address": {"address_line_1": "1 Example Road", "locality": "London", "postal_code": "SW1A 1AA"},
        "previous_company_names": [{"name": "ACME SYSTEMS LIMITED", "effective_from": "2012-01-01", "ceased_on": "2019-01-01"}],
    })
    stats = assimilate_research_results(db)
    assert stats.tasks_ingested == 1
    assert stats.facts_written >= 4
    rebuild_entity_graph(db, fuzzy=False)
    relation_types = {r["relation_type"] for r in db.list_entity_relations(limit=200)}
    assert {"official_name_of", "registered_office_at", "previous_company_name_of", "has_company_status"} <= relation_types


def test_officer_result_generates_recursive_appointments_task(tmp_path):
    db = Database(tmp_path / "fia.db")
    _seed_cross_source_company(db)
    task = db.list_research_tasks(limit=100, task_type="companies_house_officers", state="pending")[0]
    db.complete_research_task(task["id"], result={
        "items": [{
            "name": "DOE, JANE",
            "officer_role": "director",
            "appointed_on": "2020-01-01",
            "links": {"officer": {"appointments": "/officers/abcDEF123/appointments"}},
        }]
    })
    _pipeline(db)
    recursive = db.list_research_tasks(limit=100, task_type="companies_house_officer_appointments", state="pending")
    assert len(recursive) == 1
    assert recursive[0]["target_value"] == "abcDEF123"


def test_officer_appointments_result_generates_linked_company_profile(tmp_path):
    db = Database(tmp_path / "fia.db")
    _seed_cross_source_company(db)
    officer_task = db.list_research_tasks(limit=100, task_type="companies_house_officers", state="pending")[0]
    db.complete_research_task(officer_task["id"], result={
        "items": [{"name": "DOE, JANE", "links": {"officer": {"appointments": "/officers/abcDEF123/appointments"}}}]
    })
    _pipeline(db)
    appointments_task = db.list_research_tasks(limit=100, task_type="companies_house_officer_appointments", state="pending")[0]
    db.complete_research_task(appointments_task["id"], result={
        "items": [{
            "name": "DOE, JANE",
            "officer_role": "director",
            "appointed_to": {"company_number": "87654321", "company_name": "ACME SUCCESSOR LIMITED"},
        }]
    })
    _pipeline(db)
    profiles = db.list_research_tasks(limit=200, task_type="companies_house_profile", state="pending")
    assert any(r["target_value"] == "87654321" for r in profiles)


def test_entity_ids_remain_stable_across_rebuilds(tmp_path):
    db = Database(tmp_path / "fia.db")
    _seed_cross_source_company(db)
    first = [(r["id"], r["canonical_key"]) for r in db.connect().execute("SELECT id,canonical_key FROM entities ORDER BY id")]
    rebuild_entity_graph(db, fuzzy=False)
    second = [(r["id"], r["canonical_key"]) for r in db.connect().execute("SELECT id,canonical_key FROM entities ORDER BY id")]
    assert first == second
