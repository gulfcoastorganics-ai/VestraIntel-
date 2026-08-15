from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit
import json
import re

import httpx
from bs4 import BeautifulSoup

from .config import load_settings
from .db import Database


PORTAL_TECHNOLOGIES: tuple[dict[str, Any], ...] = (
    {
        "id": "ckan",
        "name": "CKAN Action API",
        "access": "usually public read-only metadata",
        "capabilities": ["dataset_search", "resource_search", "recent_changes", "bulk_resources"],
    },
    {
        "id": "socrata",
        "name": "Socrata / SODA",
        "access": "public catalogs; current SODA3 data queries may require app token or user auth",
        "capabilities": ["catalog_discovery", "dataset_api", "exports", "soql"],
    },
    {
        "id": "arcgis",
        "name": "ArcGIS Hub / Portal",
        "access": "public items searchable without account when shared publicly",
        "capabilities": ["catalog_search", "item_search", "feature_services", "downloads"],
    },
    {
        "id": "dcat",
        "name": "W3C DCAT metadata",
        "access": "depends on publisher",
        "capabilities": ["catalog_metadata", "dataset_metadata", "distribution_links", "data_services"],
    },
    {
        "id": "sparql",
        "name": "SPARQL read-only endpoint",
        "access": "depends on endpoint",
        "capabilities": ["rdf_query", "federated_metadata", "structured_results"],
    },
    {
        "id": "rss_atom",
        "name": "RSS / Atom change feed",
        "access": "usually public read-only",
        "capabilities": ["change_monitoring", "entry_links", "timestamps"],
    },
    {
        "id": "bulk_download",
        "name": "Generic bulk-data portal",
        "access": "depends on publisher",
        "capabilities": ["bulk_files", "scheduled_refresh", "offline_ingestion"],
    },
)


MACHINE_EXTENSIONS = {"csv", "tsv", "json", "jsonl", "xml", "zip", "xlsx", "xls", "parquet", "ttl", "rdf", "nt", "nq"}
FEED_TYPES = {"application/rss+xml", "application/atom+xml"}
RDF_TYPES = {
    "text/turtle",
    "application/rdf+xml",
    "application/ld+json",
    "application/n-triples",
    "application/n-quads",
}


@dataclass(frozen=True)
class PortalCandidate:
    canonical_url: str
    host: str
    portal_type: str
    confidence: float
    connector_priority_score: float
    access_level: str
    capabilities: tuple[str, ...]
    evidence: tuple[str, ...]
    connector_spec: dict[str, Any]
    source_candidate_ids: tuple[int, ...] = ()
    asset_signal_score: float = 0.0

    def as_record(self) -> dict[str, Any]:
        return {
            "canonical_url": self.canonical_url,
            "host": self.host,
            "portal_type": self.portal_type,
            "confidence": self.confidence,
            "connector_priority_score": self.connector_priority_score,
            "access_level": self.access_level,
            "capabilities_json": json.dumps(self.capabilities, sort_keys=True),
            "evidence_json": json.dumps(self.evidence, sort_keys=True),
            "connector_spec_json": json.dumps(self.connector_spec, sort_keys=True, default=str),
            "source_candidate_ids_json": json.dumps(self.source_candidate_ids),
            "asset_signal_score": self.asset_signal_score,
        }


def _origin(url: str) -> str:
    parts = urlsplit(url.strip())
    if not parts.scheme:
        parts = urlsplit("https://" + url.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError(f"not an HTTP(S) URL: {url}")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), "", "", ""))


def _same_host(base: str, href: str) -> bool:
    try:
        return urlsplit(base).netloc.lower() == urlsplit(href).netloc.lower()
    except Exception:
        return False


