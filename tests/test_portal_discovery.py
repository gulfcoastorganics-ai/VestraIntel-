from pathlib import Path

import httpx

from fia.db import Database
from fia.portal_discovery import (
    PortalCandidate,
    PortalDiscoveryConfig,
    PortalFingerprinter,
    discover_portals,
)
from fia.source_discovery import _candidate


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ckan_fingerprint_uses_read_only_status_endpoint():
    def handler(request: httpx.Request):
        if request.url.path == "/api/3/action/status_show":
            return httpx.Response(200, json={"success": True, "result": {"site_title": "Catalog"}})
        return httpx.Response(200, text="<html><body>Open data portal</body></html>", headers={"content-type": "text/html"})

    with _client(handler) as client:
        row = PortalFingerprinter(client).probe("https://catalog.example/")
    assert row is not None
    assert row.portal_type == "ckan"
    assert row.confidence >= 0.95
    assert row.connector_spec["search_endpoint"].endswith("/api/3/action/package_search")
    assert row.connector_spec["requires_analyst_approval"] is True


def test_socrata_fingerprint_is_passive_and_marks_soda3_credential_note():
    html = "<html><head><title>Open Data</title></head><body>Powered by Socrata. SODA API.</body></html>"
    with _client(lambda request: httpx.Response(200 if request.url.path == "/" else 404, text=html if request.url.path == "/" else "")) as client:
        row = PortalFingerprinter(client).probe("https://data.example/")
    assert row is not None
    assert row.portal_type == "socrata"
    assert "SODA3" in row.connector_spec["credential_note"]
    assert row.connector_spec["requires_analyst_approval"] is True


def test_arcgis_fingerprint_uses_public_search_probe():
    def handler(request: httpx.Request):
        if request.url.path == "/sharing/rest/search":
            return httpx.Response(200, json={"total": 1, "results": []})
        if request.url.path == "/api/search/v1":
            return httpx.Response(404)
        if request.url.path == "/api/3/action/status_show":
            return httpx.Response(404)
        return httpx.Response(200, text="<html>Government open data</html>", headers={"content-type": "text/html"})

    with _client(handler) as client:
        row = PortalFingerprinter(client).probe("https://maps.example/")
    assert row is not None
    assert row.portal_type == "arcgis"
    assert "catalog_search" in row.capabilities
    assert row.connector_spec["portal_search_endpoint"].endswith("/sharing/rest/search")


def test_dcat_rss_and_bulk_links_are_hybrid_capabilities():
    html = """
    <html><head>
      <link rel="alternate" type="application/atom+xml" href="/updates.atom" />
      <link rel="alternate" type="text/turtle" href="/catalog.ttl" />
    </head><body>
      <a href="/download/owners.csv">owners</a>
      <a href="/download/archive.zip">archive</a>
    </body></html>
    """
    def handler(request: httpx.Request):
        if request.url.path in {"/api/3/action/status_show", "/sharing/rest/search", "/api/search/v1"}:
            return httpx.Response(404)
        return httpx.Response(200, text=html, headers={"content-type": "text/html"})

    with _client(handler) as client:
        row = PortalFingerprinter(client).probe("https://records.example/")
    assert row is not None
    assert row.portal_type == "rss_atom"  # strongest advertised passive signal
    assert "catalog_metadata" in row.capabilities
    assert "bulk_files" in row.capabilities
    assert "change_monitoring" in row.capabilities


def test_advertised_sparql_endpoint_is_probed_with_bounded_select_only():
    html = '<html><body><a href="/sparql">SPARQL endpoint</a></body></html>'
    seen_queries = []
    def handler(request: httpx.Request):
        if request.url.path == "/sparql":
            seen_queries.append(request.url.params.get("query"))
            return httpx.Response(
                200,
                json={"head": {"vars": ["s"]}, "results": {"bindings": []}},
                headers={"content-type": "application/sparql-results+json"},
            )
        if request.url.path in {"/api/3/action/status_show", "/sharing/rest/search", "/api/search/v1"}:
            return httpx.Response(404)
        return httpx.Response(200, text=html, headers={"content-type": "text/html"})

    with _client(handler) as client:
        row = PortalFingerprinter(client).probe("https://linked.example/")
    assert row is not None
    assert row.portal_type == "sparql"
    assert seen_queries == ["SELECT * WHERE { ?s ?p ?o } LIMIT 1"]
    assert row.connector_spec["update_operations_allowed"] is False


def test_portal_approval_survives_rediscovery(tmp_path: Path):
    db = Database(tmp_path / "fia.sqlite3")
    first = PortalCandidate(
        canonical_url="https://catalog.example", host="catalog.example", portal_type="ckan",
        confidence=0.98, connector_priority_score=90, access_level="public_read_only",
        capabilities=("dataset_search",), evidence=("status",), connector_spec={"adapter": "ckan"},
        source_candidate_ids=(1,), asset_signal_score=80,
    )
    db.upsert_portal_candidates([first])
    row = db.list_portal_candidates()[0]
    assert db.set_portal_candidate_state(row["id"], "approved")
    second = PortalCandidate(
        canonical_url="https://catalog.example", host="catalog.example", portal_type="ckan",
        confidence=0.99, connector_priority_score=95, access_level="public_read_only",
        capabilities=("dataset_search", "recent_changes"), evidence=("new status",), connector_spec={"adapter": "ckan"},
        source_candidate_ids=(1, 2), asset_signal_score=90,
    )
    db.upsert_portal_candidates([second])
    approved = db.list_portal_candidates(state="approved")
    assert len(approved) == 1
    assert approved[0]["connector_priority_score"] == 95


def test_discovery_can_seed_from_existing_dataset_candidates(tmp_path: Path):
    db = Database(tmp_path / "fia.sqlite3")
    source = _candidate(
        catalog_id="uk_data_gov", jurisdiction="United Kingdom", external_id="x",
        title="Unclaimed funds bulk data", description="CSV owner records",
        landing_url="https://portal.example/dataset/unclaimed", formats=["CSV"], keywords=["unclaimed funds"],
        access_level="public", license_value="Open Government Licence", modified_at="2026-08-14",
    )
    db.upsert_source_candidates([source])

    class FakeFingerprinter:
        def __init__(self, client):
            pass
        def probe(self, seed_url, *, source_candidate_ids=(), asset_signal_score=0):
            assert seed_url == "https://portal.example"
            assert source_candidate_ids
            return PortalCandidate(
                canonical_url=seed_url, host="portal.example", portal_type="bulk_download",
                confidence=0.8, connector_priority_score=75, access_level="public_read_only",
                capabilities=("bulk_files",), evidence=("fixture",), connector_spec={"adapter": "bulk_download"},
                source_candidate_ids=tuple(source_candidate_ids), asset_signal_score=asset_signal_score,
            )

    stats = discover_portals(
        db,
        PortalDiscoveryConfig(urls=(), from_source_candidates=True, min_source_score=0, max_seeds=10),
        fingerprinter_factory=FakeFingerprinter,
    )
    assert stats.seeds == 1
    assert stats.saved == 1
    row = db.portal_candidate(db.list_portal_candidates()[0]["id"])
    assert row["connector_spec"]["adapter"] == "bulk_download"
    assert row["source_candidate_ids"]
