from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Iterable
import json
import re

import httpx

from .config import load_settings
from .db import Database


DEFAULT_DISCOVERY_QUERIES: tuple[str, ...] = (
    "unclaimed property",
    "unclaimed funds",
    "surplus funds",
    "bankruptcy unclaimed",
    "liquidation distributions",
    "dissolved companies assets",
    "bona vacantia",
    "unpaid checks",
    "dormant securities",
    "royalties unmatched",
    "patents license sale",
    "public auctions assets",
    "contract opportunities",
)


DISCOVERY_CATALOGS: tuple[dict[str, str], ...] = (
    {
        "id": "us_data_gov",
        "name": "U.S. Data.gov Catalog API v4",
        "jurisdiction": "United States",
        "access": "api_key",
        "mode": "metadata_search",
        "url": "https://resources.data.gov/catalog-api/",
    },
    {
        "id": "uk_data_gov",
        "name": "UK data.gov.uk CKAN directory",
        "jurisdiction": "United Kingdom",
        "access": "public",
        "mode": "metadata_search",
        "url": "https://guidance.data.gov.uk/get_data/api_documentation/",
    },
    {
        "id": "ca_open_government",
        "name": "Canada Open Government Portal CKAN",
        "jurisdiction": "Canada",
        "access": "public_read_only",
        "mode": "metadata_search",
        "url": "https://open.canada.ca/data/en/dataset/2d90548d-50ef-4802-91f8-c59c5cf68251",
    },
    {
        "id": "eu_data_portal",
        "name": "European Data Portal Hub Search",
        "jurisdiction": "European Union",
        "access": "public_read_only_search",
        "mode": "metadata_search",
        "url": "https://data.europa.eu/api/hub/search/",
    },
)


ASSET_TERMS: tuple[tuple[str, float], ...] = (
    ("bona vacantia", 28),
    ("unclaimed funds", 26),
    ("unclaimed property", 24),
    ("surplus funds", 24),
    ("bankruptcy unclaimed", 24),
    ("unclaimed estate", 22),
    ("unpaid check", 20),
    ("dormant securities", 20),
    ("liquidation distribution", 19),
    ("royalt", 16),
    ("dissolved compan", 16),
    ("insolvenc", 15),
    ("foreclosure", 14),
    ("tax deed", 14),
    ("patent", 10),
    ("license", 8),
    ("auction", 8),
    ("contract opportunit", 7),
    ("procurement", 6),
)

MACHINE_FORMAT_WEIGHTS: dict[str, float] = {
    "API": 24,
    "SPARQL": 24,
    "JSON": 22,
    "JSONL": 22,
    "CSV": 20,
    "TSV": 18,
    "XML": 15,
    "ZIP": 14,
    "SQLITE": 14,
    "XLSX": 10,
    "XLS": 8,
    "HTML": 3,
    "PDF": 1,
}


@dataclass(frozen=True)
class SourceCandidate:
    catalog_id: str
    external_id: str
    title: str
    description: str
    publisher: str | None
    jurisdiction: str
    landing_url: str | None
    metadata_url: str | None
    access_level: str | None
    license: str | None
    formats: tuple[str, ...]
    keywords: tuple[str, ...]
    modified_at: str | None
    update_frequency: str | None
    asset_density_score: float
    machine_readability_score: float
    access_score: float
    legal_reuse_score: float
    freshness_score: float
    novelty_score: float
    monetization_fit_score: float
    overall_score: float
    monetization_route: str
    reasons: tuple[str, ...]
    raw: dict[str, Any]

    def as_record(self) -> dict[str, Any]:
        out = asdict(self)
        out["formats_json"] = json.dumps(self.formats, sort_keys=True)
        out["keywords_json"] = json.dumps(self.keywords, sort_keys=True)
        out["reason_json"] = json.dumps(self.reasons, sort_keys=True)
        out["raw_json"] = json.dumps(self.raw, sort_keys=True, default=str)
        for key in ("formats", "keywords", "reasons", "raw"):
            out.pop(key, None)
        return out


