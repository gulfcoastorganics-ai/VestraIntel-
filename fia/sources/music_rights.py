from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ..models import Opportunity
from ..scoring import score_opportunity
from .tabular_unclaimed import read_tabular_path

SOUNDEXCHANGE_URL = "https://www.soundexchange.com/what-we-do/for-artists-labels-and-producers/"
MLC_URL = "https://www.themlc.com/dataprograms"


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _pick(row: dict[str, Any], *aliases: str) -> str | None:
    normalized = {_norm(str(k)): v for k, v in row.items() if k is not None}
    for alias in aliases:
        value = normalized.get(_norm(alias))
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _stable_id(*parts: str | None) -> str:
    payload = "|".join(str(p or "").strip().lower() for p in parts)
    return hashlib.sha256(payload.encode("utf-8", "replace")).hexdigest()[:24]


class SoundExchangeStatusFile:
    """Import a legitimately obtained public SoundExchange unclaimed-status list/export.

    The imported row is an owner/rightsholder lead only. FIA does not treat it as permission to
    claim, broker, or redirect royalties.
    """

    source_id = "soundexchange_unclaimed"

    def from_path(self, path: Path) -> Iterable[Opportunity]:
        for row in read_tabular_path(path):
            artist = _pick(row, "artist", "artist name", "creator", "name")
            performer = _pick(row, "performer", "performer name", "unregistered performer")
            owner = _pick(
                row,
                "sound recording owner",
                "sound recording owner name",
                "recording owner",
                "label",
                "owner",
            )
            isrc = _pick(row, "isrc", "recording isrc")
            status = _pick(row, "status", "list status", "registration status") or "unclaimed_status"
            display = artist or performer or owner or "Unknown creator/rightsholder"
            external_id = _stable_id(display, performer, owner, isrc, status)
            raw = dict(row)
            if isrc:
                raw["isrc"] = isrc.upper().replace("-", "")
            item = Opportunity(
                source_id=self.source_id,
                external_id=external_id,
                asset_class="unclaimed_royalty_signal",
                title=f"SoundExchange {status}: {display}",
                jurisdiction="United States",
                custodian="SoundExchange",
                source_url=SOUNDEXCHANGE_URL,
                legal_model="owner_or_heir_only",
                owner_name=owner or performer or artist,
                compliance_status="owner_only",
                notes="Public unclaimed-status signal; entitlement remains with the qualifying creator/rightsholder.",
                raw=raw,
            )
            item.score = score_opportunity(item)
            yield item


class MLCDataFile:
    """Import an authorized MLC export/BWARM-derived CSV or reconciliation work file."""

    source_id = "mlc_data"

    def from_path(self, path: Path) -> Iterable[Opportunity]:
        for row in read_tabular_path(path):
            title = _pick(row, "work title", "title", "musical work title", "recording title")
            writer = _pick(row, "writer", "writer name", "songwriter")
            publisher = _pick(row, "publisher", "publisher name", "administrator")
            isrc = _pick(row, "isrc", "recording isrc")
            work_id = _pick(row, "mlc work id", "work id", "mlc id", "song code")
            status = _pick(row, "match status", "status", "claim status") or "metadata_signal"
            display = title or work_id or isrc or "Unknown musical work"
            external_id = work_id or _stable_id(display, writer, publisher, isrc, status)
            raw = dict(row)
            if isrc:
                raw["isrc"] = isrc.upper().replace("-", "")
            item = Opportunity(
                source_id=self.source_id,
                external_id=str(external_id),
                asset_class="royalty_metadata_signal",
                title=f"MLC {status}: {display}",
                jurisdiction="United States",
                custodian="The Mechanical Licensing Collective",
                source_url=MLC_URL,
                legal_model="open_data_intelligence",
                owner_name=publisher or writer,
                compliance_status="public_intelligence_only",
                notes="Authorized metadata/reconciliation signal; FIA does not claim royalties for third parties.",
                raw=raw,
            )
            item.score = score_opportunity(item)
            yield item
