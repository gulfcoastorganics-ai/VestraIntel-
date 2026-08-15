from pathlib import Path

import httpx

from fia.db import Database
from fia.source_discovery import (
    CKANMiner,
    DataGovMiner,
    EUDataPortalMiner,
    SourceMiningConfig,
    _candidate,
    infer_monetization_route,
    mine_source_catalogs,
    score_candidate,
)


def test_scoring_prefers_asset_dense_machine_readable_source():
    good, _ = score_candidate(
        title="Unclaimed property and surplus funds",
        description="Weekly public claimant-owner dataset",
        keywords=["unclaimed property", "surplus funds"],
        formats=["CSV", "JSON", "API"],
        access_level="public",
        license_value="CC0 publicdomain",
        modified_at="2026-08-14T00:00:00+00:00",
        popularity=1,
    )
    weak, _ = score_candidate(
        title="Annual administrative report",
        description="General summary document",
        keywords=["report"],
        formats=["PDF"],
        access_level="public",
        license_value=None,
        modified_at="2019-01-01",
        popularity=100,
    )
    assert good["overall_score"] > weak["overall_score"] + 30
    assert good["machine_readability_score"] > weak["machine_readability_score"]


def test_route_inference_is_conservative_and_specific():
    assert infer_monetization_route("Unclaimed funds", "", []) == "locator_fee_review"
    assert infer_monetization_route("Dissolved companies assets", "bona vacantia", []) == "asset_acquisition_review"
    assert infer_monetization_route("Unmatched royalties", "ISRC rightsholder metadata", []) == "rights_reconciliation_intelligence"
    assert infer_monetization_route("Government contracts", "procurement opportunities", []) == "procurement_intelligence"


def test_datagov_normalizer_uses_dcat_metadata():
    payload = {
        "results": [{
            "identifier": "abc-123",
            "title": "Unclaimed property records",
            "description": "Public records",
            "publisher": "Example Treasury",
            "keyword": ["unclaimed property"],
            "popularity": 1,
            "last_harvested_date": "2026-08-14T12:00:00+00:00",
            "distribution_titles": ["Owner records CSV", "Public API"],
            "dcat": {
                "accessLevel": "public",
                "license": "https://creativecommons.org/publicdomain/zero/1.0/",
                "modified": "2026-08-14T00:00:00+00:00",
                "landingPage": "https://example.gov/data",
                "distribution": [{"format": "CSV"}, {"mediaType": "application/json"}],
            },
        }]
    }
    def handler(request: httpx.Request):
        assert request.headers["X-Api-Key"] == "secret"
        return httpx.Response(200, json=payload)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        rows = DataGovMiner(client, api_key="secret").search("unclaimed property", 10)
    assert len(rows) == 1
    assert rows[0].catalog_id == "us_data_gov"
    assert "CSV" in rows[0].formats
    assert rows[0].monetization_route == "locator_fee_review"


def test_ckan_normalizer_handles_public_catalog():
    payload = {"success": True, "result": {"results": [{
        "id": "uk-1",
        "name": "surplus-funds",
        "title": "Court surplus funds",
        "notes": "Public surplus records",
        "metadata_modified": "2026-08-01T00:00:00+00:00",
        "license_title": "Open Government Licence",
        "organization": {"title": "Example Court"},
        "tags": [{"name": "surplus funds"}],
        "resources": [{"format": "CSV"}],
    }]}}
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))) as client:
        rows = CKANMiner(client, catalog_id="uk_data_gov", jurisdiction="United Kingdom", base_url="https://data.gov.uk").search("surplus funds", 10)
    assert rows[0].publisher == "Example Court"
    assert rows[0].overall_score > 40
    assert rows[0].monetization_route == "locator_fee_review"


def test_eu_search_normalizer_handles_multilingual_title():
    payload = {"results": [{
        "id": "eu-1",
        "title": {"en": "Liquidation distributions"},
        "description": {"en": "Official insolvency distribution data"},
        "modified": "2026-07-01T00:00:00+00:00",
        "keyword": ["liquidation"],
        "distribution": [{"format": "CSV"}],
        "publisher": {"name": "Example Authority"},
    }]}
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))) as client:
        rows = EUDataPortalMiner(client).search("liquidation", 10)
    assert rows[0].title == "Liquidation distributions"
    assert rows[0].monetization_route == "successor_claim_review"


def test_candidate_state_persists_across_rediscovery(tmp_path: Path):
    db = Database(tmp_path / "fia.sqlite3")
    candidate = _candidate(
        catalog_id="uk_data_gov", jurisdiction="United Kingdom", external_id="x1",
        title="Unclaimed estates", description="public CSV", formats=["CSV"],
        keywords=["unclaimed"], access_level="public", license_value="Open Government Licence",
        modified_at="2026-08-14",
    )
    assert db.upsert_source_candidates([candidate]) == 1
    row = db.list_source_candidates()[0]
    assert db.set_source_candidate_state(row["id"], "approved")
    updated = _candidate(
        catalog_id="uk_data_gov", jurisdiction="United Kingdom", external_id="x1",
        title="Unclaimed estates updated", description="public CSV", formats=["CSV", "JSON"],
        keywords=["unclaimed"], access_level="public", license_value="Open Government Licence",
        modified_at="2026-08-14",
    )
    db.upsert_source_candidates([updated])
    approved = db.list_source_candidates(state="approved")
    assert len(approved) == 1
    assert approved[0]["title"] == "Unclaimed estates updated"


def test_mining_isolates_catalog_errors_and_saves_results(tmp_path: Path):
    db = Database(tmp_path / "fia.sqlite3")
    class Good:
        def search(self, query, limit=25):
            return [_candidate(
                catalog_id="uk_data_gov", jurisdiction="United Kingdom", external_id=f"{query}-1",
                title=f"Unclaimed funds {query}", description="CSV data", formats=["CSV"],
                keywords=["unclaimed funds"], access_level="public", license_value="Open Government Licence",
                modified_at="2026-08-14",
            )]
    class Bad:
        def search(self, query, limit=25):
            raise RuntimeError("catalog unavailable")
    stats = mine_source_catalogs(
        db,
        SourceMiningConfig(catalog_ids=("uk_data_gov", "eu_data_portal"), queries=("one", "two"), results_per_query=5),
        miner_factory=lambda client: {"uk_data_gov": Good(), "eu_data_portal": Bad()},
    )
    assert stats.saved == 2
    assert len(stats.errors) == 2
    assert len(db.list_source_candidates(state=None)) == 2
    assert db.list_source_mining_runs()[0]["status"] == "completed_with_errors"
