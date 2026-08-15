from __future__ import annotations

import httpx

API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"


class USASpendingClient:
    """Thin read-only wrapper for the public USAspending V2 awards search API."""

    def __init__(self, client: httpx.Client):
        self.client = client

    def search_awards(self, payload: dict) -> dict:
        response = self.client.post(API, json=payload)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def contracts_payload(start_date: str, end_date: str, *, limit: int = 100, page: int = 1) -> dict:
        return {
            "subawards": False,
            "limit": limit,
            "page": page,
            "filters": {
                "time_period": [{"start_date": start_date, "end_date": end_date}],
                "award_type_codes": ["A", "B", "C", "D"],
            },
            "fields": [
                "Award ID",
                "Recipient Name",
                "Start Date",
                "End Date",
                "Award Amount",
                "Awarding Agency",
                "Awarding Sub Agency",
                "Award Type",
                "Description",
            ],
            "sort": "End Date",
            "order": "asc",
        }
