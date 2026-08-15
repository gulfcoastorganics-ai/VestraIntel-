from decimal import Decimal

from fia.anomalies import detect_anomalies
from fia.case_resolution import rebuild_case_resolutions
from fia.commercial import rebuild_commercial_assessments
from fia.db import Database
from fia.economics import rebuild_case_economics
from fia.entity_resolution import rebuild_entity_graph
from fia.models import Opportunity
from fia.research import plan_research


def _op(**kwargs):
    base = dict(
        jurisdiction="Test",
        custodian="Official source",
        source_url="https://example.test/record",
        legal_model="open_data_intelligence",
        compliance_status="review_required",
        score=80,
    )
    base.update(kwargs)
    return Opportunity(**base)


def _pipeline(db: Database):
    rebuild_entity_graph(db, fuzzy=False)
    rebuild_commercial_assessments(db)
    detect_anomalies(db)
    plan_research(db)
    rebuild_case_resolutions(db)
    return rebuild_case_economics(db)


def test_california_locator_uses_verified_fee_ceiling_as_revenue_reference(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert([
        _op(
            source_id="ca_unclaimed_property",
            external_id="CA-ECON-1",
            asset_class="unclaimed_funds",
            title="High value property",
            owner_name="Example Holdings LLC",
            face_value=Decimal("10000"),
            currency="USD",
            legal_model="licensed_locator",
            compliance_status="agreement_required",
        )
    ])
    _pipeline(db)
    anomaly = db.list_anomalies(anomaly_type="identity_resolution_gap")[0]
    case = db.case_economics(anomaly["id"])
    assert case is not None
    assert case["revenue_reference"] == 1000.0
    assert case["currency"] == "USD"
    assert case["revenue_basis"] == "verified_fee_ceiling"
    assert case["expected_case_value"] < 1000.0


def test_high_value_locator_task_ranks_economically_and_is_queryable(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert([
        _op(
            source_id="companies_house",
            external_id="01234567",
            asset_class="dissolved_company",
            title="ACME TECHNOLOGIES LIMITED company number 01234567",
            owner_name="ACME TECHNOLOGIES LIMITED",
            raw={"company_number": "01234567"},
        ),
        _op(
            source_id="ca_unclaimed_property",
            external_id="CA-ECON-2",
            asset_class="unclaimed_funds",
            title="Unclaimed property for ACME TECHNOLOGIES LIMITED",
            owner_name="ACME TECHNOLOGIES LIMITED",
            face_value=Decimal("25000"),
            currency="USD",
            legal_model="licensed_locator",
            compliance_status="agreement_required",
            raw={"company_number": "01234567"},
        ),
    ])
    stats = _pipeline(db)
    assert stats.economically_ranked >= 1
    anomaly = db.list_anomalies(anomaly_type="orphaned_business_asset")[0]
    nxt = db.next_economic_task(anomaly["id"])
    assert nxt is not None
    assert nxt["best_task_economic_score"] > 0
    assert nxt["research_cost"] > 0
    assert 0 < nxt["resolve_probability"] <= 1


def test_unknown_new_york_value_stays_explicitly_unknown(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert([
        _op(
            source_id="companies_house",
            external_id="07654321",
            asset_class="dissolved_company",
            title="EXAMPLE HOLDINGS LIMITED company number 07654321",
            owner_name="EXAMPLE HOLDINGS LIMITED",
            raw={"company_number": "07654321"},
        ),
        _op(
            source_id="ny_unclaimed_property",
            external_id="NY-ECON-1",
            asset_class="unclaimed_funds",
            title="Potential property",
            owner_name="EXAMPLE HOLDINGS LIMITED",
            legal_model="licensed_locator",
            compliance_status="agreement_required",
            raw={"company_number": "07654321"},
        ),
    ])
    stats = _pipeline(db)
    anomaly = db.list_anomalies(anomaly_type="orphaned_business_asset")[0]
    case = db.case_economics(anomaly["id"])
    assert stats.unknown_value >= 1
    assert case is not None
    assert case["revenue_reference"] is None
    assert case["revenue_basis"] == "unknown"
    assert case["economic_status"] in {"value_unknown", "no_economic_task"}


def test_intelligence_sale_uses_visible_planning_assumption(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert([
        _op(
            source_id="uspto_official_gazette",
            external_id="P1",
            asset_class="patent_expiration",
            title="Patent 9,871,896 expired for failure to pay maintenance fee",
            owner_name="ACME TECHNOLOGIES LIMITED",
        ),
        _op(
            source_id="flc_license_notices",
            external_id="F1",
            asset_class="federal_license_notice",
            title="Current licensing signal for ACME TECHNOLOGIES LIMITED",
            owner_name="ACME TECHNOLOGIES LIMITED",
        ),
    ])
    rebuild_entity_graph(db, fuzzy=False)
    rebuild_commercial_assessments(db)
    detect_anomalies(db)
    plan_research(db)
    rebuild_case_resolutions(db)
    rebuild_case_economics(db, default_intelligence_value=400)
    anomaly = db.list_anomalies(anomaly_type="lapsed_technology_reuse")[0]
    case = db.case_economics(anomaly["id"])
    assert case is not None
    assert case["revenue_reference"] == 400.0
    assert case["revenue_basis"] == "planning_assumption:intelligence_sale"
    assert case["assumptions"]["planning_only"] is True
