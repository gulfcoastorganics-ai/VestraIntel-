from fia.keying import extract_keys


def test_extracts_name_patent_and_isrc():
    keys = set(extract_keys(
        title="Patent 9,871,896 opportunity",
        owner_name="Acme Music, LLC",
        raw_text='ISRC USABC2600123 {"company_number": "01234567"}',
    ))
    assert ("owner_name", "acme music llc") in keys
    assert ("patent_number", "9,871,896") in keys
    assert ("isrc", "USABC2600123") in keys
    assert ("company_number", "01234567") in keys
