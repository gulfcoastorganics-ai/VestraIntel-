from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from ..models import Opportunity
from ..scoring import score_opportunity
from .tabular_unclaimed import read_tabular_path

SOURCE_URL = "https://fiscal.treasury.gov/about-us/unclaimed-assets"


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _pick(row: dict[str, Any], *aliases: str) -> str | None:
    normalized = {_norm(str(k)): v for k, v in row.items() if k is not None}
    for alias in aliases:
        value = normalized.get(_norm(alias))
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _money(value: str | None) -> Decimal | None:
    if not value:
        return None
    cleaned = re.sub(r"[^0-9.()\-]", "", value.replace(",", ""))
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"
    try:
        return Decimal(cleaned) if cleaned else None
    except InvalidOperation:
        return None


class TreasuryCanceledCheckFile:
    """Import Treasury/Federal-agency canceled or unpaid-check data obtained lawfully (e.g. FOIA).

    Treasury cancellation lists are not personal-identifier indexes. A row is therefore a research
    signal until the issuing agency independently identifies the lawful payee and confirms status.
    """

    source_id = "treasury_unpaid_checks_foia"

    def from_path(self, path: Path) -> Iterable[Opportunity]:
        for row in read_tabular_path(path):
            symbol = _pick(row, "check symbol", "symbol", "check symbol number")
            number = _pick(row, "check number", "serial number", "check serial")
            amount = _money(_pick(row, "amount", "check amount", "dollar amount"))
            agency = _pick(row, "agency", "issuing agency", "certifying agency")
            payee = _pick(row, "payee", "payee name", "beneficiary")
            stable = "|".join(v or "" for v in (symbol, number, agency, str(amount or ""), payee))
            external_id = hashlib.sha256(stable.encode("utf-8", "replace")).hexdigest()[:24]
            title = f"Canceled/unpaid federal check {symbol or '?'}-{number or '?'}"
            if amount is not None:
                title += f" — USD {amount:,.2f}"
            if agency:
                title += f" — {agency}"
            item = Opportunity(
                source_id=self.source_id,
                external_id=external_id,
                asset_class="federal_unpaid_check_signal",
                title=title,
                jurisdiction="United States",
                custodian=agency or "U.S. federal certifying agency",
                source_url=SOURCE_URL,
                legal_model="manual_legal_review",
                owner_name=payee,
                face_value=amount,
                currency="USD" if amount is not None else None,
                compliance_status="review_required",
                notes="Locator-research signal only; issuing agency must identify/confirm the lawful payee and payment status.",
                raw=dict(row),
            )
            item.score = score_opportunity(item)
            yield item
