import httpx

from fia.sources.companies_house import CompaniesHouseClient


def test_dissolved_search_uses_official_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/dissolved-search/companies"
        assert request.url.params["q"] == "example"
        assert request.url.params["search_type"] == "best-match"
        assert request.headers.get("authorization", "").startswith("Basic ")
        return httpx.Response(200, json={"items": [{"company_number": "01234567"}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = CompaniesHouseClient("test-key", client).search_dissolved("example")
    assert result["items"][0]["company_number"] == "01234567"


def test_company_research_endpoints_use_read_only_public_data_paths():
    seen = []
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={"items": []})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        ch = CompaniesHouseClient("test-key", client)
        ch.officers("01234567")
        ch.persons_with_significant_control("01234567")
        ch.insolvency("01234567")
    assert seen == [
        "/company/01234567/officers",
        "/company/01234567/persons-with-significant-control",
        "/company/01234567/insolvency",
    ]
