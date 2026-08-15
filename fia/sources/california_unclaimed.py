from __future__ import annotations

import tempfile
from collections.abc import Iterable
from pathlib import Path

import httpx

from ..models import Opportunity
from .tabular_unclaimed import normalize_unclaimed_rows, read_tabular_path

PAGE_URL = "https://www.sco.ca.gov/upd_download_property_records.html"
BUCKET_URLS = {
    "under_10": "https://claimit.ca.gov/upd-property-records/01_From_0_To_Below_10.zip",
    "10_to_99": "https://claimit.ca.gov/upd-property-records/02_From_10_To_Below_100.zip",
    "100_to_499": "https://claimit.ca.gov/upd-property-records/03_From_100_To_Below_500.zip",
    "500_plus": "https://claimit.ca.gov/upd-property-records/04_From_500_To_Beyond.zip",
    "all": "https://claimit.ca.gov/upd-property-records/00_All_Records.zip",
}


class CaliforniaUnclaimedProperty:
    source_id = "ca_unclaimed_property"

    def __init__(self, client: httpx.Client):
        self.client = client

    def fetch(self, *, bucket: str = "500_plus") -> Iterable[Opportunity]:
        if bucket not in BUCKET_URLS:
            raise ValueError(f"Unknown California bucket: {bucket}")
        with self.client.stream(
            "GET", BUCKET_URLS[bucket], follow_redirects=True, timeout=180
        ) as response:
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(suffix=".zip") as tmp:
                for chunk in response.iter_bytes(chunk_size=64 * 1024):
                    tmp.write(chunk)
                tmp.flush()
                yield from self.from_path(Path(tmp.name))

    def from_path(self, path: Path) -> Iterable[Opportunity]:
        rows = read_tabular_path(path)
        yield from normalize_unclaimed_rows(
            rows,
            source_id=self.source_id,
            jurisdiction="California, USA",
            custodian="California State Controller's Office",
            source_url=PAGE_URL,
            legal_model="licensed_locator",
            compliance_status="agreement_and_law_review",
        )
