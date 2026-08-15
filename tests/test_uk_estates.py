import httpx

from fia.sources.uk_unclaimed_estates import UKUnclaimedEstates


def test_parse_estate_csv():
    text = "Surname,Forenames,Date of Death,Place of Death,BVD Reference,Date Advertised\nSmith,Jane,01/02/2024,Leeds,BV123,10/08/2026\n"
    adapter = UKUnclaimedEstates(httpx.Client())
    rows = list(adapter.parse(text))
    assert len(rows) == 1
    assert rows[0].owner_name == "Jane Smith"
    assert rows[0].published_at.isoformat() == "2026-08-10"
