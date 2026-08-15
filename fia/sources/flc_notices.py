from __future__ import annotations

import hashlib
import re
from datetime import datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from fia.models import Opportunity
from fia.scoring import score_opportunity
from fia.sources.base import SourceAdapter

URL = "https://federallabs.org/flc-business/notice-of-intent-to-license"


class FLCLicenseNotices(SourceAdapter):
    source_id = "flc_license_notices"

    def __init__(self, client: httpx.Client):
        self.client = client

    def fetch(self):
        response = self.client.get(URL, follow_redirects=True)
        response.raise_for_status()
        yield from self.parse(response.text)

    def parse(self, html: str):
        soup = BeautifulSoup(html, "html.parser")
        seen: set[str] = set()
        for link in soup.find_all("a", href=True):
            href = str(link.get("href"))
            text = " ".join(link.stripped_strings)
            if "notice-of-intent-to-license/" not in href or not text:
                continue
            full_url = urljoin(URL, href)
            if full_url in seen or full_url.rstrip("/") == URL.rstrip("/"):
                continue
            seen.add(full_url)
            context = " ".join(link.parent.stripped_strings) if link.parent else text
            date_match = re.search(r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{1,2}, 20\d{2}", context)
            published = datetime.strptime(date_match.group(0), "%b %d, %Y").date() if date_match else None
            external_id = hashlib.sha256(full_url.encode()).hexdigest()[:24]
            item = Opportunity(
                source_id=self.source_id,
                external_id=external_id,
                asset_class="federal_license_notice",
                title=text[:300],
                jurisdiction="United States",
                custodian="Federal Laboratory Consortium",
                source_url=full_url,
                legal_model="open_data_intelligence",
                published_at=published,
                compliance_status="public_intelligence_only",
                raw={"listing_text": context},
            )
            item.score = score_opportunity(item)
            yield item
