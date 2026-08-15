from pathlib import Path

from fia.db import Database
from fia.models import Opportunity


def item(title: str) -> Opportunity:
    return Opportunity(
        source_id="test",
        external_id="1",
        asset_class="unclaimed_funds",
        title=title,
        jurisdiction="Test",
        custodian="Test Custodian",
        source_url="https://example.test/1",
        legal_model="open_data_intelligence",
        owner_name="Example Owner",
    )


def test_change_tracking(tmp_path: Path):
    db = Database(tmp_path / "fia.sqlite3")
    first = db.upsert_with_stats([item("Version one")])
    same = db.upsert_with_stats([item("Version one")])
    changed = db.upsert_with_stats([item("Version two")])
    assert (first.new, first.changed, first.unchanged) == (1, 0, 0)
    assert (same.new, same.changed, same.unchanged) == (0, 0, 1)
    assert (changed.new, changed.changed, changed.unchanged) == (0, 1, 0)
    rows = db.recent_changes(limit=10)
    assert rows[0]["change_count"] == 1
    assert rows[0]["title"] == "Version two"


def test_upsert_with_stats_consumes_an_opportunity_generator(tmp_path: Path):
    db = Database(tmp_path / "fia.sqlite3")
    consumed: list[int] = []

    def opportunities():
        for index in range(3):
            consumed.append(index)
            opportunity = item(f"Streamed {index}")
            opportunity.external_id = str(index)
            yield opportunity

    stats = db.upsert_with_stats(opportunities())

    assert consumed == [0, 1, 2]
    assert (stats.total, stats.new, stats.changed, stats.unchanged) == (3, 3, 0, 0)
    assert len(db.list_opportunities(limit=10)) == 3
