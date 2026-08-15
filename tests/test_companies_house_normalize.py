from fia.sources.companies_house import normalize_dissolved_items


def test_normalize_dissolved_items():
    rows = normalize_dissolved_items(
        {
            "items": [
                {
                    "company_name": "EXAMPLE TECHNOLOGIES LTD",
                    "company_number": "01234567",
                    "company_status": "dissolved",
                    "date_of_cessation": "2026-08-01",
                }
            ]
        }
    )
    assert len(rows) == 1
    assert rows[0].external_id == "01234567"
    assert rows[0].owner_name == "EXAMPLE TECHNOLOGIES LTD"
    assert rows[0].asset_class == "dissolved_company"
