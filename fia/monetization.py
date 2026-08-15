from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .db import Database

ROUTE_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "route_id": "locator_fee",
        "name": "Locator / recovery service",
        "revenue_model": "fee_after_owner_agreement_and_recovery",
        "description": "Reconnect the lawful owner/payee to an asset under the applicable finder/locator rules.",
        "human_gate": True,
    },
    {
        "route_id": "successor_assignment_review",
        "name": "Successor / assignment review",
        "revenue_model": "lawful_assignment_or_successor_recovery_if_permitted",
        "description": "Research a documented successor or assignment path; no entitlement is inferred from discovery alone.",
        "human_gate": True,
    },
    {
        "route_id": "asset_acquisition",
        "name": "Asset acquisition",
        "revenue_model": "purchase_then_use_license_or_resell",
        "description": "Acquire an asset through an official sale/referral process after title, valuation, and legal review.",
        "human_gate": True,
    },
    {
        "route_id": "intelligence_sale",
        "name": "Intelligence / reconciliation service",
        "revenue_model": "research_or_data_service_fee",
        "description": "Sell lawful analysis, reconciliation, monitoring, or lead intelligence without claiming the underlying asset.",
        "human_gate": False,
    },
    {
        "route_id": "licensing_introduction",
        "name": "Licensing introduction",
        "revenue_model": "contracted_referral_or_advisory_fee",
        "description": "Introduce a willing licensor/rightsholder and prospective commercial user under a separate written agreement.",
        "human_gate": True,
    },
    {
        "route_id": "owner_only",
        "name": "Owner/rightsholder only",
        "revenue_model": "none_without_separate_permitted_service",
        "description": "The underlying money/right is claimable only by the lawful owner/rightsholder or authorized representative.",
        "human_gate": True,
    },
)


@dataclass(frozen=True)
class RoutingStats:
    opportunity_routes: int
    anomaly_routes: int


def _route_for_opportunity(row: Any) -> tuple[str, float, list[str], list[str], list[str]]:
    source = str(row["source_id"])
    asset = str(row["asset_class"])
    legal = str(row["legal_model"])

    prerequisites = ["verify_current_source_record"]
    prohibitions = ["no_false_entitlement_claims", "no_impersonation"]
    reasons = [f"source:{source}", f"asset_class:{asset}", f"legal_model:{legal}"]

    if source in {"ca_unclaimed_property", "ny_unclaimed_property"}:
        prerequisites += ["confirm_locator_eligibility", "owner_agreement_before_recovery_action"]
        prohibitions += ["no_claim_without_owner_authority", "no_fee_above_applicable_cap"]
        return "locator_fee", 88.0, prerequisites, prohibitions, reasons

    if source == "treasury_unpaid_checks_foia":
        prerequisites += [
            "identify_certifying_agency",
            "agency_confirm_lawful_payee",
            "review_locator_rules_for_payee_jurisdiction",
        ]
        prohibitions += ["no_assumption_that_cancellation_list_identifies_payee", "no_collection_without_payee_authority"]
        return "locator_fee", 73.0, prerequisites, prohibitions, reasons

    if source == "official_surplus_funds":
        prerequisites += [
            "review_jurisdiction_specific_surplus_statute",
            "confirm_claimant_priority_and_deadline",
            "confirm_locator_or_assignment_model_is_permitted",
        ]
        prohibitions += ["no_universal_fee_assumption", "no_assignment_without_jurisdiction_review", "no_claim_without_authority"]
        return "locator_fee", 69.0, prerequisites, prohibitions, reasons

    if source == "soundexchange_unclaimed":
        prerequisites += ["qualifying_creator_or_rightsholder_must_claim", "use_public_status_only_for_reconciliation_or_owner_notice_review"]
        prohibitions += ["no_royalty_claim_for_unrelated_party", "no_representation_as_soundexchange_partner"]
        return "owner_only", 96.0, prerequisites, prohibitions, reasons

    if source == "mlc_data" or asset == "royalty_metadata_signal":
        prerequisites += ["authorized_data_access", "validate_metadata_before_client_delivery"]
        prohibitions += ["no_claiming_unrelated_royalty_shares", "no_unauthorized_bulk_access"]
        return "intelligence_sale", 91.0, prerequisites, prohibitions, reasons

    if source == "sam_contract_opportunities" or asset == "contract_opportunity_signal":
        prerequisites += ["verify_opportunity_is_current", "separate_bid_eligibility_from_intelligence_service"]
        prohibitions += ["no_false_vendor_eligibility_claims"]
        return "intelligence_sale", 82.0, prerequisites, prohibitions, reasons

    if asset in {"patent_license_offer", "federal_license_notice"}:
        prerequisites += ["confirm_current_licensing_status", "written_referral_or_advisory_terms_before_fee"]
        prohibitions += ["no_claim_of_ownership_or_exclusivity"]
        return "licensing_introduction", 84.0, prerequisites, prohibitions, reasons

    if legal == "successor_claim":
        prerequisites += ["document_chain_of_ownership", "jurisdiction_or_court_review"]
        prohibitions += ["no_filing_before_entitlement_review"]
        return "successor_assignment_review", 89.0, prerequisites, prohibitions, reasons

    if legal == "asset_purchase":
        prerequisites += ["confirm_title", "independent_valuation", "official_sale_or_transfer_process"]
        prohibitions += ["no_taking_or_using_asset_before_transfer"]
        return "asset_acquisition", 90.0, prerequisites, prohibitions, reasons

    if legal == "owner_or_heir_only":
        prerequisites += ["owner_or_heir_entitlement_required"]
        prohibitions += ["no_claim_by_unrelated_discoverer"]
        return "owner_only", 94.0, prerequisites, prohibitions, reasons

    if legal == "open_data_intelligence":
        prerequisites += ["validate_commercial_relevance"]
        return "intelligence_sale", 78.0, prerequisites, prohibitions, reasons

    prerequisites += ["human_legal_review"]
    return "owner_only", 45.0, prerequisites, prohibitions, reasons


