from __future__ import annotations

import httpx

API = "https://api.company-information.service.gov.uk"
STREAM_API = "https://stream.companieshouse.gov.uk"


class CompaniesHouseClient:
    """Read-only public company enrichment. Requires a Companies House API key."""

    def __init__(self, api_key: str, client: httpx.Client):
        if not api_key:
            raise ValueError("COMPANIES_HOUSE_API_KEY is required")
        self.api_key = api_key
        self.client = client

    @property
    def auth(self) -> tuple[str, str]:
        return (self.api_key, "")

    def company_profile(self, company_number: str) -> dict:
        response = self.client.get(
            f"{API}/company/{company_number}", auth=self.auth, follow_redirects=True
        )
        response.raise_for_status()
        return response.json()

    def search_dissolved(
        self,
        query: str,
        *,
        search_type: str = "best-match",
        size: int = 100,
        start_index: int = 0,
    ) -> dict:
        if not 1 <= size <= 100:
            raise ValueError("Companies House dissolved-search size must be between 1 and 100")
        response = self.client.get(
            f"{API}/dissolved-search/companies",
            params={
                "q": query,
                "search_type": search_type,
                "size": size,
                "start_index": start_index,
            },
            auth=self.auth,
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.json()

    def advanced_dissolved(
        self,
        *,
        dissolved_from: str,
        dissolved_to: str,
        size: int = 100,
        start_index: int = 0,
        location: str | None = None,
        sic_codes: list[str] | None = None,
    ) -> dict:
        if not 1 <= size <= 5000:
            raise ValueError("Companies House advanced-search size must be between 1 and 5000")
        params: list[tuple[str, str | int]] = [
            ("company_status", "dissolved"),
            ("dissolved_from", dissolved_from),
            ("dissolved_to", dissolved_to),
            ("size", size),
            ("start_index", start_index),
        ]
        if location:
            params.append(("location", location))
        for code in sic_codes or []:
            params.append(("sic_codes", code))
        response = self.client.get(
            f"{API}/advanced-search/companies",
            params=params,
            auth=self.auth,
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.json()

    def filing_history(self, company_number: str, *, items_per_page: int = 100) -> dict:
        response = self.client.get(
            f"{API}/company/{company_number}/filing-history",
            params={"items_per_page": items_per_page},
            auth=self.auth,
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.json()

    def officers(self, company_number: str, *, items_per_page: int = 100) -> dict:
        response = self.client.get(
            f"{API}/company/{company_number}/officers",
            params={"items_per_page": items_per_page}, auth=self.auth, follow_redirects=True
        )
        response.raise_for_status()
        return response.json()

    def persons_with_significant_control(self, company_number: str, *, items_per_page: int = 100) -> dict:
        response = self.client.get(
            f"{API}/company/{company_number}/persons-with-significant-control",
            params={"items_per_page": items_per_page}, auth=self.auth, follow_redirects=True
        )
        response.raise_for_status()
        return response.json()

    def insolvency(self, company_number: str) -> dict:
        response = self.client.get(
            f"{API}/company/{company_number}/insolvency", auth=self.auth, follow_redirects=True
        )
        response.raise_for_status()
        return response.json()

    def officer_appointments(self, officer_id: str, *, items_per_page: int = 100) -> dict:
        response = self.client.get(
            f"{API}/officers/{officer_id}/appointments",
            params={"items_per_page": items_per_page}, auth=self.auth, follow_redirects=True
        )
        response.raise_for_status()
        return response.json()


def normalize_dissolved_items(data: dict) -> list:
    """Normalize Companies House dissolved-company search results into opportunities."""
    from ..models import Opportunity
    from ..scoring import score_opportunity

    rows = []
    for raw in data.get("items") or []:
        number = str(raw.get("company_number") or "").strip().upper()
        name = str(raw.get("company_name") or "").strip()
        if not number or not name:
            continue
        cessation = raw.get("date_of_cessation") or raw.get("date_of_dissolution")
        published_at = None
        if cessation:
            try:
                from datetime import date

                published_at = date.fromisoformat(str(cessation)[:10])
            except ValueError:
                published_at = None
        item = Opportunity(
            source_id="companies_house",
            external_id=number,
            asset_class="dissolved_company",
            title=f"Dissolved company — {name} ({number})",
            jurisdiction="United Kingdom",
            custodian="Companies House",
            source_url=f"https://find-and-update.company-information.service.gov.uk/company/{number}",
            legal_model="open_data_intelligence",
            owner_name=name,
            published_at=published_at,
            compliance_status="public_intelligence_only",
            raw=dict(raw),
        )
        item.score = score_opportunity(item)
        rows.append(item)
    return rows


class CompaniesHouseStreamClient:
    """Bounded reader for Companies House's official read-only streaming API."""

    def __init__(self, stream_key: str, client: httpx.Client):
        if not stream_key:
            raise ValueError("COMPANIES_HOUSE_STREAM_KEY is required")
        self.stream_key = stream_key
        self.client = client

    @property
    def auth(self) -> tuple[str, str]:
        return (self.stream_key, "")

    def company_events(self, *, timepoint: str | None = None, max_events: int = 100) -> tuple[list[dict], str | None]:
        if max_events < 1:
            raise ValueError("max_events must be positive")
        params = {"timepoint": timepoint} if timepoint else None
        events: list[dict] = []
        last_timepoint = timepoint
        timeout = httpx.Timeout(connect=10.0, read=15.0, write=10.0, pool=10.0)
        try:
            with self.client.stream(
                "GET", f"{STREAM_API}/companies", params=params, auth=self.auth,
                follow_redirects=True, timeout=timeout
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    import json
                    envelope = json.loads(line)
                    events.append(envelope)
                    event = envelope.get("event") or {}
                    if event.get("timepoint") is not None:
                        last_timepoint = str(event["timepoint"])
                    if len(events) >= max_events:
                        break
        except httpx.ReadTimeout:
            # A quiet stream is a successful bounded catch-up, not an error.
            pass
        return events, last_timepoint


def normalize_stream_dissolutions(events: list[dict]) -> list:
    """Keep only dissolved/ceased company-profile events as discovery records."""
    from ..models import Opportunity
    from ..scoring import score_opportunity
    from datetime import date

    rows = []
    for envelope in events:
        data = envelope.get("data") or {}
        if not isinstance(data, dict):
            continue
        number = str(data.get("company_number") or "").strip().upper()
        name = str(data.get("company_name") or "").strip()
        status = str(data.get("company_status") or "").strip().lower()
        cessation = data.get("date_of_cessation")
        if not number or not name:
            continue
        if status not in {"dissolved", "converted-closed", "removed", "closed"} and not cessation:
            continue
        published_at = None
        if cessation:
            try:
                published_at = date.fromisoformat(str(cessation)[:10])
            except ValueError:
                pass
        event = envelope.get("event") or {}
        item = Opportunity(
            source_id="companies_house_stream",
            external_id=number,
            asset_class="dissolved_company",
            title=f"Companies House stream dissolution — {name} ({number})",
            jurisdiction="United Kingdom",
            custodian="Companies House",
            source_url=f"https://find-and-update.company-information.service.gov.uk/company/{number}",
            legal_model="open_data_intelligence",
            owner_name=name,
            published_at=published_at,
            compliance_status="public_intelligence_only",
            raw={"stream_event": event, "company_profile": data},
        )
        item.score = score_opportunity(item)
        rows.append(item)
    return rows
