from decimal import Decimal
from pathlib import Path

from fia.sources.california_unclaimed import CaliforniaUnclaimedProperty
from fia.sources.new_york_unclaimed import NewYorkOwnerFile


def test_california_csv_parser(tmp_path: Path):
    path = tmp_path / "ca.csv"
    path.write_text(
        "Property ID,Owner First Name,Owner Last Name,Property Type,Reported Amount,Holder Name,Report Year\n"
        "CA-1,Ada,Lovelace,Uncashed Check,$1250.50,Example Bank,2024\n",
        encoding="utf-8",
    )
    adapter = CaliforniaUnclaimedProperty(client=None)  # file import does not use HTTP
    items = list(adapter.from_path(path))
    assert len(items) == 1
    assert items[0].external_id == "CA-1"
    assert items[0].owner_name == "Ada Lovelace"
    assert items[0].face_value == Decimal("1250.50")
    assert items[0].jurisdiction == "California, USA"


def test_new_york_pipe_delimited_parser(tmp_path: Path):
    path = tmp_path / "ny.txt"
    path.write_text(
        "Owner Name|Nature of Property|Reported By|Date Reported\n"
        "Example Studio LLC|Royalty|Example Holder|2025\n",
        encoding="utf-8",
    )
    items = list(NewYorkOwnerFile().from_path(path))
    assert len(items) == 1
    assert items[0].owner_name == "Example Studio LLC"
    assert items[0].face_value is None
    assert items[0].compliance_status == "agreement_required"