def _bounded_links(base_url: str, html: str) -> list[tuple[str, str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[tuple[str, str, str]] = []
    for tag in soup.find_all(["a", "link"]):
        href = tag.get("href")
        if not href:
            continue
        absolute = urljoin(base_url, str(href))
        rel = " ".join(tag.get("rel") or []) if isinstance(tag.get("rel"), list) else str(tag.get("rel") or "")
        typ = str(tag.get("type") or "").lower()
        out.append((absolute, rel.lower(), typ))
        if len(out) >= 500:
            break
    return out


def _connector_spec(portal_type: str, canonical_url: str, *, discovered: dict[str, Any]) -> dict[str, Any]:
    origin = _origin(canonical_url)
    if portal_type == "ckan":
        return {
            "adapter": "ckan",
            "base_url": origin,
            "search_endpoint": f"{origin}/api/3/action/package_search",
            "recent_changes_endpoint": f"{origin}/api/3/action/recently_changed_packages_activity_list",
            "mode": "read_only_metadata",
            "requires_analyst_approval": True,
        }
    if portal_type == "socrata":
        return {
            "adapter": "socrata",
            "base_url": origin,
            "catalog_discovery": True,
            "dataset_api_pattern": f"{origin}/api/v3/views/{{dataset_id}}/query.json",
            "mode": "read_only_metadata_and_approved_data",
            "credential_note": "SODA3 data queries may require an app token or authenticated user",
            "requires_analyst_approval": True,
        }
    if portal_type == "arcgis":
        return {
            "adapter": "arcgis",
            "base_url": origin,
            "portal_search_endpoint": f"{origin}/sharing/rest/search",
            "hub_search_endpoint": f"{origin}/api/search/v1",
            "mode": "public_read_only_search",
            "requires_analyst_approval": True,
        }
    if portal_type == "dcat":
        return {
            "adapter": "dcat",
            "catalog_urls": discovered.get("dcat_urls", [canonical_url]),
            "mode": "read_only_rdf_metadata",
            "requires_analyst_approval": True,
        }
    if portal_type == "sparql":
        return {
            "adapter": "sparql",
            "endpoint": discovered.get("sparql_endpoint", canonical_url),
            "mode": "read_only_select_ask_only",
            "update_operations_allowed": False,
            "requires_analyst_approval": True,
        }
    if portal_type == "rss_atom":
        return {
            "adapter": "feed_monitor",
            "feed_urls": discovered.get("feed_urls", [canonical_url]),
            "mode": "read_only_change_monitor",
            "requires_analyst_approval": True,
        }
    return {
        "adapter": "bulk_download",
        "base_url": origin,
        "file_urls": discovered.get("bulk_urls", []),
        "mode": "public_file_monitor",
        "requires_analyst_approval": True,
    }


def _priority(confidence: float, capabilities: Iterable[str], asset_signal_score: float, access_level: str) -> float:
    caps = set(capabilities)
    machine_bonus = 18 if caps & {"dataset_search", "catalog_search", "rdf_query", "catalog_metadata"} else 8
    delta_bonus = 8 if caps & {"recent_changes", "change_monitoring", "scheduled_refresh"} else 0
    access_bonus = 10 if access_level.startswith("public") else 4
    asset_bonus = min(25.0, max(0.0, asset_signal_score) * 0.25)
    return round(min(100.0, confidence * 45 + machine_bonus + delta_bonus + access_bonus + asset_bonus), 2)


class PortalFingerprinter:
    """Bounded, read-only portal fingerprinting.

    The fingerprinter never logs in, posts data, follows forms, bypasses challenges, or issues SPARQL updates.
    """

    def __init__(self, client: httpx.Client):
        self.client = client

    def probe(self, seed_url: str, *, source_candidate_ids: Iterable[int] = (), asset_signal_score: float = 0.0) -> PortalCandidate | None:
        origin = _origin(seed_url)
        first = self.client.get(seed_url, follow_redirects=True)
        first.raise_for_status()
        final_url = str(first.url)
        content_type = first.headers.get("content-type", "").split(";")[0].strip().lower()
        body = first.text[:1_000_000] if "text" in content_type or "html" in content_type or content_type in {"", "application/json", "application/ld+json"} else ""
        lower = body.lower()
        links = _bounded_links(final_url, body) if body else []

        evidence: dict[str, list[str]] = {k: [] for k in ("ckan", "socrata", "arcgis", "dcat", "sparql", "rss_atom", "bulk_download")}
        discovered: dict[str, Any] = {"feed_urls": [], "dcat_urls": [], "bulk_urls": []}

        # Passive evidence from the seed response.
        if "ckan" in lower or re.search(r"/api/(?:3/)?action/", lower):
            evidence["ckan"].append("seed HTML/JSON contains CKAN Action API markers")
        if "socrata" in lower or "soda api" in lower or "soda3" in lower:
            evidence["socrata"].append("seed contains Socrata/SODA markers")
        if "arcgis" in lower or "esri" in lower:
            evidence["arcgis"].append("seed contains ArcGIS/Esri markers")
        if "dcat:" in lower or "www.w3.org/ns/dcat" in lower:
            evidence["dcat"].append("seed contains DCAT vocabulary markers")
        if content_type in RDF_TYPES:
            evidence["dcat"].append(f"seed content type is RDF-capable: {content_type}")
            discovered["dcat_urls"].append(final_url)
        if content_type in FEED_TYPES or "<rss" in lower or "<feed" in lower and "xmlns=\"http://www.w3.org/2005/atom\"" in lower:
            evidence["rss_atom"].append("seed is an RSS/Atom feed")
            discovered["feed_urls"].append(final_url)

        for href, rel, typ in links:
            href_l = href.lower()
            if typ in FEED_TYPES:
                evidence["rss_atom"].append(f"feed autodiscovery link: {href}")
                discovered["feed_urls"].append(href)
            if typ in RDF_TYPES or "dcat" in href_l or href_l.endswith((".ttl", ".rdf", ".jsonld")):
                evidence["dcat"].append(f"RDF/DCAT metadata link: {href}")
                discovered["dcat_urls"].append(href)
            if "sparql" in href_l:
                evidence["sparql"].append(f"SPARQL endpoint/link advertised: {href}")
                discovered.setdefault("sparql_candidates", []).append(href)
            ext = href_l.split("?", 1)[0].rsplit(".", 1)[-1] if "." in href_l.rsplit("/", 1)[-1] else ""
            if ext in MACHINE_EXTENSIONS:
                discovered["bulk_urls"].append(href)
        if len(set(discovered["bulk_urls"])) >= 2:
            evidence["bulk_download"].append(f"seed advertises {len(set(discovered['bulk_urls']))} machine-readable bulk files")

        # Active probes are low-impact GETs to standard read-only endpoints.
        try:
            r = self.client.get(f"{origin}/api/3/action/status_show", follow_redirects=True)
            if r.status_code == 200:
                payload = r.json()
                if isinstance(payload, dict) and payload.get("success") is True:
                    evidence["ckan"].append("CKAN status_show endpoint returned success=true")
        except Exception:
            pass

        try:
            r = self.client.get(f"{origin}/sharing/rest/search", params={"q": "*", "num": 1, "f": "json"}, follow_redirects=True)
            if r.status_code == 200:
                payload = r.json()
                if isinstance(payload, dict) and ("results" in payload or "total" in payload):
                    evidence["arcgis"].append("ArcGIS sharing/rest/search returned portal-style JSON")
        except Exception:
            pass

        try:
            r = self.client.get(f"{origin}/api/search/v1", follow_redirects=True)
            if r.status_code == 200:
                payload = r.json()
                if isinstance(payload, dict) and any(k in payload for k in ("links", "conformsTo", "collections")):
                    evidence["arcgis"].append("ArcGIS Hub/OGC search landing endpoint responded")
        except Exception:
            pass

        # Probe only endpoints explicitly advertised as SPARQL by the seed page.
        for endpoint in list(dict.fromkeys(discovered.get("sparql_candidates", [])))[:2]:
            if not _same_host(final_url, endpoint):
                continue
            try:
                r = self.client.get(
                    endpoint,
                    params={"query": "SELECT * WHERE { ?s ?p ?o } LIMIT 1"},
                    headers={"Accept": "application/sparql-results+json"},
                    follow_redirects=True,
                )
                if r.status_code == 200 and "sparql-results" in r.headers.get("content-type", ""):
                    evidence["sparql"].append(f"advertised SPARQL endpoint answered a bounded SELECT: {endpoint}")
                    discovered["sparql_endpoint"] = endpoint
                    break
                if r.status_code == 200:
                    payload = r.json()
                    if isinstance(payload, dict) and ("results" in payload or "boolean" in payload):
                        evidence["sparql"].append(f"advertised SPARQL endpoint returned result JSON: {endpoint}")
                        discovered["sparql_endpoint"] = endpoint
                        break
            except Exception:
                pass

        # Socrata is identified passively because current SODA3 data queries can require a token.
        # A Socrata catalog is still connector-worthy based on platform markers; no credential bypass is attempted.

        weights = {
            "ckan": 0.98 if any("status_show" in e for e in evidence["ckan"]) else 0.78,
            "socrata": 0.86,
            "arcgis": 0.96 if any("returned" in e or "responded" in e for e in evidence["arcgis"]) else 0.78,
            "dcat": 0.82,
            "sparql": 0.97 if any("answered" in e or "returned result" in e for e in evidence["sparql"]) else 0.72,
            "rss_atom": 0.88,
            "bulk_download": 0.72,
        }
        ranked = [(kind, weights[kind], ev) for kind, ev in evidence.items() if ev]
        if not ranked:
            return None
        ranked.sort(key=lambda x: (x[1], len(x[2])), reverse=True)
        portal_type, confidence, primary_evidence = ranked[0]

        capability_map = {item["id"]: tuple(item["capabilities"]) for item in PORTAL_TECHNOLOGIES}
        capabilities: set[str] = set(capability_map[portal_type])
        # Preserve additional detected capabilities from hybrid portals without changing the primary adapter type.
        for kind, _, _ in ranked[1:]:
            capabilities.update(capability_map[kind])
        access_level = "public_read_only" if first.status_code == 200 else "unknown"
        spec = _connector_spec(portal_type, origin, discovered=discovered)
        all_evidence = tuple(dict.fromkeys(e for kind, _, ev in ranked for e in ev))
        score = _priority(confidence, capabilities, asset_signal_score, access_level)
        return PortalCandidate(
            canonical_url=origin,
            host=urlsplit(origin).netloc,
            portal_type=portal_type,
            confidence=round(confidence, 3),
            connector_priority_score=score,
            access_level=access_level,
            capabilities=tuple(sorted(capabilities)),
            evidence=all_evidence,
            connector_spec=spec,
            source_candidate_ids=tuple(sorted(set(int(x) for x in source_candidate_ids))),
            asset_signal_score=round(float(asset_signal_score), 2),
        )


@dataclass(frozen=True)
class PortalDiscoveryConfig:
    urls: tuple[str, ...] = ()
    from_source_candidates: bool = True
    source_candidate_states: tuple[str, ...] = ("approved", "watch", "discovered")
    min_source_score: float = 45.0
    max_seeds: int = 100


@dataclass(frozen=True)
class PortalDiscoveryStats:
    run_id: int
    seeds: int
    probed: int
    saved: int
    errors: tuple[str, ...]


def _extract_candidate_urls(raw: Any, *, limit: int = 30) -> list[str]:
    out: list[str] = []

    def walk(value: Any, key_hint: str = "") -> None:
        if len(out) >= limit:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                walk(child, str(key).lower())
                if len(out) >= limit:
                    break
        elif isinstance(value, list):
            for child in value[:50]:
                walk(child, key_hint)
                if len(out) >= limit:
                    break
        elif isinstance(value, str) and value.startswith(("http://", "https://")):
            if any(token in key_hint for token in ("url", "uri", "access", "download", "endpoint", "api", "landing", "resource", "distribution")):
                out.append(value)

    walk(raw)
    return out


def _source_candidate_seeds(db: Database, config: PortalDiscoveryConfig) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    if not config.from_source_candidates:
        return grouped
    for state in config.source_candidate_states:
        for row in db.list_source_candidates(limit=max(1000, config.max_seeds * 20), min_score=config.min_source_score, state=state):
            urls = [row["landing_url"], row["metadata_url"]]
            try:
                raw = json.loads(row["raw_json"] or "{}")
            except (json.JSONDecodeError, TypeError):
                raw = {}
            urls.extend(_extract_candidate_urls(raw))
            for url in urls:
                if not url:
                    continue
                try:
                    root = _origin(str(url))
                except ValueError:
                    continue
                item = grouped.setdefault(root, {"ids": set(), "score": 0.0})
                item["ids"].add(int(row["id"]))
                item["score"] = max(float(item["score"]), float(row["overall_score"] or 0))
    return grouped


def discover_portals(
    db: Database,
    config: PortalDiscoveryConfig | None = None,
    *,
    fingerprinter_factory: Callable[[httpx.Client], PortalFingerprinter] = PortalFingerprinter,
) -> PortalDiscoveryStats:
    config = config or PortalDiscoveryConfig()
    grouped = _source_candidate_seeds(db, config)
    for url in config.urls:
        root = _origin(url)
        grouped.setdefault(root, {"ids": set(), "score": 0.0})
    seeds = sorted(grouped.items(), key=lambda kv: float(kv[1]["score"]), reverse=True)[: config.max_seeds]
    run_id = db.begin_portal_discovery_run(seeds=[s[0] for s in seeds], config=asdict(config))
    errors: list[str] = []
    candidates: list[PortalCandidate] = []
    probed = 0
    settings = load_settings()
    try:
        with httpx.Client(timeout=30, headers={"User-Agent": settings.user_agent}) as client:
            fingerprinter = fingerprinter_factory(client)
            for root, meta in seeds:
                try:
                    candidate = fingerprinter.probe(
                        root,
                        source_candidate_ids=meta["ids"],
                        asset_signal_score=float(meta["score"]),
                    )
                    probed += 1
                    if candidate is not None:
                        candidates.append(candidate)
                except Exception as exc:
                    errors.append(f"{root}: {type(exc).__name__}: {exc}")
        saved = db.upsert_portal_candidates(candidates)
        status = "completed_with_errors" if errors else "completed"
        db.finish_portal_discovery_run(run_id, status=status, probed_count=probed, saved_count=saved, errors=errors)
    except Exception as exc:
        db.finish_portal_discovery_run(run_id, status="failed", probed_count=probed, saved_count=0, errors=errors + [f"{type(exc).__name__}: {exc}"])
        raise
    return PortalDiscoveryStats(run_id=run_id, seeds=len(seeds), probed=probed, saved=saved, errors=tuple(errors))
