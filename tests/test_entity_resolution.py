from pathlib import Path

from fia.db import Database
from fia.entity_resolution import rebuild_entity_graph
from fia.models import Opportunity


def opportunity(source: str, external: str, owner: str, raw: dict) -> Opportunity:
    return Opportunity(
        source_id=source,
        external_id=external,
        asset_class="test_asset",
        title=f"Signal for {owner}",
        jurisdiction="Test",
        custodian="Test",
        source_url=f"https://example.test/{external}",
        legal_model="open_data_intelligence",
        owner_name=owner,
        raw=raw,
    )


def test_entity_graph_uses_identifiers_and_conservative_name_variants(tmp_path: Path):
    db = Database(tmp_path / "fia.sqlite3")
    db.upsert_with_stats(
        [
            opportunity("source_a", "1", "Acme Technologies LLC", {"company_number": "01234567"}),
            opportunity("source_b", "2", "ACME Technologies LLC", {"company no": "01234567"}),
            opportunity("source_c", "3", "Acme Technology Limited", {}),
            opportunity("source_a", "4", "John Smith", {}),
            opportunity("source_b", "5", "Jon Smith", {}),
        ]
    )

    stats = rebuild_entity_graph(db, fuzzy=True, fuzzy_limit=100, min_fuzzy_score=0.88)
    assert stats.entities >= 5

    orgs = db.list_entities(limit=20, min_sources=2, entity_type="organization")
    assert any(row["display_name"].lower() == "acme technologies llc" for row in orgs)

    relations = db.list_entity_relations(
        limit=50, relation_type="possible_same_organization", min_confidence=0.88
    )
    assert any("Acme" in row["left_name"] or "Acme" in row["right_name"] for row in relations)
    # Person typo/fuzzy matching is deliberately disabled.
    assert not any("John Smith" in (row["left_name"], row["right_name"]) for row in relations)


def test_company_number_from_json_style_key_creates_strong_entity(tmp_path: Path):
    db = Database(tmp_path / "fia.sqlite3")
    db.upsert([opportunity("companies_house", "x", "Example Ltd", {"company_number": "SC123456"})])
    rebuild_entity_graph(db, fuzzy=False)
    entities = db.list_entities(limit=20, min_sources=1)
    assert any(row["canonical_key"] == "company_number:SC123456" for row in entities)
