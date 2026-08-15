from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from collections.abc import Iterable
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from ..models import Opportunity
from ..scoring import score_opportunity


def _norm_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _pick(row: dict[str, Any], *aliases: str) -> str | None:
    normalized = {_norm_header(str(k)): v for k, v in row.items() if k is not None}
    for alias in aliases:
        value = normalized.get(_norm_header(alias))
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


def _date(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y", "%m-%d-%Y"):
        try:
            from datetime import datetime

            parsed = datetime.strptime(value, fmt)
            return parsed.date()
        except ValueError:
            continue
    return None


def _owner_name(row: dict[str, Any]) -> str | None:
    direct = _pick(
        row,
        "owner name",
        "owner_name",
        "name",
        "reported owner name",
        "potential owner",
        "owner",
    )
    if direct:
        return direct
    first = _pick(row, "first name", "owner first name", "firstname", "ownerfirstname")
    middle = _pick(row, "middle name", "middle initial", "owner middle name", "middlename")
    last = _pick(row, "last name", "owner last name", "lastname", "ownerlastname")
    business = _pick(row, "business name", "owner business name", "entity name")
    if business:
        return business
    parts = [part for part in (first, middle, last) if part]
    return " ".join(parts) or None


def _row_id(row: dict[str, Any], owner_name: str | None) -> str:
    direct = _pick(
        row,
        "property id",
        "property_id",
        "record id",
        "record_id",
        "property number",
        "account number",
        "account",
        "id",
    )
    if direct:
        return direct
    stable = "|".join(
        str(row.get(key, "")).strip() for key in sorted(row, key=lambda k: str(k).lower())
    )
    if owner_name:
        stable = f"{owner_name}|{stable}"
    return hashlib.sha256(stable.encode("utf-8", "replace")).hexdigest()[:24]


def read_tabular_path(path: Path) -> list[dict[str, str]]:
    """Read CSV/TXT or a ZIP containing one or more delimited text files."""
    raw_files: list[tuple[str, bytes]] = []
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if name.lower().endswith((".csv", ".txt")) and not name.endswith("/"):
                    raw_files.append((name, zf.read(name)))
    else:
        raw_files.append((path.name, path.read_bytes()))

    rows: list[dict[str, str]] = []
    for _name, payload in raw_files:
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = payload.decode("cp1252", errors="replace")
        sample = text[:8192]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t|;")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        for row in reader:
            if row and any(str(v or "").strip() for v in row.values()):
                rows.append({str(k): str(v or "") for k, v in row.items() if k is not None})
    return rows


def normalize_unclaimed_rows(
    rows: Iterable[dict[str, Any]],
    *,
    source_id: str,
    jurisdiction: str,
    custodian: str,
    source_url: str,
    legal_model: str,
    compliance_status: str,
    currency: str = "USD",
) -> Iterable[Opportunity]:
    for row in rows:
        owner = _owner_name(row)
        property_type = _pick(
            row,
            "property type",
            "property_type",
            "nature of property",
            "property description",
            "type",
        ) or "Unclaimed property"
        holder = _pick(
            row,
            "reported by",
            "holder name",
            "holder",
            "reporting holder",
            "company name",
            "reported holder",
        )
        amount = _money(
            _pick(
                row,
                "reported amount",
                "property amount",
                "amount",
                "cash reported",
                "value",
                "current cash value",
            )
        )
        published_at = _date(
            _pick(row, "reported date", "date reported", "report year", "reported year")
        )
        external_id = _row_id(row, owner)
        title_parts = [owner or "Unknown owner", property_type]
        if amount is not None:
            title_parts.append(f"{currency} {amount:,.2f}")
        if holder:
            title_parts.append(f"reported by {holder}")
        item = Opportunity(
            source_id=source_id,
            external_id=external_id,
            asset_class="unclaimed_funds",
            title=" — ".join(title_parts),
            jurisdiction=jurisdiction,
            custodian=custodian,
            source_url=source_url,
            legal_model=legal_model,
            owner_name=owner,
            face_value=amount,
            currency=currency if amount is not None else None,
            published_at=published_at,
            compliance_status=compliance_status,
            raw=dict(row),
        )
        item.score = score_opportunity(item)
        yield item
