from __future__ import annotations

from datetime import date
from decimal import Decimal

from .models import Opportunity


ASSET_BASE = {
    "unclaimed_estate": 42,
    "patent_license_offer": 50,
    "patent_expiration": 34,
    "federal_license_notice": 58,
    "dissolved_company_asset": 55,
    "federal_award_rebid_signal": 48,
    "unclaimed_royalty_signal": 52,
    "unclaimed_funds": 50,
    "dissolved_company_signal": 46,
}

LEGAL_CLARITY = {
    "open_data_intelligence": 18,
    "licensed_locator": 10,
    "successor_claim": 8,
    "asset_purchase": 12,
    "owner_or_heir_only": 2,
    "manual_legal_review": 0,
}


def score_opportunity(item: Opportunity, *, today: date | None = None) -> float:
    today = today or date.today()
    score = float(ASSET_BASE.get(item.asset_class, 35))
    score += LEGAL_CLARITY.get(item.legal_model, 0)

    if item.face_value is not None:
        value = max(Decimal("0"), item.face_value)
        if value >= 250_000:
            score += 18
        elif value >= 50_000:
            score += 14
        elif value >= 10_000:
            score += 10
        elif value >= 1_000:
            score += 6
        else:
            score += 2

    if item.published_at:
        age = (today - item.published_at).days
        if age <= 7:
            score += 16
        elif age <= 30:
            score += 10
        elif age <= 180:
            score += 4
        elif age > 3650:
            score -= 5

    if item.claim_deadline:
        days = (item.claim_deadline - today).days
        if days < 0:
            score -= 40
        elif days <= 7:
            score += 4
        elif days <= 30:
            score += 8

    if item.compliance_status == "public_intelligence_only":
        score += 5
    elif item.compliance_status in {"licensed_only", "owner_only"}:
        score -= 3

    return round(max(0.0, min(100.0, score)), 2)
