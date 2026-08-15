from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime

import httpx

from fia.models import Opportunity
from fia.scoring import score_opportunity
from fia.sources.base import SourceAdapter

CSV_URL = (
    "https://assets.publishing.service.gov.uk/media/6a799b3e29aec7cd59ccc06d/"
    "UnclaimedEstatesList.csv"
)
PAGE_URL = "https://www.gov.uk/government/statistical-data-sets/unclaimed-estates-list"


def _pick(row: dict[str, str], *names: str) -> str | None:
    normalized = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
    for name in names:
        value = normalized.get(name.lower())
        if value:
            return value
    return None


def _date(value: str | None):
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d %B %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


class UKUnclaimedEstates(SourceAdapter):
    source_id = "uk_unclaimed_estates"

    def __init__(self, client: httpx.Client):
        self.client = client

    def fetch(self):
        response = self.client.get(CSV_URL, follow_redirects=True)
        response.raise_for_status()
        yield from self.parse(response.text)

    def parse(self, text: str):
        reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
        for row in reader:
            surname = _pick(row, "surname", "last name")
            forenames = _pick(row, "forename", "forenames", "first name", "first names")
            name = " ".join(part for part in (forenames, surname) if part) or "Unknown estate"
            date_of_death = _date(_pick(row, "date of death", "dod"))
            place = _pick(row, "place of death", "place of birth", "location")
            reference = _pick(row, "bvd reference", "reference", "case reference")
            identity_seed = reference or f"{name}|{date_of_death}|{place}"
            external_id = hashlib.sha256(identity_seed.encode()).hexdigest()[:24]
            published = _date(_pick(row, "date advertised", "advertised", "date added"))
            item = Opportunity(
                source_id=self.source_id,
                external_id=external_id,
                asset_class="unclaimed_estate",
                title=f"Unclaimed estate: {name}",
                owner_name=name,
                jurisdiction="England & Wales",
                custodian="UK Bona Vacantia Division",
                source_url=PAGE_URL,
                legal_model="owner_or_heir_only",
                published_at=published,
                compliance_status="owner_only",
                notes=(f"Date of death: {date_of_death}; place: {place}" if date_of_death or place else None),
                raw=row,
            )
            item.score = score_opportunity(item)
            yield item
