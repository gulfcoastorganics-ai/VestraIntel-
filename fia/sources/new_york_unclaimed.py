from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ..models import Opportunity
from .tabular_unclaimed import normalize_unclaimed_rows, read_tabular_path

SOURCE_URL = "https://www.osc.ny.gov/unclaimed-funds/resources/location-service-providers"


class NewYorkOwnerFile:
    """Importer for the owner-name file legitimately obtained from NY OSC's secure download flow."""

    source_id = "ny_unclaimed_property"

    def from_path(self, path: Path) -> Iterable[Opportunity]:
        rows = read_tabular_path(path)
        yield from normalize_unclaimed_rows(
            rows,
            source_id=self.source_id,
            jurisdiction="New York, USA",
            custodian="New York State Office of the State Comptroller, Office of Unclaimed Funds",
            source_url=SOURCE_URL,
            legal_model="licensed_locator",
            compliance_status="agreement_required",
        )
