from decimal import Decimal

from fia.anomalies import detect_anomalies
from fia.commercial import rebuild_commercial_assessments
from fia.db import Database
from fia.entity_resolution import rebuild_entity_graph
from fia.models import Opportunity
from fia.monetization import rebuild_monetization_routes


def _opp(source_id, external_id, asset_class, title, legal_model, *, owner=None, raw=None, value=None, status="public_intelligence_only"):
    return Opportunity(
        source_id=source_id,
        external_id=external_id,
        asset_class=asset_class,
        title=title,
        jurisdiction="United States",
        custodian="Official source",
        source_url="https://example.gov",
        legal_model=legal_model,
        owner_name=owner,
        face_value=Decimal(str(value)) if value is not None else None,
        currency="USD" if value is not None else None,
        compliance_status=status,
        raw=raw or {},
    )


def test_soundexchange_routes_owner_only(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert([_opp("soundexchange_unclaimed", "1", "unclaimed_royalty_signal", "SX lead", "owner_or_heir_only", owner="Artist One", status="owner_only")])
    stats = rebuild_monetization_routes(db)
    assert stats.opportunity_routes == 1
    route = db.monetization_route("opportunity", 1)
    assert route["route_id"] == "owner_only"
    assert "no_royalty_claim_for_unrelated_party" in route["prohibitions"]


def test_treasury_routes_locator_research_with_payee_gate(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert([_opp("treasury_unpaid_checks_foia", "1", "federal_unpaid_check_signal", "Canceled check", "manual_legal_review", value=5000, status="review_required")])
    rebuild_monetization_routes(db)
    route = db.monetization_route("opportunity", 1)
    assert route["route_id"] == "locator_fee"
    assert "agency_confirm_lawful_payee" in route["prerequisites"]


def test_royalty_cross_source_anomaly_routes_intelligence(tmp_path):
    db = Database(tmp_path / "fia.db")
    isrc = "USABC2600001"
    db.upsert([
        _opp("soundexchange_unclaimed", "sx1", "unclaimed_royalty_signal", f"SX {isrc}", "owner_or_heir_only", owner="Example Records", raw={"isrc": isrc}, status="owner_only"),
        _opp("mlc_data", "mlc1", "royalty_metadata_signal", f"MLC {isrc}", "open_data_intelligence", owner="Example Records", raw={"isrc": isrc}),
    ])
    rebuild_entity_graph(db, fuzzy=False)
    rebuild_commercial_assessments(db)
    detect_anomalies(db)
    stats = rebuild_monetization_routes(db)
    assert stats.anomaly_routes >= 1
    rows = db.list_monetization_routes(target_type="anomaly", route_id="intelligence_sale")
    assert rows
