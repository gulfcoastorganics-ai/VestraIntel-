from pathlib import Path

from fia.db import Database


def test_source_run_lifecycle(tmp_path: Path):
    db = Database(tmp_path / "fia.sqlite3")
    run_id = db.begin_run("ca_unclaimed_property")
    db.finish_run(run_id, record_count=42)
    row = db.list_runs(limit=1)[0]
    assert row["status"] == "completed"
    assert row["record_count"] == 42
