from decimal import Decimal

from fia.anomalies import detect_anomalies
from fia.commercial import rebuild_commercial_assessments
from fia.db import Database
from fia.entity_resolution import rebuild_entity_graph
from fia.models import Opportunity


def _op(**kwargs):
    defaults = dict(
        jurisdiction="Test",
        custodian="Official source",
        source_url="https://example.test/record",
        legal_model="open_data_intelligence",
        compliance_status="review_required",
        score=80,
    )
    defaults.update(kwargs)
    return Opportunity(**defaults)


def _pipeline(db: Database):
    rebuild_entity_graph(db, fuzzy=False)
    rebuild_commercial_assessments(db)
    return detect_anomalies(db)


def test_detects_dissolved_company_with_unclaimed_asset(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert(
        [
            _op(
                source_id="companies_house",
                external_id="01234567",
                asset_class="dissolved_company",
                title="ACME TECHNOLOGIES LIMITED dissolved",
                owner_name="ACME TECHNOLOGIES LIMITED",
                raw={"company_number": "01234567"},
            ),
            _op(
                source_id="ca_unclaimed_property",
                external_id="CA-1",
                asset_class="unclaimed_funds",
                title="Unclaimed property for ACME TECHNOLOGIES LIMITED",
                owner_name="ACME TECHNOLOGIES LIMITED",
                face_value=Decimal("25000"),
                currency="USD",
                legal_model="licensed_locator",
                compliance_status="agreement_required",
            ),
        ]
    )
    stats = _pipeline(db)
    assert stats.findings >= 1
    rows = db.list_anomalies(anomaly_type="orphaned_business_asset")
    assert len(rows) == 1
    case = db.anomaly_case(rows[0]["id"])
    assert "entitlement_not_established" in case["blocks"]
    assert set(case["source_ids"]) == {"companies_house", "ca_unclaimed_property"}


def test_detects_lapsed_patent_with_live_signal_and_requires_recheck(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert(
        [
            _op(
                source_id="uspto_official_gazette",
                external_id="PAT-1",
                asset_class="patent_expiration",
                title="Patent 9,871,896 expired for failure to pay maintenance fee",
                owner_name="ACME TECHNOLOGIES LIMITED",
            ),
            _op(
                source_id="flc_license_notices",
                external_id="FLC-1",
                asset_class="federal_license_notice",
                title="Technology licensing signal for ACME Technologies",
                owner_name="ACME TECHNOLOGIES LIMITED",
            ),
        ]
    )
    _pipeline(db)
    rows = db.list_anomalies(anomaly_type="lapsed_technology_reuse")
    assert len(rows) == 1
    case = db.anomaly_case(rows[0]["id"])
    assert "patent_status_recheck_required" in case["blocks"]
    assert "recheck_uspto_maintenance_and_reinstatement_status" in case["next_actions"]


def test_high_value_single_source_is_flagged_for_identity_corroboration(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert(
        [
            _op(
                source_id="ca_unclaimed_property",
                external_id="CA-2",
                asset_class="unclaimed_funds",
                title="High-value unclaimed property",
                owner_name="Example Holdings LLC",
                face_value=Decimal("75000"),
                currency="USD",
                legal_model="licensed_locator",
                compliance_status="agreement_required",
            )
        ]
    )
    _pipeline(db)
    rows = db.list_anomalies(anomaly_type="identity_resolution_gap")
    assert len(rows) == 1
    case = db.anomaly_case(rows[0]["id"])
    assert case["primary_opportunity_id"] is not None
    assert "identity_not_independently_corroborated" in case["blocks"]


def test_dismissed_state_survives_redetection(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert(
        [
            _op(
                source_id="companies_house",
                external_id="09876543",
                asset_class="dissolved_company",
                title="Example Systems Limited dissolved",
                owner_name="Example Systems Limited",
            ),
            _op(
                source_id="ca_unclaimed_property",
                external_id="CA-3",
                asset_class="unclaimed_funds",
                title="Example Systems Limited property",
                owner_name="Example Systems Limited",
                face_value=Decimal("12000"),
                currency="USD",
                legal_model="licensed_locator",
                compliance_status="agreement_required",
            ),
        ]
    )
    _pipeline(db)
    row = db.list_anomalies(anomaly_type="orphaned_business_asset")[0]
    assert db.set_anomaly_state(row["id"], "dismissed")
    detect_anomalies(db)
    dismissed = db.list_anomalies(anomaly_type="orphaned_business_asset", state="dismissed")
    assert len(dismissed) == 1