def _route_for_anomaly(row: Any) -> tuple[str, float, list[str], list[str], list[str]]:
    anomaly = str(row["anomaly_type"])
    prerequisites = ["verify_all_underlying_source_records", "human_review_before_external_action"]
    prohibitions = ["no_entitlement_inference_from_correlation", "no_impersonation"]
    reasons = [f"anomaly_type:{anomaly}"]

    if anomaly == "royalty_metadata_mismatch":
        prerequisites += ["confirm_authorized_music_metadata_access", "validate_isrc_work_rightsholder_relationship"]
        prohibitions += ["no_claiming_or_redirecting_third_party_royalties"]
        return "intelligence_sale", 94.0, prerequisites, prohibitions, reasons
    if anomaly == "dissolved_company_ip":
        prerequisites += ["confirm_ip_was_owned_at_dissolution", "confirm_current_title_and_restoration_status", "obtain_valuation"]
        prohibitions += ["no_use_or_transfer_before_valid_acquisition_or_license"]
        return "asset_acquisition", 92.0, prerequisites, prohibitions, reasons
    if anomaly in {"orphaned_business_asset", "successor_entitlement_candidate"}:
        prerequisites += ["document_successor_or_assignment_chain", "jurisdiction_specific_entitlement_review"]
        prohibitions += ["no_filing_or_assignment_purchase_before_review"]
        return "successor_assignment_review", 93.0, prerequisites, prohibitions, reasons
    if anomaly == "lapsed_technology_reuse":
        prerequisites += ["recheck_patent_status_and_family", "freedom_to_operate_review_before_productization"]
        prohibitions += ["no_assumption_that_one_expired_patent_clears_all_rights"]
        return "intelligence_sale", 87.0, prerequisites, prohibitions, reasons
    if anomaly in {"high_value_cross_source", "material_source_change", "identity_resolution_gap"}:
        prerequisites += ["resolve_identity_and_materiality_before_monetization"]
        return "intelligence_sale", 74.0, prerequisites, prohibitions, reasons
    return "intelligence_sale", 60.0, prerequisites, prohibitions, reasons


def rebuild_monetization_routes(db: Database) -> RoutingStats:
    db.init()
    now = datetime.now(timezone.utc).isoformat()
    opportunity_count = anomaly_count = 0
    with db.connect() as conn:
        conn.execute("DELETE FROM monetization_routes")
        for row in conn.execute("SELECT * FROM opportunities ORDER BY id"):
            route, score, prerequisites, prohibitions, reasons = _route_for_opportunity(row)
            conn.execute(
                """
                INSERT INTO monetization_routes(
                  target_type,target_id,route_id,route_score,revenue_model,prerequisites_json,
                  prohibitions_json,reason_json,updated_at
                ) VALUES('opportunity',?,?,?,?,?,?,?,?)
                """,
                (
                    int(row["id"]), route, score,
                    next(item["revenue_model"] for item in ROUTE_CATALOG if item["route_id"] == route),
                    json.dumps(prerequisites), json.dumps(prohibitions), json.dumps(reasons), now,
                ),
            )
            opportunity_count += 1
        for row in conn.execute("SELECT * FROM anomaly_findings WHERE state IN ('open','confirmed') ORDER BY id"):
            route, score, prerequisites, prohibitions, reasons = _route_for_anomaly(row)
            conn.execute(
                """
                INSERT INTO monetization_routes(
                  target_type,target_id,route_id,route_score,revenue_model,prerequisites_json,
                  prohibitions_json,reason_json,updated_at
                ) VALUES('anomaly',?,?,?,?,?,?,?,?)
                """,
                (
                    int(row["id"]), route, score,
                    next(item["revenue_model"] for item in ROUTE_CATALOG if item["route_id"] == route),
                    json.dumps(prerequisites), json.dumps(prohibitions), json.dumps(reasons), now,
                ),
            )
            anomaly_count += 1
        conn.commit()
    return RoutingStats(opportunity_routes=opportunity_count, anomaly_routes=anomaly_count)
