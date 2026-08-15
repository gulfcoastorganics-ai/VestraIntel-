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

BANKRUPTCY_URL = "https://www.uscourts.gov/court-programs/bankruptcy/unclaimed-funds-bankruptcy"


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


def _stable(*parts: str | None) -> str:
    return hashlib.sha256("|".join(str(p or "") for p in parts).encode("utf-8", "replace")).hexdigest()[:24]


class BankruptcyUnclaimedFundsFile:
    """Import an official court export/manual record set without bypassing the national locator CAPTCHA."""

    source_id = "us_bankruptcy_unclaimed"

    def from_path(self, path: Path) -> Iterable[Opportunity]:
        for row in read_tabular_path(path):
            creditor = _pick(row, "creditor", "creditor name", "payee", "claimant", "name")
            debtor = _pick(row, "debtor", "debtor name", "case name")
            case_number = _pick(row, "case number", "case no", "bankruptcy case number")
            court = _pick(row, "court", "district", "bankruptcy court")
            amount = _money(_pick(row, "amount", "unclaimed amount", "funds", "balance"))
            claim_no = _pick(row, "claim number", "claim no", "proof of claim number")
            external_id = case_number or _stable(creditor, debtor, court, claim_no, str(amount or ""))
            title = f"Bankruptcy unclaimed funds: {creditor or 'unknown creditor'}"
            if debtor:
                title += f" — {debtor}"
            if amount is not None:
                title += f" — USD {amount:,.2f}"
            raw = dict(row)
            if case_number:
                raw["case_number"] = case_number
            item = Opportunity(
                source_id=self.source_id,
                external_id=str(external_id),
                asset_class="bankruptcy_unclaimed_funds",
                title=title,
                jurisdiction="United States federal bankruptcy court",
                custodian=court or "United States Bankruptcy Court",
                source_url=BANKRUPTCY_URL,
                legal_model="successor_claim",
                owner_name=creditor,
                face_value=amount,
                currency="USD" if amount is not None else None,
                compliance_status="review_required",
                notes="Court-held funds signal; original owner/successor entitlement and court-specific documentation must be proven.",
                raw=raw,
            )
            item.score = score_opportunity(item)
            yield item


class OfficialSurplusFundsFile:
    """Import an official county/court surplus-funds dataset with explicit provenance.

    FIA deliberately does not encode a universal finder fee or assignment rule for this class.
    """

    source_id = "official_surplus_funds"

    def from_path(
        self,
        path: Path,
        *,
        jurisdiction: str,
        custodian: str,
        source_url: str,
    ) -> Iterable[Opportunity]:
        for row in read_tabular_path(path):
            owner = _pick(row, "former owner", "owner", "owner name", "claimant", "name")
            case_number = _pick(row, "case number", "case no", "tax deed number", "sale number", "file number")
            amount = _money(_pick(row, "surplus", "surplus amount", "excess proceeds", "amount", "balance"))
            sale_type = _pick(row, "sale type", "type", "proceeding") or "surplus funds"
            property_ref = _pick(row, "parcel", "parcel id", "property id", "folio", "account")
            external_id = case_number or _stable(owner, property_ref, str(amount or ""), jurisdiction)
            title = f"Official {sale_type}: {owner or 'unknown apparent owner'}"
            if amount is not None:
                title += f" — USD {amount:,.2f}"
            item = Opportunity(
                source_id=self.source_id,
                external_id=str(external_id),
                asset_class="surplus_funds",
                title=title,
                jurisdiction=jurisdiction,
                custodian=custodian,
                source_url=source_url,
                legal_model="manual_legal_review",
                owner_name=owner,
                face_value=amount,
                currency="USD" if amount is not None else None,
                compliance_status="review_required",
                notes="Official surplus-funds signal; fee, assignment, priority, deadline, and entitlement rules are jurisdiction-specific.",
                raw=dict(row),
            )
            item.score = score_opportunity(item)
            yield item
