import httpx

from fia.sources.uspto_og import USPTOOfficialGazette


def test_parse_license_and_expiration_signals():
    html = """
    <html><body>
    January 13, 2026 | US PATENT AND TRADEMARK OFFICE
    <h2>Notice of Expiration of Patents Due to Failure to Pay Maintenance Fee</h2>
    8,468,613 12/982,621 06/25/2013
    <h2>Patents Reinstated Due</h2>
    <h2>Patents and Patent Applications Available for License or Sale</h2>
    9,871,896 CELLULAR PHONE IN A BODY OF A HOME/OFFICE TELEPHONE
    Contact: Example
    <div>Top of Notices</div>
    </body></html>
    """
    adapter = USPTOOfficialGazette(httpx.Client(), "https://example.test")
    rows = list(adapter.parse(html, "https://example.test"))
    classes = {r.asset_class for r in rows}
    assert "patent_expiration" in classes
    assert "patent_license_offer" in classes
