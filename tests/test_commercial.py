from datetime import date
from decimal import Decimal

from fia.commercial import rebuild_commercial_assessments
from fia.db import Database
from fia.entity_resolution import rebuild_entity_graph
from fia.models import Opportunity


def _item(source_id: str, external_id: str, owner: str, *, value=None, legal="licensed_locator", status="agreement_required", raw=None):
    return Opportunity(
        source_id=source_id,
        external_id=external_id,
        asset_class="unclaimed_funds",
        title=f"Property for {owner}",
        jurisdiction="California, USA" if source_id == "ca_unclaimed_property" else "New York, USA",
        custodian="Official custodian",
        source_url="https://example.gov/record",
        legal_model=legal,
        owner_name=owner,
        face_value=Decimal(str(value)) if value is not None else None,
        currency="USD" if value is not None else None,
        compliance_status=status,
        raw=raw or {},
    )


def test_california_fee_ceiling_and_gate(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert([_item("ca_unclaimed_property", "1", "Acme Technologies LLC", value=10000)])
    rebuild_entity_graph(db, fuzzy=False)
    rebuild_commercial_assessments(db, today=date(2026, 8, 14))
    row = db.list_commercial_assessments(limit=1)[0]
    assert row["fee_cap_percent"] == 10.0
    assert row["gross_fee_ceiling"] == "1000.00"
    assert "signed_owner_agreement_required" in row["block_json"]
    assert row["lane"] == "locator_service"


def test_new_york_unknown_value_has_no_fee_ceiling(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert([_item("ny_unclaimed_property", "1", "Example Holdings Inc")])
    rebuild_entity_graph(db, fuzzy=False)
    rebuild_commercial_assessments(db, today=date(2026, 8, 14))
    row = db.list_commercial_assessments(limit=1)[0]
    assert row["fee_cap_percent"] == 15.0
    assert row["gross_fee_ceiling"] is None


def test_cross_source_entity_gets_commercial_summary(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert([
        _item("ca_unclaimed_property", "1", "Acme Technologies LLC", value=5000, raw={"company_number": "01234567"}),
        Opportunity(
            source_id="companies_house", external_id="01234567", asset_class="dissolved_company",
            title="Dissolved Acme", jurisdiction="United Kingdom", custodian="Companies House",
            source_url="https://example.gov/company", legal_model="open_data_intelligence",
            owner_name="Acme Technologies Limited", compliance_status="public_intelligence_only",
            raw={"company_number": "01234567"},
        ),
    ])
    rebuild_entity_graph(db, fuzzy=False)
    rebuild_commercial_assessments(db, today=date(2026, 8, 14))
    rows = db.list_entity_commercial_summaries(limit=20, min_sources=2)
    assert rows
    assert any(r["source_count"] >= 2 for r in rows)


def test_successor_claim_is_review_lane(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert([_item("bankruptcy", "1", "Example Creditor LLC", value=25000, legal="successor_claim", status="review_required")])
    rebuild_entity_graph(db, fuzzy=False)
    rebuild_commercial_assessments(db, today=date(2026, 8, 14))
    row = db.list_commercial_assessments(limit=1)[0]
    assert row["lane"] == "successor_claim_review"
    assert "chain_of_ownership_required" in row["block_json"]
