from fia.db import Database
from fia.entity_resolution import rebuild_entity_graph
from fia.models import Opportunity


def test_official_previous_name_and_address_become_graph_relations(tmp_path):
    db = Database(tmp_path / "fia.db")
    db.upsert([Opportunity(
        source_id="companies_house", external_id="01234567", asset_class="dissolved_company",
        title="Dissolved Acme Technologies Limited", owner_name="Acme Technologies Limited",
        jurisdiction="United Kingdom", custodian="Companies House",
        source_url="https://example.gov/company", legal_model="open_data_intelligence",
        compliance_status="public_intelligence_only",
        raw={
            "company_number": "01234567",
            "previous_company_names": [{"name": "Acme Systems Limited"}],
            "registered_office_address": {"address_line_1": "1 Example Road", "locality": "London", "postal_code": "SW1A 1AA"},
        },
    )])
    rebuild_entity_graph(db, fuzzy=False)
    rels = db.list_entity_relations(limit=50)
    types = {r["relation_type"] for r in rels}
    assert "previous_company_name_of" in types
    assert "registered_office_at" in types
