from datetime import date
from decimal import Decimal

from fia.models import Opportunity
from fia.scoring import score_opportunity


def test_high_value_fresh_public_signal_scores_above_old_unknown():
    fresh = Opportunity(
        source_id="x",
        external_id="1",
        asset_class="federal_license_notice",
        title="Fresh",
        jurisdiction="US",
        custodian="X",
        source_url="https://example.test",
        legal_model="open_data_intelligence",
        face_value=Decimal("250000"),
        published_at=date(2026, 8, 10),
        compliance_status="public_intelligence_only",
    )
    old = Opportunity(
        source_id="x",
        external_id="2",
        asset_class="unclaimed_estate",
        title="Old",
        jurisdiction="UK",
        custodian="X",
        source_url="https://example.test",
        legal_model="owner_or_heir_only",
        published_at=date(2000, 1, 1),
        compliance_status="owner_only",
    )
    assert score_opportunity(fresh, today=date(2026, 8, 12)) > score_opportunity(
        old, today=date(2026, 8, 12)
    )
