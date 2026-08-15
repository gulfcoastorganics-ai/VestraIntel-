from pathlib import Path

from fia.sources.music_rights import SoundExchangeStatusFile, MLCDataFile
from fia.sources.treasury_unpaid import TreasuryCanceledCheckFile
from fia.sources.sam_contracts import SAMContractOpportunitiesFile
from fia.keying import extract_keys


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_soundexchange_file_preserves_owner_only_gate_and_isrc(tmp_path):
    path = _write(
        tmp_path / "sx.csv",
        "Artist,Performer,Sound Recording Owner,ISRC,Status\nExample Band,Jane Doe,Example Records,USABC2600001,Unregistered\n",
    )
    rows = list(SoundExchangeStatusFile().from_path(path))
    assert len(rows) == 1
    row = rows[0]
    assert row.asset_class == "unclaimed_royalty_signal"
    assert row.legal_model == "owner_or_heir_only"
    keys = set(extract_keys(title=row.title, owner_name=row.owner_name, raw_text=str(row.raw)))
    assert ("isrc", "USABC2600001") in keys


def test_mlc_file_is_reconciliation_intelligence(tmp_path):
    path = _write(
        tmp_path / "mlc.csv",
        "Work Title,Writer,Publisher,ISRC,Match Status\nExample Song,Writer One,Example Publishing,USABC2600001,Unmatched\n",
    )
    rows = list(MLCDataFile().from_path(path))
    assert len(rows) == 1
    assert rows[0].source_id == "mlc_data"
    assert rows[0].legal_model == "open_data_intelligence"
    assert rows[0].asset_class == "royalty_metadata_signal"


def test_treasury_check_file_is_research_signal_not_entitlement(tmp_path):
    path = _write(
        tmp_path / "checks.csv",
        "Check Symbol,Check Number,Amount,Issuing Agency\n1234,567890,1250.50,Example Agency\n",
    )
    rows = list(TreasuryCanceledCheckFile().from_path(path))
    assert len(rows) == 1
    assert str(rows[0].face_value) == "1250.50"
    assert rows[0].owner_name is None
    assert rows[0].legal_model == "manual_legal_review"
    assert rows[0].compliance_status == "review_required"


def test_sam_file_maps_public_procurement_signal(tmp_path):
    path = _write(
        tmp_path / "sam.csv",
        "NoticeId,Title,Department,ResponseDeadLine,PostedDate\nN-1,Cloud modernization,Department X,2026-09-01,2026-08-14\n",
    )
    rows = list(SAMContractOpportunitiesFile().from_path(path))
    assert len(rows) == 1
    assert rows[0].external_id == "N-1"
    assert rows[0].asset_class == "contract_opportunity_signal"
    assert rows[0].claim_deadline.isoformat() == "2026-09-01"

from fia.sources.court_funds import BankruptcyUnclaimedFundsFile, OfficialSurplusFundsFile


def test_bankruptcy_file_preserves_successor_gate(tmp_path):
    path = _write(
        tmp_path / "bankruptcy.csv",
        "Creditor,Debtor,Case Number,Amount,Court\nAcme LLC,Debtor Inc,26-12345,15000,Example Bankruptcy Court\n",
    )
    rows = list(BankruptcyUnclaimedFundsFile().from_path(path))
    assert len(rows) == 1
    assert rows[0].asset_class == "bankruptcy_unclaimed_funds"
    assert rows[0].legal_model == "successor_claim"
    assert str(rows[0].face_value) == "15000"


def test_surplus_file_requires_explicit_provenance(tmp_path):
    path = _write(
        tmp_path / "surplus.csv",
        "Former Owner,Case Number,Surplus Amount\nJane Example,2026-001,25000\n",
    )
    rows = list(
        OfficialSurplusFundsFile().from_path(
            path,
            jurisdiction="Example County, Florida, USA",
            custodian="Example County Clerk",
            source_url="https://example.gov/surplus",
        )
    )
    assert len(rows) == 1
    assert rows[0].asset_class == "surplus_funds"
    assert rows[0].jurisdiction.startswith("Example County")
    assert rows[0].source_url == "https://example.gov/surplus"
