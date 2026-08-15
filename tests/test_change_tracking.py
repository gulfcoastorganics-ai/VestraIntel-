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
