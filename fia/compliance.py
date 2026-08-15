from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Gate:
    automation: str
    action: str
    rationale: str


GATES: dict[str, Gate] = {
    "uk_unclaimed_estates": Gate(
        "public_ingest",
        "owner_or_heir_only",
        "Public discovery is permitted; entitlement must be proven by the heir/representative.",
    ),
    "ca_unclaimed_property": Gate(
        "public_ingest",
        "agreement_and_law_review",
        "California publishes public bulk records; owner/heir entitlement and current investigator/contract rules govern any recovery service.",
    ),
    "uspto_official_gazette": Gate(
        "public_ingest",
        "public_intelligence_only",
        "Public notices can be indexed. Any license, patent or FTO decision requires separate diligence.",
    ),
    "uspto_open_data": Gate(
        "credentialed_public_api",
        "public_intelligence_only",
        "USPTO Open Data Portal now requires account/API-key access; use only authenticated public-data APIs.",
    ),
    "flc_license_notices": Gate(
        "public_ingest",
        "public_intelligence_only",
        "Public licensing notices can be monitored; objections/applications follow agency procedures.",
    ),
    "companies_house": Gate(
        "credentialed_public_api",
        "public_intelligence_only",
        "Public company data can be enriched using an API key; Crown asset purchase is a separate process.",
    ),
    "ny_unclaimed_property": Gate(
        "registered_or_manual",
        "agreement_required",
        "New York publishes finder rules and a quarterly owner-name file; locator activity has fee/agreement rules.",
    ),
    "bankruptcy_unclaimed_funds": Gate(
        "manual_only",
        "review_required",
        "Court locator interfaces and claim procedures vary; do not bypass CAPTCHA or file without entitlement.",
    ),
    "soundexchange_unclaimed": Gate(
        "public_search_or_manual",
        "public_intelligence_only",
        "Use public lists/search for catalog reconciliation; royalty claims belong to actual rightsholders.",
    ),
    "mlc_data": Gate(
        "enrollment_required",
        "public_intelligence_only",
        "Public Search API/Bulk Data access requires enrollment in the MLC Data Access Hub.",
    ),
}