def _text(*parts: Any) -> str:
    values: list[str] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, (list, tuple, set)):
            values.extend(str(x) for x in part if x is not None)
        elif isinstance(part, dict):
            values.extend(str(x) for x in part.values() if x is not None)
        else:
            values.append(str(part))
    return " ".join(values).lower()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    candidate = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        try:
            dt = datetime.strptime(candidate[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def infer_monetization_route(title: str, description: str, keywords: Iterable[str]) -> str:
    text = _text(title, description, list(keywords))
    if any(x in text for x in ("royalt", "isrc", "rightsholder", "musical works")):
        return "rights_reconciliation_intelligence"
    if any(x in text for x in ("bona vacantia", "dissolved company", "dissolved companies", "orphaned ip")):
        return "asset_acquisition_review"
    if any(x in text for x in ("bankruptcy", "liquidation", "insolvency", "successor")):
        return "successor_claim_review"
    if any(x in text for x in ("unclaimed", "surplus funds", "unpaid check", "escheat")):
        return "locator_fee_review"
    if any(x in text for x in ("patent", "license for sale", "licensing")):
        return "licensing_intelligence"
    if any(x in text for x in ("contract opportunit", "procurement", "tender", "award")):
        return "procurement_intelligence"
    if "auction" in text:
        return "asset_acquisition_review"
    return "intelligence_sale_review"


def score_candidate(
    *,
    title: str,
    description: str,
    keywords: Iterable[str],
    formats: Iterable[str],
    access_level: str | None,
    license_value: str | None,
    modified_at: str | None,
    popularity: int | float | None = None,
) -> tuple[dict[str, float], tuple[str, ...]]:
    text = _text(title, description, list(keywords))
    reasons: list[str] = []
    asset = 0.0
    for term, weight in ASSET_TERMS:
        if term in text:
            asset += weight
            reasons.append(f"asset term: {term}")
    asset = min(100.0, asset)

    normalized_formats = {str(fmt).strip().upper() for fmt in formats if str(fmt).strip()}
    machine = max((MACHINE_FORMAT_WEIGHTS.get(fmt, 0) for fmt in normalized_formats), default=0)
    if len(normalized_formats & {"API", "SPARQL", "JSON", "JSONL", "CSV", "TSV"}) >= 2:
        machine += 8
    machine = min(100.0, machine * 3.0)
    if normalized_formats:
        reasons.append("machine formats: " + ", ".join(sorted(normalized_formats)[:6]))

    access_text = (access_level or "").lower()
    if "non-public" in access_text or "restricted" in access_text:
        access = 10.0
        reasons.append("restricted access")
    elif "public" in access_text or not access_text:
        access = 90.0
        reasons.append("public/read-only metadata")
    else:
        access = 60.0

    license_text = (license_value or "").lower()
    if any(x in license_text for x in ("publicdomain", "cc0", "open government", "ogl", "creativecommons")):
        reuse = 95.0
        reasons.append("open/reuse-friendly license metadata")
    elif license_text:
        reuse = 65.0
        reasons.append("license published; review required")
    else:
        reuse = 45.0
        reasons.append("license not explicit")

    now = datetime.now(timezone.utc)
    modified = _parse_datetime(modified_at)
    if modified is None:
        freshness = 35.0
    else:
        days = max(0, (now - modified).days)
        if days <= 30:
            freshness = 100.0
        elif days <= 90:
            freshness = 85.0
        elif days <= 365:
            freshness = 65.0
        elif days <= 1095:
            freshness = 45.0
        else:
            freshness = 25.0
        reasons.append(f"modified {days} days ago")

    if popularity is None:
        novelty = 55.0
    else:
        try:
            p = float(popularity)
        except (TypeError, ValueError):
            p = 0.0
        novelty = 80.0 if p <= 2 else 65.0 if p <= 10 else 45.0 if p <= 50 else 25.0
        reasons.append(f"catalog popularity signal: {p:g}")

    route = infer_monetization_route(title, description, keywords)
    route_fit = {
        "locator_fee_review": 90.0,
        "asset_acquisition_review": 88.0,
        "successor_claim_review": 82.0,
        "rights_reconciliation_intelligence": 78.0,
        "licensing_intelligence": 72.0,
        "procurement_intelligence": 62.0,
        "intelligence_sale_review": 45.0,
    }[route]

    overall = (
        asset * 0.31
        + machine * 0.20
        + access * 0.12
        + reuse * 0.10
        + freshness * 0.10
        + novelty * 0.07
        + route_fit * 0.10
    )
    if asset < 8:
        overall *= 0.60
    return {
        "asset_density_score": round(asset, 2),
        "machine_readability_score": round(machine, 2),
        "access_score": round(access, 2),
        "legal_reuse_score": round(reuse, 2),
        "freshness_score": round(freshness, 2),
        "novelty_score": round(novelty, 2),
        "monetization_fit_score": round(route_fit, 2),
        "overall_score": round(min(100.0, overall), 2),
    }, tuple(reasons)


def _formats_from_distributions(distributions: Any) -> tuple[str, ...]:
    formats: set[str] = set()
    if not isinstance(distributions, list):
        return ()
    for item in distributions:
        if isinstance(item, dict):
            value = item.get("format") or item.get("mediaType") or item.get("media_type")
            if value:
                token = str(value).split("/")[-1].split(";")[0].upper()
                token = {"JAVASCRIPT": "JSON", "VND.MS-EXCEL": "XLS"}.get(token, token)
                formats.add(token)
            title = str(item.get("title") or "")
            match = re.search(r"\.([A-Za-z0-9]{2,6})(?:$|\?)", title)
            if match:
                formats.add(match.group(1).upper())
    return tuple(sorted(formats))


def _candidate(
    *, catalog_id: str, jurisdiction: str, external_id: str, title: str, description: str = "",
    publisher: str | None = None, landing_url: str | None = None, metadata_url: str | None = None,
    access_level: str | None = "public", license_value: str | None = None,
    formats: Iterable[str] = (), keywords: Iterable[str] = (), modified_at: str | None = None,
    update_frequency: str | None = None, popularity: int | float | None = None,
    raw: dict[str, Any] | None = None,
) -> SourceCandidate:
    fmt = tuple(sorted({str(x).upper() for x in formats if x}))
    keys = tuple(sorted({str(x).strip() for x in keywords if str(x).strip()}))
    scores, reasons = score_candidate(
        title=title, description=description, keywords=keys, formats=fmt,
        access_level=access_level, license_value=license_value, modified_at=modified_at,
        popularity=popularity,
    )
    route = infer_monetization_route(title, description, keys)
    return SourceCandidate(
        catalog_id=catalog_id, external_id=external_id, title=title, description=description,
        publisher=publisher, jurisdiction=jurisdiction, landing_url=landing_url, metadata_url=metadata_url,
        access_level=access_level, license=license_value, formats=fmt, keywords=keys,
        modified_at=modified_at, update_frequency=update_frequency,
        monetization_route=route, reasons=reasons, raw=raw or {}, **scores,
    )


class DataGovMiner:
    catalog_id = "us_data_gov"
    base_url = "https://api.gsa.gov/technology/datagov/v4/search"

    def __init__(self, client: httpx.Client, api_key: str | None = None):
        self.client = client
        self.api_key = api_key

    def search(self, query: str, limit: int = 25) -> list[SourceCandidate]:
        if not self.api_key:
            raise RuntimeError("DATA_GOV_API_KEY is required for automated Data.gov v4 mining")
        response = self.client.get(
            self.base_url,
            params={"q": query, "per_page": max(1, min(limit, 100)), "sort": "last_harvested_date"},
            headers={"X-Api-Key": self.api_key},
        )
        response.raise_for_status()
        data = response.json()
        out: list[SourceCandidate] = []
        for item in data.get("results", []):
            dcat = item.get("dcat") or {}
            distributions = dcat.get("distribution") or []
            formats = list(_formats_from_distributions(distributions))
            for title in item.get("distribution_titles") or []:
                m = re.search(r"\b(API|CSV|JSONL?|XML|XLSX?|ZIP|SPARQL)\b", str(title), re.I)
                if m:
                    formats.append(m.group(1).upper())
            external = str(item.get("identifier") or item.get("slug") or item.get("harvest_record") or item.get("title"))
            org = item.get("organization") or {}
            out.append(_candidate(
                catalog_id=self.catalog_id, jurisdiction="United States", external_id=external,
                title=str(item.get("title") or "Untitled dataset"),
                description=str(item.get("description") or dcat.get("description") or ""),
                publisher=str(item.get("publisher") or org.get("name") or "") or None,
                landing_url=dcat.get("landingPage") or item.get("harvest_record_raw"),
                metadata_url=item.get("harvest_record"), access_level=dcat.get("accessLevel") or "public",
                license_value=dcat.get("license"), formats=formats,
                keywords=item.get("keyword") or dcat.get("keyword") or (),
                modified_at=dcat.get("modified") or item.get("last_harvested_date"),
                update_frequency=dcat.get("accrualPeriodicity"), popularity=item.get("popularity"), raw=item,
            ))
        return out


class CKANMiner:
    def __init__(self, client: httpx.Client, *, catalog_id: str, jurisdiction: str, base_url: str):
        self.client = client
        self.catalog_id = catalog_id
        self.jurisdiction = jurisdiction
        self.base_url = base_url.rstrip("/")

    def search(self, query: str, limit: int = 25) -> list[SourceCandidate]:
        response = self.client.get(
            f"{self.base_url}/api/action/package_search",
            params={"q": query, "rows": max(1, min(limit, 1000))},
        )
        response.raise_for_status()
        payload = response.json()
        result = payload.get("result") or {}
        out: list[SourceCandidate] = []
        for item in result.get("results", []):
            resources = item.get("resources") or []
            formats = [r.get("format") for r in resources if isinstance(r, dict) and r.get("format")]
            landing = item.get("url") or item.get("landing_page") or item.get("notes_url")
            if not landing and item.get("name"):
                landing = f"{self.base_url}/dataset/{item['name']}"
            out.append(_candidate(
                catalog_id=self.catalog_id, jurisdiction=self.jurisdiction,
                external_id=str(item.get("id") or item.get("name") or item.get("title")),
                title=str(item.get("title") or item.get("name") or "Untitled dataset"),
                description=str(item.get("notes") or ""),
                publisher=((item.get("organization") or {}).get("title") if isinstance(item.get("organization"), dict) else None),
                landing_url=landing, metadata_url=(f"{self.base_url}/api/action/package_show?id={item.get('id')}" if item.get("id") else None),
                access_level="public", license_value=item.get("license_url") or item.get("license_title"),
                formats=formats, keywords=[t.get("name") for t in item.get("tags") or [] if isinstance(t, dict)],
                modified_at=item.get("metadata_modified") or item.get("metadata_created"),
                update_frequency=item.get("frequency") or item.get("update_frequency"), raw=item,
            ))
        return out


class EUDataPortalMiner:
    catalog_id = "eu_data_portal"
    base_url = "https://data.europa.eu/api/hub/search/search"

    def __init__(self, client: httpx.Client):
        self.client = client

    def search(self, query: str, limit: int = 25) -> list[SourceCandidate]:
        response = self.client.get(
            self.base_url,
            params=[("q", query), ("filters", "dataset"), ("limit", str(max(1, min(limit, 1000)))), ("showScore", "true")],
        )
        response.raise_for_status()
        payload = response.json()
        raw_results = payload.get("result") or payload.get("results") or payload.get("items") or []
        if isinstance(raw_results, dict):
            raw_results = raw_results.get("results") or raw_results.get("items") or []
        out: list[SourceCandidate] = []
        for item in raw_results if isinstance(raw_results, list) else []:
            if not isinstance(item, dict):
                continue
            title_value = item.get("title")
            if isinstance(title_value, dict):
                title = str(title_value.get("en") or next(iter(title_value.values()), "Untitled dataset"))
            else:
                title = str(title_value or "Untitled dataset")
            desc_value = item.get("description")
            if isinstance(desc_value, dict):
                description = str(desc_value.get("en") or next(iter(desc_value.values()), ""))
            else:
                description = str(desc_value or "")
            distributions = item.get("distributions") or item.get("distribution") or []
            formats = _formats_from_distributions(distributions)
            publisher = item.get("publisher")
            if isinstance(publisher, dict):
                publisher = publisher.get("name") or publisher.get("label")
            out.append(_candidate(
                catalog_id=self.catalog_id, jurisdiction="European Union",
                external_id=str(item.get("id") or item.get("identifier") or item.get("uri") or title),
                title=title, description=description, publisher=str(publisher) if publisher else None,
                landing_url=item.get("landingPage") or item.get("landing_page") or item.get("uri"),
                metadata_url=item.get("uri") or item.get("id"), access_level="public",
                license_value=item.get("license") if isinstance(item.get("license"), str) else None,
                formats=formats, keywords=item.get("keywords") or item.get("keyword") or (),
                modified_at=item.get("modified") or item.get("issued"), update_frequency=item.get("accrualPeriodicity"), raw=item,
            ))
        return out


@dataclass(frozen=True)
class SourceMiningConfig:
    catalog_ids: tuple[str, ...] = ()
    queries: tuple[str, ...] = DEFAULT_DISCOVERY_QUERIES
    results_per_query: int = 25
    min_score: float = 35.0
    max_candidates: int = 1000


@dataclass(frozen=True)
class SourceMiningStats:
    run_id: int
    catalogs: tuple[str, ...]
    queries: int
    seen: int
    saved: int
    above_threshold: int
    errors: tuple[str, ...]


def _catalog_miners(client: httpx.Client) -> dict[str, Any]:
    settings = load_settings()
    return {
        "us_data_gov": DataGovMiner(client, api_key=settings.data_gov_api_key),
        "uk_data_gov": CKANMiner(client, catalog_id="uk_data_gov", jurisdiction="United Kingdom", base_url="https://data.gov.uk"),
        "ca_open_government": CKANMiner(client, catalog_id="ca_open_government", jurisdiction="Canada", base_url="https://open.canada.ca/data"),
        "eu_data_portal": EUDataPortalMiner(client),
    }


def mine_source_catalogs(
    db: Database,
    config: SourceMiningConfig | None = None,
    *,
    miner_factory: Callable[[httpx.Client], dict[str, Any]] = _catalog_miners,
) -> SourceMiningStats:
    config = config or SourceMiningConfig()
    catalogs = tuple(config.catalog_ids or tuple(x["id"] for x in DISCOVERY_CATALOGS))
    run_id = db.begin_source_mining_run(catalogs=catalogs, queries=config.queries, config=asdict(config))
    seen = saved = above = 0
    errors: list[str] = []
    settings = load_settings()
    try:
        with httpx.Client(timeout=45, headers={"User-Agent": settings.user_agent}) as client:
            miners = miner_factory(client)
            dedup: dict[tuple[str, str], SourceCandidate] = {}
            for catalog_id in catalogs:
                miner = miners.get(catalog_id)
                if miner is None:
                    errors.append(f"{catalog_id}: no miner configured")
                    continue
                for query in config.queries:
                    try:
                        items = miner.search(query, limit=config.results_per_query)
                    except Exception as exc:  # source failures are isolated and audited
                        errors.append(f"{catalog_id}/{query}: {type(exc).__name__}: {exc}")
                        continue
                    seen += len(items)
                    for candidate in items:
                        key = (candidate.catalog_id, candidate.external_id)
                        prior = dedup.get(key)
                        if prior is None or candidate.overall_score > prior.overall_score:
                            dedup[key] = candidate
            ranked = sorted(dedup.values(), key=lambda x: x.overall_score, reverse=True)
            selected = ranked[: config.max_candidates]
            saved = db.upsert_source_candidates(selected)
            above = sum(1 for c in selected if c.overall_score >= config.min_score)
        db.finish_source_mining_run(run_id, status="completed_with_errors" if errors else "completed", seen_count=seen, saved_count=saved, above_threshold_count=above, errors=errors)
    except Exception as exc:
        db.finish_source_mining_run(run_id, status="failed", seen_count=seen, saved_count=saved, above_threshold_count=above, errors=errors + [f"{type(exc).__name__}: {exc}"])
        raise
    return SourceMiningStats(run_id=run_id, catalogs=catalogs, queries=len(config.queries), seen=seen, saved=saved, above_threshold=above, errors=tuple(errors))
