from __future__ import annotations

import hashlib
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from fia.models import Opportunity
from fia.scoring import score_opportunity
from fia.sources.base import SourceAdapter

DEFAULT_URL = "https://patentsgazette.uspto.gov/week02/OG/TOC.htm"


class USPTOOfficialGazette(SourceAdapter):
    source_id = "uspto_official_gazette"

    def __init__(self, client: httpx.Client, url: str = DEFAULT_URL):
        self.client = client
        self.url = url

    def fetch(self):
        response = self.client.get(self.url, follow_redirects=True)
        response.raise_for_status()
        yield from self.parse(response.text, self.url)

    def parse(self, html: str, source_url: str):
        text = BeautifulSoup(html, "html.parser").get_text("\n")
        issue_date = None
        m = re.search(r"([A-Z][a-z]+ \d{1,2}, 20\d{2})\s*\|\s*US PATENT", text)
        if m:
            issue_date = datetime.strptime(m.group(1), "%B %d, %Y").date()

        sale_marker = "Patents and Patent Applications Available for License or Sale"
        if sale_marker in text:
            section = text.rsplit(sale_marker, 1)[1]
            section = section.split("Top of Notices", 1)[0]
            blocks = re.split(r"\n\s*(?=(?:RE\.\s*)?\d[\d,]{5,}\s+)" , section)
            for block in blocks:
                first = re.search(r"((?:RE\.\s*)?\d[\d,]{5,})\s+(.+)", block.strip())
                if not first:
                    continue
                patent_no = re.sub(r"\s+", "", first.group(1))
                title = first.group(2).strip().split("\n")[0][:250]
                raw = block.strip()
                item = Opportunity(
                    source_id=self.source_id,
                    external_id=f"sale:{patent_no}",
                    asset_class="patent_license_offer",
                    title=f"Patent available for license/sale: {patent_no} — {title}",
                    jurisdiction="United States",
                    custodian="USPTO Official Gazette",
                    source_url=source_url,
                    legal_model="open_data_intelligence",
                    published_at=issue_date,
                    compliance_status="public_intelligence_only",
                    raw={"patent_number": patent_no, "text": raw},
                )
                item.score = score_opportunity(item)
                yield item

        exp_marker = "Notice of Expiration of Patents Due to Failure to Pay Maintenance Fee"
        if exp_marker in text:
            section = text.rsplit(exp_marker, 1)[1]
            section = section.split("Patents Reinstated Due", 1)[0]
            seen: set[str] = set()
            for patent_no in re.findall(r"\b(\d{1,2},\d{3},\d{3})\b", section):
                if patent_no in seen:
                    continue
                seen.add(patent_no)
                external_id = "expired:" + hashlib.sha1(patent_no.encode()).hexdigest()[:16]
                item = Opportunity(
                    source_id=self.source_id,
                    external_id=external_id,
                    asset_class="patent_expiration",
                    title=f"Patent expiration signal: {patent_no}",
                    jurisdiction="United States",
                    custodian="USPTO Official Gazette",
                    source_url=source_url,
                    legal_model="open_data_intelligence",
                    published_at=issue_date,
                    compliance_status="public_intelligence_only",
                    notes="Verify current patent status, reinstatement, continuations and related rights before use.",
                    raw={"patent_number": patent_no},
                )
                item.score = score_opportunity(item)
                yield item
