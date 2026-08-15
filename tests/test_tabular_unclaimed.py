import io
import zipfile
from decimal import Decimal
from pathlib import Path

from fia.sources.california_unclaimed import CaliforniaUnclaimedProperty
from fia.sources.new_york_unclaimed import NewYorkOwnerFile
from fia.sources.tabular_unclaimed import normalize_unclaimed_rows, read_tabular_path


def _california_zip_bytes(row_count: int = 1) -> bytes:
    rows = [
        "Property ID,Owner Name,Property Type,Reported Amount,Holder Name,Report Year"
    ]
    rows.extend(
        f"CA-{index},Owner {index},Uncashed Check,{index + 1},Example Bank,2024"
        for index in range(row_count)
    )
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("california.csv", "\n".join(rows) + "\n")
    return payload.getvalue()


def test_california_bulk_download_streams_without_accessing_content():
    payload = _california_zip_bytes()

    class StreamingResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        @property
        def content(self):
            raise AssertionError("bulk response.content must not be accessed")

        def raise_for_status(self):
            return None

        def iter_bytes(self, chunk_size):
            assert chunk_size == 64 * 1024
            for offset in range(0, len(payload), 17):
                yield payload[offset:offset + 17]

    class StreamingClient:
        def __init__(self):
            self.calls = []

        def stream(self, method, url, **kwargs):
            self.calls.append((method, url, kwargs))
            return StreamingResponse()

    client = StreamingClient()
    items = list(CaliforniaUnclaimedProperty(client).fetch(bucket="500_plus"))

    assert len(items) == 1
    assert items[0].external_id == "CA-0"
    assert client.calls[0][0] == "GET"
    assert client.calls[0][2]["follow_redirects"] is True
    assert client.calls[0][2]["timeout"] == 180


def test_zip_rows_are_lazy_and_members_are_never_read_wholesale(tmp_path: Path, monkeypatch):
    path = tmp_path / "many-records.zip"
    path.write_bytes(_california_zip_bytes(row_count=5000))

    def fail_read(*args, **kwargs):
        raise AssertionError("ZipFile.read must not be used for bulk members")

    monkeypatch.setattr(zipfile.ZipFile, "read", fail_read)
    rows = read_tabular_path(path)

    assert not isinstance(rows, list)
    iterator = iter(rows)
    assert iterator is rows
    assert next(iterator)["Property ID"] == "CA-0"
    iterator.close()


def test_plain_cp1252_rows_stream_with_bounded_encoding_fallback(tmp_path: Path):
    path = tmp_path / "cp1252.csv"
    path.write_bytes("Property ID,Owner Name\nCA-1,Jos\xe9\n".encode("cp1252"))

    rows = read_tabular_path(path)

    assert not isinstance(rows, list)
    assert next(iter(rows))["Owner Name"] == "Jos\xe9"


def test_normalize_unclaimed_rows_accepts_a_row_generator():
    rows = (
        row for row in [{
            "Property ID": "CA-streamed",
            "Owner Name": "Ada Lovelace",
            "Property Type": "Uncashed Check",
            "Reported Amount": "$12.50",
        }]
    )

    items = normalize_unclaimed_rows(
        rows,
        source_id="ca_unclaimed_property",
        jurisdiction="California, USA",
        custodian="California State Controller's Office",
        source_url="https://example.test/california",
        legal_model="licensed_locator",
        compliance_status="agreement_and_law_review",
    )
    item = next(iter(items))

    assert item.external_id == "CA-streamed"
    assert item.owner_name == "Ada Lovelace"
    assert item.face_value == Decimal("12.50")


def test_california_csv_parser(tmp_path: Path):
    path = tmp_path / "ca.csv"
    path.write_text(
        "Property ID,Owner First Name,Owner Last Name,Property Type,Reported Amount,Holder Name,Report Year\n"
        "CA-1,Ada,Lovelace,Uncashed Check,$1250.50,Example Bank,2024\n",
        encoding="utf-8",
    )
    adapter = CaliforniaUnclaimedProperty(client=None)  # file import does not use HTTP
    items = list(adapter.from_path(path))
    assert len(items) == 1
    assert items[0].external_id == "CA-1"
    assert items[0].owner_name == "Ada Lovelace"
    assert items[0].face_value == Decimal("1250.50")
    assert items[0].jurisdiction == "California, USA"


def test_new_york_pipe_delimited_parser(tmp_path: Path):
    path = tmp_path / "ny.txt"
    path.write_text(
        "Owner Name|Nature of Property|Reported By|Date Reported\n"
        "Example Studio LLC|Royalty|Example Holder|2025\n",
        encoding="utf-8",
    )
    items = list(NewYorkOwnerFile().from_path(path))
    assert len(items) == 1
    assert items[0].owner_name == "Example Studio LLC"
    assert items[0].face_value is None
    assert items[0].compliance_status == "agreement_required"
