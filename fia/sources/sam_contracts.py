from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models import Opportunity
from ..scoring import score_opportunity
from .tabular_unclaimed import read_tabular_path

SOURCE_URL = "https://sam.gov/data-services/Contract%20Opportunities/datagov?privacy=Public"


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _pick(row: dict[str, Any], *aliases: str) -> str | None:
    normalized = {_norm(str(k)): v for k, v in row.items() if k is not None}
    for alias in aliases:
        value = normalized.get(_norm(alias))
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _date(value: str | None):
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(value.strip().replace("Z", "+0000"), fmt).date()
        except ValueError:
            continue
    return None


class SAMContractOpportunitiesFile:
    """Import SAM.gov's public Contract Opportunities CSV/file extracts for intelligence routing."""

    source_id = "sam_contract_opportunities"

    def from_path(self, path: Path) -> Iterable[Opportunity]:
        for row in read_tabular_path(path):
            notice_id = _pick(row, "notice id", "noticeid", "id")
            solicitation = _pick(row, "solicitation number", "solicitationnumber")
            title = _pick(row, "title", "opportunity title") or "Federal contract opportunity"
            agency = _pick(row, "department/ind agency", "department", "agency", "organization")
            deadline = _date(_pick(row, "response deadline", "responsedeadline", "response date"))
            published = _date(_pick(row, "posted date", "posteddate", "publish date"))
            ext = notice_id or solicitation
            if not ext:
                ext = hashlib.sha256(repr(sorted(row.items())).encode("utf-8", "replace")).hexdigest()[:24]
            item = Opportunity(
                source_id=self.source_id,
                external_id=str(ext),
                asset_class="contract_opportunity_signal",
                title=title,
                jurisdiction="United States",
                custodian=agency or "SAM.gov / federal contracting office",
                source_url=SOURCE_URL,
                legal_model="open_data_intelligence",
                published_at=published,
                claim_deadline=deadline,
                compliance_status="public_intelligence_only",
                notes="Public procurement intelligence; bidding/representation requirements are separate from FIA discovery.",
                raw=dict(row),
            )
            item.score = score_opportunity(item)
            yield item
