from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any


@dataclass
class Opportunity:
    source_id: str
    external_id: str
    asset_class: str
    title: str
    jurisdiction: str
    custodian: str
    source_url: str
    legal_model: str
    owner_name: str | None = None
    face_value: Decimal | None = None
    currency: str | None = None
    published_at: date | None = None
    claim_deadline: date | None = None
    status: str = "discovered"
    compliance_status: str = "review_required"
    score: float = 0.0
    notes: str | None = None
    raw: dict[str, Any] | None = None
    ingested_at: datetime | None = None

    def as_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["face_value"] = str(self.face_value) if self.face_value is not None else None
        record["published_at"] = self.published_at.isoformat() if self.published_at else None
        record["claim_deadline"] = self.claim_deadline.isoformat() if self.claim_deadline else None
        record["ingested_at"] = (self.ingested_at or datetime.now(timezone.utc)).isoformat()
        return record
