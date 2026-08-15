from __future__ import annotations

import csv
import json
from pathlib import Path

import httpx
import typer
import uvicorn

from .config import load_settings
from .db import Database
from .registry import SOURCES
from .sources.california_unclaimed import CaliforniaUnclaimedProperty
from .sources.companies_house import CompaniesHouseClient, normalize_dissolved_items
from .sources.flc_notices import FLCLicenseNotices
from .sources.new_york_unclaimed import NewYorkOwnerFile
from .sources.uk_unclaimed_estates import UKUnclaimedEstates
from .sources.uspto_og import USPTOOfficialGazette
from .sources.music_rights import SoundExchangeStatusFile, MLCDataFile
from .sources.treasury_unpaid import TreasuryCanceledCheckFile
from .sources.sam_contracts import SAMContractOpportunitiesFile
from .sources.court_funds import BankruptcyUnclaimedFundsFile, OfficialSurplusFundsFile
from .entity_resolution import rebuild_entity_graph
from .commercial import rebuild_commercial_assessments
from .anomalies import RULE_CATALOG, detect_anomalies
from .research import TASK_CATALOG, execute_task, plan_research
from .feedback import assimilate_research_results
from .case_resolution import rebuild_case_resolutions
from .economics import rebuild_case_economics
from .scheduler import SchedulerConfig, run_scheduler
from .source_orchestration import SOURCE_POLICIES, SourceOrchestratorConfig, ensure_source_states, run_source_orchestrator
from .portfolio import run_portfolio
from .monetization import ROUTE_CATALOG, rebuild_monetization_routes
from .source_discovery import (
    DISCOVERY_CATALOGS, DEFAULT_DISCOVERY_QUERIES, SourceMiningConfig, mine_source_catalogs,
)
from .portal_discovery import (
    PORTAL_TECHNOLOGIES, PortalDiscoveryConfig, discover_portals,
)
from .gpt_actions import build_action_schema

app = typer.Typer(help="Forgotten Asset Intelligence CLI")
ingest_app = typer.Typer(help="Ingest approved public sources")
company_app = typer.Typer(help="Read-only corporate enrichment")
app.add_typer(ingest_app, name="ingest")
app.add_typer(company_app, name="company")


def _db() -> Database:
    return Database(load_settings().db_path)


def _client() -> httpx.Client:
    settings = load_settings()
    return httpx.Client(timeout=45, headers={"User-Agent": settings.user_agent})


def _ingest(source_id: str, items) -> int:
    db = _db()
    run_id = db.begin_run(source_id)
    try:
        stats = db.upsert_with_stats(items)
        db.finish_run(
            run_id,
            record_count=stats.total,
            new_count=stats.new,
            changed_count=stats.changed,
            unchanged_count=stats.unchanged,
        )
        return stats.total
    except Exception as exc:
        db.finish_run(run_id, error=f"{type(exc).__name__}: {exc}")
        raise



@app.command("source-catalogs")
def source_catalogs():
    """List official metadata catalogs used to discover new candidate data sources."""
    for item in DISCOVERY_CATALOGS:
        typer.echo(f"{item['id']:<24} {item['access']:<24} {item['jurisdiction']:<18} {item['name']}")


@app.command("source-mine")
def source_mine(
    catalog: list[str] | None = typer.Option(None, "--catalog", help="Catalog ID; repeat to search multiple"),
    query: list[str] | None = typer.Option(None, "--query", help="Discovery query; repeat to add multiple"),
    results_per_query: int = typer.Option(25, min=1, max=1000),
    min_score: float = typer.Option(35.0, min=0, max=100),
    max_candidates: int = typer.Option(1000, min=1, max=10000),
):
    """Search official open-data catalogs for new candidate datasets; metadata only."""
    known = {x['id'] for x in DISCOVERY_CATALOGS}
    chosen = tuple(catalog or ())
    unknown = sorted(set(chosen) - known)
    if unknown:
        raise typer.BadParameter(f"Unknown catalog(s): {', '.join(unknown)}")
    config = SourceMiningConfig(
        catalog_ids=chosen, queries=tuple(query or DEFAULT_DISCOVERY_QUERIES),
        results_per_query=results_per_query, min_score=min_score, max_candidates=max_candidates,
    )
    stats = mine_source_catalogs(_db(), config)
    typer.echo(json.dumps({
        'run_id': stats.run_id, 'catalogs': stats.catalogs, 'queries': stats.queries,
        'seen': stats.seen, 'saved': stats.saved, 'above_threshold': stats.above_threshold,
        'errors': stats.errors,
    }, indent=2))


@app.command("source-candidates")
def source_candidates(
    limit: int = 50, min_score: float = typer.Option(0, min=0, max=100),
    catalog_id: str | None = None, route: str | None = None,
    state: str = typer.Option("discovered", help="discovered, approved, rejected, watch, archived, or all"),
):
    """Rank candidate datasets discovered in official metadata catalogs."""
    state_filter = None if state == 'all' else state
    rows = _db().list_source_candidates(
        limit=limit, min_score=min_score, catalog_id=catalog_id, route=route, state=state_filter
    )
    if not rows:
        typer.echo("No source candidates match the filters; run `fia source-mine`")
        return
    for row in rows:
        typer.echo(
            f"#{row['id']:<5} {row['overall_score']:>5.1f} {row['catalog_id']:<20} "
            f"{row['monetization_route']:<34} {row['title'][:90]}"
        )


@app.command("source-candidate")
def source_candidate(candidate_id: int):
    """Show scoring, provenance, access metadata, and raw catalog metadata for one candidate source."""
    result = _db().source_candidate(candidate_id)
    if result is None:
        raise typer.BadParameter(f"Unknown source candidate id: {candidate_id}")
    typer.echo(json.dumps(result, indent=2))


@app.command("source-candidate-state")
def source_candidate_state(candidate_id: int, state: str):
    """Approve, reject, watch, archive, or return a discovered source candidate."""
    try:
        changed = _db().set_source_candidate_state(candidate_id, state)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if not changed:
        raise typer.BadParameter(f"Unknown source candidate id: {candidate_id}")
    typer.echo(f"candidate={candidate_id} state={state}")


@app.command("source-mining-runs")
def source_mining_runs(limit: int = 50):
    """Show auditable metadata-catalog mining runs."""
    for row in _db().list_source_mining_runs(limit=limit):
        typer.echo(
            f"#{row['id']:<4} {row['status']:<22} seen={row['seen_count']:<5} "
            f"saved={row['saved_count']:<5} threshold={row['above_threshold_count']:<5} {row['started_at']}"
        )


@app.command("portal-technologies")
def portal_technologies():
    """List portal/API technologies FIA can fingerprint and propose connectors for."""
    for item in PORTAL_TECHNOLOGIES:
        typer.echo(f"{item['id']:<16} {item['access']:<55} {item['name']}")


@app.command("portal-discover")
def portal_discover(
    url: list[str] | None = typer.Option(None, "--url", help="Portal or dataset URL to fingerprint; repeatable"),
    from_source_candidates: bool = typer.Option(True, "--from-source-candidates/--no-source-candidates"),
    min_source_score: float = typer.Option(45.0, min=0, max=100),
    max_seeds: int = typer.Option(100, min=1, max=1000),
):
    """Fingerprint candidate portal technologies with bounded, read-only probes."""
    config = PortalDiscoveryConfig(
        urls=tuple(url or ()),
        from_source_candidates=from_source_candidates,
        min_source_score=min_source_score,
        max_seeds=max_seeds,
    )
    if not config.urls and not config.from_source_candidates:
        raise typer.BadParameter("provide --url or enable --from-source-candidates")
    stats = discover_portals(_db(), config)
    typer.echo(json.dumps({
        "run_id": stats.run_id, "seeds": stats.seeds, "probed": stats.probed,
        "saved": stats.saved, "errors": stats.errors,
    }, indent=2))


@app.command("portal-candidates")
def portal_candidates(
    limit: int = 50, min_score: float = typer.Option(0, min=0, max=100),
    portal_type: str | None = None,
    state: str = typer.Option("discovered", help="discovered, approved, rejected, watch, archived, or all"),
):
    """Rank discovered portal technologies and connector proposals."""
    state_filter = None if state == "all" else state
    rows = _db().list_portal_candidates(limit=limit, min_score=min_score, portal_type=portal_type, state=state_filter)
    if not rows:
        typer.echo("No portal candidates match the filters; run `fia portal-discover`")
        return
    for row in rows:
        typer.echo(
            f"#{row['id']:<5} {row['connector_priority_score']:>5.1f} {row['portal_type']:<14} "
            f"conf={row['confidence']:.2f} asset={row['asset_signal_score']:.1f} {row['canonical_url']}"
        )


@app.command("portal-candidate")
def portal_candidate(candidate_id: int):
    """Show evidence and the proposed connector spec for one discovered portal."""
    result = _db().portal_candidate(candidate_id)
    if result is None:
        raise typer.BadParameter(f"Unknown portal candidate id: {candidate_id}")
    typer.echo(json.dumps(result, indent=2))


@app.command("portal-candidate-state")
def portal_candidate_state(candidate_id: int, state: str):
    """Approve, watch, reject, archive, or reset a portal connector proposal."""
    try:
        changed = _db().set_portal_candidate_state(candidate_id, state)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if not changed:
        raise typer.BadParameter(f"Unknown portal candidate id: {candidate_id}")
    typer.echo(f"portal_candidate={candidate_id} state={state}")


@app.command("portal-discovery-runs")
def portal_discovery_runs(limit: int = 50):
    """Show auditable portal-fingerprinting runs."""
    for row in _db().list_portal_discovery_runs(limit=limit):
        typer.echo(
            f"#{row['id']:<4} {row['status']:<22} probed={row['probed_count']:<5} "
            f"saved={row['saved_count']:<5} {row['started_at']}"
        )


@app.command("source-status")
def source_status(limit: int = 100):
    """Show freshness, cursors, failures, and next-due times for orchestrated sources."""
    database = _db()
    ensure_source_states(database)
    for row in database.list_source_sync_states(limit=limit):
        typer.echo(
            f"{row['source_id']:<28} {row['last_status']:<12} failures={row['consecutive_failures']:<2} "
            f"next={row['next_due_at'] or '-'} cursor={row['cursor'] or '-'}"
        )


@app.command("source-events")
def source_events(limit: int = 50, source_id: str | None = None):
    """Show auditable source-refresh attempts."""
    for row in _db().list_source_sync_events(limit=limit, source_id=source_id):
        typer.echo(
            f"#{row['id']:<4} {row['source_id']:<28} {row['status']:<12} "
            f"records={row['record_count']:<6} new={row['new_count']:<6} changed={row['changed_count']:<6}"
        )


@app.command("source-refresh")
def source_refresh(
    execute: bool = typer.Option(False, "--execute", help="Actually call due public/read-only sources; default is dry-run"),
    source: list[str] | None = typer.Option(None, "--source", help="Limit to one or more source IDs"),
    max_sources: int = typer.Option(10, min=0, max=50),
    california_bucket: str = typer.Option("500_plus"),
    stream_events: int = typer.Option(100, min=1, max=5000),
):
    """Refresh due source feeds with freshness tracking and exponential retry/backoff."""
    stats = run_source_orchestrator(
        _db(),
        SourceOrchestratorConfig(
            dry_run=not execute, source_ids=tuple(source or ()), max_sources=max_sources,
            california_bucket=california_bucket, companies_house_stream_max_events=stream_events,
        ),
    )
    typer.echo(json.dumps({
        "status": stats.status, "due_sources": stats.due_sources, "completed_sources": stats.completed_sources,
        "blocked_sources": stats.blocked_sources, "failed_sources": stats.failed_sources,
        "records": stats.total_records, "new": stats.new_records, "changed": stats.changed_records,
    }, indent=2))


@app.command("portfolio-run")
def portfolio_run(
    execute_sources: bool = typer.Option(False, "--execute-sources"),
    execute_research: bool = typer.Option(False, "--execute-research"),
    max_source_refreshes: int = typer.Option(10, min=0, max=50),
    max_research_steps: int = typer.Option(20, min=0, max=500),
    max_planning_cost: float = typer.Option(250.0, min=0),
):
    """Refresh due feeds, then spend permitted research effort on the best case across the portfolio."""
    result = run_portfolio(
        _db(),
        source_config=SourceOrchestratorConfig(dry_run=not execute_sources, max_sources=max_source_refreshes),
        research_config=SchedulerConfig(
            dry_run=not execute_research, max_steps=max_research_steps, max_planning_cost=max_planning_cost
        ),
    )
    typer.echo(json.dumps({
        "sources": {
            "status": result.sources.status, "due": result.sources.due_sources,
            "completed": result.sources.completed_sources, "blocked": result.sources.blocked_sources,
            "failed": result.sources.failed_sources, "new": result.sources.new_records,
            "changed": result.sources.changed_records,
        },
        "research": {
            "run_id": result.research.run_id, "status": result.research.status,
            "steps": result.research.steps_executed, "planning_cost": result.research.planning_cost_spent,
            "stop_reason": result.research.stop_reason,
        },
    }, indent=2))


@app.command("gpt-schema")
def gpt_schema(
    base_url: str = typer.Option(..., help="Public HTTPS Vestra Intel origin"),
    output: Path | None = typer.Option(None, help="Optional JSON output path"),
):
    """Generate the GPT Actions OpenAPI schema for a deployed Vestra Intel origin."""
    schema = build_action_schema(base_url)
    rendered = json.dumps(schema, indent=2)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
        typer.echo(str(output))
    else:
        typer.echo(rendered)

@app.command("init-db")
def init_db():
    _db().init()
    typer.echo(f"Initialized {_db().path}")


@app.command("sources")
def sources():
    for source in SOURCES:
        typer.echo(f"{source['id']:<28} {source['access']:<20} {source['action_gate']}")


@ingest_app.command("uk-estates")
def ingest_uk_estates():
    with _client() as client:
        count = _ingest("uk_unclaimed_estates", UKUnclaimedEstates(client).fetch())
    typer.echo(f"Upserted {count} UK unclaimed-estate records")


@ingest_app.command("uspto")
def ingest_uspto(url: str = typer.Option(..., help="Official Gazette notices TOC URL")):
    with _client() as client:
        count = _ingest("uspto_official_gazette", USPTOOfficialGazette(client, url=url).fetch())
    typer.echo(f"Upserted {count} USPTO signals")


@ingest_app.command("flc")
def ingest_flc():
    with _client() as client:
        count = _ingest("flc_license_notices", FLCLicenseNotices(client).fetch())
    typer.echo(f"Upserted {count} FLC licensing signals")


@ingest_app.command("california")
def ingest_california(
    bucket: str = typer.Option(
        "500_plus", help="under_10, 10_to_99, 100_to_499, 500_plus, or all"
    )
):
    """Download and ingest California's official public ZIP/CSV property dataset."""
    with _client() as client:
        adapter = CaliforniaUnclaimedProperty(client)
        count = _ingest(adapter.source_id, adapter.fetch(bucket=bucket))
    typer.echo(f"Upserted {count} California unclaimed-property records from {bucket}")


@ingest_app.command("california-file")
def ingest_california_file(path: Path = typer.Argument(..., exists=True, readable=True)):
    """Ingest a California public property ZIP/CSV already downloaded from SCO."""
    with _client() as client:
        adapter = CaliforniaUnclaimedProperty(client)
        count = _ingest(adapter.source_id, adapter.from_path(path))
    typer.echo(f"Upserted {count} California records from {path}")


@ingest_app.command("new-york-file")
def ingest_new_york_file(path: Path = typer.Argument(..., exists=True, readable=True)):
    """Ingest the NY OSC owner-name file after obtaining it through OSC's request flow."""
    adapter = NewYorkOwnerFile()
    count = _ingest(adapter.source_id, adapter.from_path(path))
    typer.echo(f"Upserted {count} New York owner-file records from {path}")

@ingest_app.command("soundexchange-file")
def ingest_soundexchange_file(path: Path = typer.Argument(..., exists=True, readable=True)):
    """Import a legitimately obtained public SoundExchange unclaimed-status list/export."""
    adapter = SoundExchangeStatusFile()
    count = _ingest(adapter.source_id, adapter.from_path(path))
    typer.echo(f"Upserted {count} SoundExchange status records from {path}")


@ingest_app.command("mlc-file")
def ingest_mlc_file(path: Path = typer.Argument(..., exists=True, readable=True)):
    """Import an authorized MLC metadata/reconciliation export."""
    adapter = MLCDataFile()
    count = _ingest(adapter.source_id, adapter.from_path(path))
    typer.echo(f"Upserted {count} MLC metadata records from {path}")


@ingest_app.command("treasury-checks-file")
def ingest_treasury_checks_file(path: Path = typer.Argument(..., exists=True, readable=True)):
    """Import canceled/unpaid federal-check records lawfully obtained from Treasury/an agency."""
    adapter = TreasuryCanceledCheckFile()
    count = _ingest(adapter.source_id, adapter.from_path(path))
    typer.echo(f"Upserted {count} Treasury/federal check signals from {path}")


@ingest_app.command("sam-opportunities-file")
def ingest_sam_opportunities_file(path: Path = typer.Argument(..., exists=True, readable=True)):
    """Import SAM.gov's public Contract Opportunities file extract."""
    adapter = SAMContractOpportunitiesFile()
    count = _ingest(adapter.source_id, adapter.from_path(path))
    typer.echo(f"Upserted {count} SAM.gov contract-opportunity records from {path}")

@ingest_app.command("bankruptcy-file")
def ingest_bankruptcy_file(path: Path = typer.Argument(..., exists=True, readable=True)):
    """Import an official/manual bankruptcy unclaimed-funds export without bypassing CAPTCHA."""
    adapter = BankruptcyUnclaimedFundsFile()
    count = _ingest(adapter.source_id, adapter.from_path(path))
    typer.echo(f"Upserted {count} bankruptcy unclaimed-funds records from {path}")


@ingest_app.command("surplus-file")
def ingest_surplus_file(
    path: Path = typer.Argument(..., exists=True, readable=True),
    jurisdiction: str = typer.Option(..., help="Jurisdiction stated by the official source"),
    custodian: str = typer.Option(..., help="Court/county/agency holding the official dataset"),
    source_url: str = typer.Option(..., help="Official source URL for provenance"),
):
    """Import an official surplus-funds file while preserving jurisdiction/custodian provenance."""
    adapter = OfficialSurplusFundsFile()
    count = _ingest(
        adapter.source_id,
        adapter.from_path(path, jurisdiction=jurisdiction, custodian=custodian, source_url=source_url),
    )
    typer.echo(f"Upserted {count} official surplus-funds records from {path}")


@ingest_app.command("companies-house-dissolved-search")
def ingest_companies_house_dissolved_search(
    query: str,
    size: int = typer.Option(100, min=1, max=100),
):
    """Ingest dissolved-company results as intelligence records for cross-source resolution."""
    settings = load_settings()
    if not settings.companies_house_api_key:
        raise typer.BadParameter("Set COMPANIES_HOUSE_API_KEY first")
    with _client() as client:
        data = CompaniesHouseClient(settings.companies_house_api_key, client).search_dissolved(
            query, size=size
        )
    count = _ingest("companies_house", normalize_dissolved_items(data))
    typer.echo(f"Upserted {count} dissolved-company records")


@ingest_app.command("companies-house-dissolved-range")
def ingest_companies_house_dissolved_range(
    dissolved_from: str,
    dissolved_to: str,
    size: int = typer.Option(1000, min=1, max=5000),
    location: str | None = None,
):
    """Ingest a date range of dissolved Companies House entities."""
    settings = load_settings()
    if not settings.companies_house_api_key:
        raise typer.BadParameter("Set COMPANIES_HOUSE_API_KEY first")
    with _client() as client:
        data = CompaniesHouseClient(settings.companies_house_api_key, client).advanced_dissolved(
            dissolved_from=dissolved_from,
            dissolved_to=dissolved_to,
            size=size,
            location=location,
        )
    count = _ingest("companies_house", normalize_dissolved_items(data))
    typer.echo(f"Upserted {count} dissolved-company records")


@company_app.command("dissolved-search")
def dissolved_search(
    query: str,
    size: int = typer.Option(25, min=1, max=100),
):
    settings = load_settings()
    if not settings.companies_house_api_key:
        raise typer.BadParameter("Set COMPANIES_HOUSE_API_KEY first")
    with _client() as client:
        data = CompaniesHouseClient(settings.companies_house_api_key, client).search_dissolved(
            query, size=size
        )
    typer.echo(json.dumps(data, indent=2))


@company_app.command("dissolved-range")
def dissolved_range(
    dissolved_from: str,
    dissolved_to: str,
    size: int = typer.Option(100, min=1, max=5000),
    location: str | None = None,
):
    settings = load_settings()
    if not settings.companies_house_api_key:
        raise typer.BadParameter("Set COMPANIES_HOUSE_API_KEY first")
    with _client() as client:
        data = CompaniesHouseClient(settings.companies_house_api_key, client).advanced_dissolved(
            dissolved_from=dissolved_from,
            dissolved_to=dissolved_to,
            size=size,
            location=location,
        )
    typer.echo(json.dumps(data, indent=2))



@app.command("resolve")
def resolve_entities(
    fuzzy: bool = typer.Option(True, "--fuzzy/--no-fuzzy"),
    fuzzy_limit: int = typer.Option(5000, min=0, max=50000),
    min_fuzzy_score: float = typer.Option(0.90, min=0.80, max=1.0),
):
    """Rebuild the conservative entity/evidence graph from ingested records."""
    stats = rebuild_entity_graph(
        _db(), fuzzy=fuzzy, fuzzy_limit=fuzzy_limit, min_fuzzy_score=min_fuzzy_score
    )
    typer.echo(
        f"entities={stats.entities} memberships={stats.memberships} "
        f"relations={stats.relations} fuzzy_relations={stats.fuzzy_relations}"
    )


@app.command("entities")
def entities(
    limit: int = 50,
    min_sources: int = typer.Option(2, min=1),
    entity_type: str | None = None,
):
    """List canonical identifier/name entities with cross-source coverage."""
    rows = _db().list_entities(limit=limit, min_sources=min_sources, entity_type=entity_type)
    if not rows:
        typer.echo("No resolved entities match the filters; run `fia resolve` after ingestion")
        return
    for row in rows:
        typer.echo(
            f"{row['id']:>5} {row['entity_type']:<14} sources={row['source_count']:<2} "
            f"records={row['opportunity_count']:<3} confidence={row['confidence']:.2f} "
            f"{row['display_name']}"
        )


@app.command("relations")
def relations(
    limit: int = 50,
    relation_type: str | None = None,
    min_confidence: float = typer.Option(0.0, min=0.0, max=1.0),
):
    """List evidence-graph relations, including reviewable organization-name variants."""
    rows = _db().list_entity_relations(
        limit=limit, relation_type=relation_type, min_confidence=min_confidence
    )
    if not rows:
        typer.echo("No entity relations match the filters")
        return
    for row in rows:
        typer.echo(
            f"{row['relation_type']:<30} {row['confidence']:.3f}  "
            f"{row['left_name']}  <->  {row['right_name']}"
        )


@app.command("graph")
def graph(entity_id: int):
    """Print one entity's evidence graph as JSON."""
    result = _db().entity_graph(entity_id)
    if result is None:
        raise typer.BadParameter(f"Unknown entity id: {entity_id}")
    typer.echo(json.dumps(result, indent=2))


@app.command("infer")
def infer_commercial(
    rebuild_entities: bool = typer.Option(True, "--rebuild-entities/--no-rebuild-entities"),
    fuzzy: bool = typer.Option(True, "--fuzzy/--no-fuzzy"),
):
    """Build commercial triage scores and hard action gates from the evidence graph."""
    if rebuild_entities:
        rebuild_entity_graph(_db(), fuzzy=fuzzy)
    stats = rebuild_commercial_assessments(_db())
    typer.echo(f"assessed_opportunities={stats.opportunities} assessed_entities={stats.entities}")


@app.command("detect")
def detect(
    rebuild_entities: bool = typer.Option(True, "--rebuild-entities/--no-rebuild-entities"),
    rebuild_commercial: bool = typer.Option(True, "--rebuild-commercial/--no-rebuild-commercial"),
    fuzzy: bool = typer.Option(True, "--fuzzy/--no-fuzzy"),
):
    """Run the anomaly/discrepancy detector over the current evidence graph."""
    database = _db()
    if rebuild_entities:
        rebuild_entity_graph(database, fuzzy=fuzzy)
    if rebuild_commercial:
        rebuild_commercial_assessments(database)
    stats = detect_anomalies(database)
    typer.echo(
        f"findings={stats.findings} entities_scanned={stats.entities_scanned} "
        f"opportunity_findings={stats.opportunity_findings}"
    )


@app.command("anomaly-rules")
def anomaly_rules():
    """List the explainable v0.5 anomaly rules."""
    for rule in RULE_CATALOG:
        typer.echo(
            f"{rule['rule_id']:<34} min_sources={rule['minimum_sources']}  "
            f"{rule['description']}"
        )


@app.command("anomalies")
def anomalies(
    limit: int = 50,
    min_severity: float = typer.Option(0, min=0, max=100),
    anomaly_type: str | None = None,
    state: str = typer.Option("open", help="open, confirmed, dismissed, stale, or all"),
):
    """Rank compound anomaly findings by severity and evidence strength."""
    state_filter = None if state == "all" else state
    rows = _db().list_anomalies(
        limit=limit, min_severity=min_severity, anomaly_type=anomaly_type, state=state_filter
    )
    if not rows:
        typer.echo("No anomaly findings yet; run `fia detect`")
        return
    for row in rows:
        typer.echo(
            f"#{row['id']:<4} sev={row['severity_score']:>5.1f} conf={row['confidence']:.2f} "
            f"{row['anomaly_type']:<30} {row['title'][:90]}"
        )


@app.command("anomaly")
def anomaly(anomaly_id: int):
    """Print one anomaly with provenance, blocks, and next actions."""
    result = _db().anomaly_case(anomaly_id)
    if result is None:
        raise typer.BadParameter(f"Unknown anomaly id: {anomaly_id}")
    typer.echo(json.dumps(result, indent=2))


@app.command("anomaly-state")
def anomaly_state(anomaly_id: int, state: str):
    """Record analyst review state without deleting the finding history."""
    try:
        changed = _db().set_anomaly_state(anomaly_id, state)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if not changed:
        raise typer.BadParameter(f"Unknown anomaly id: {anomaly_id}")
    typer.echo(f"anomaly={anomaly_id} state={state}")


@app.command("pipeline")
def pipeline(
    fuzzy: bool = typer.Option(True, "--fuzzy/--no-fuzzy"),
):
    """Assimilate completed research, rebuild the graph, re-score, detect, and plan the next wave."""
    database = _db()
    feedback_stats = assimilate_research_results(database)
    resolution = rebuild_entity_graph(database, fuzzy=fuzzy)
    commercial_stats = rebuild_commercial_assessments(database)
    anomaly_stats = detect_anomalies(database)
    route_stats = rebuild_monetization_routes(database)
    research_stats = plan_research(database)
    case_stats = rebuild_case_resolutions(database)
    economic_stats = rebuild_case_economics(database)
    typer.echo(
        f"feedback_tasks={feedback_stats.tasks_ingested} facts={feedback_stats.facts_written} "
        f"entities={resolution.entities} relations={resolution.relations} "
        f"commercial={commercial_stats.opportunities} anomalies={anomaly_stats.findings} "
        f"routes={route_stats.opportunity_routes + route_stats.anomaly_routes} "
        f"research_tasks={research_stats.tasks} cases={case_stats.cases} "
        f"review_ready={case_stats.review_ready} researching={case_stats.researching} "
        f"economic_cases={economic_stats.economically_ranked} value_unknown={economic_stats.unknown_value}"
    )



@app.command("resolve-cases")
def resolve_cases(base_budget: float = typer.Option(100.0, min=0, help="Base research-budget units per case")):
    """Compute target-state progress and the next best lookup for every active anomaly."""
    stats = rebuild_case_resolutions(_db(), base_budget=base_budget)
    typer.echo(
        f"cases={stats.cases} review_ready={stats.review_ready} researching={stats.researching} "
        f"blocked={stats.blocked} budget_exhausted={stats.budget_exhausted}"
    )


@app.command("cases")
def cases(
    limit: int = 50,
    status: str | None = typer.Option(None, help="researching, review_ready, blocked, budget_exhausted"),
    min_resolution: float = typer.Option(0, min=0, max=100),
):
    """List cases by target-state progress and expected value of the next lookup."""
    rows = _db().list_case_resolutions(limit=limit, status=status, min_resolution=min_resolution)
    if not rows:
        typer.echo("No case-resolution states yet; run `fia pipeline` or `fia resolve-cases`")
        return
    for row in rows:
        next_bit = f" next={row['next_task_type']} evi={row['next_task_evi']:.1f}" if row['next_task_id'] else ""
        typer.echo(
            f"#{row['anomaly_id']:<4} {row['resolution_status']:<16} "
            f"progress={row['resolution_score']:>5.1f}% budget={row['budget_remaining']:>6.1f}{next_bit}  "
            f"{row['title'][:72]}"
        )


@app.command("case-resolution")
def case_resolution(anomaly_id: int):
    """Show a case target, satisfied/missing conditions, gates, budget and ranked lookups."""
    result = _db().case_resolution(anomaly_id)
    if result is None:
        raise typer.BadParameter(f"Unknown/unresolved anomaly id: {anomaly_id}; run `fia resolve-cases`")
    typer.echo(json.dumps(result, indent=2))


@app.command("next-lookup")
def next_lookup(anomaly_id: int):
    """Print the single highest-EVI eligible research task for a case."""
    result = _db().next_case_task(anomaly_id)
    if result is None:
        case = _db().case_resolution(anomaly_id)
        if case is None:
            raise typer.BadParameter(f"Unknown/unresolved anomaly id: {anomaly_id}")
        typer.echo(json.dumps({
            "anomaly_id": anomaly_id,
            "resolution_status": case["resolution_status"],
            "unresolved_conditions": case["unresolved_conditions"],
            "hard_gates": case["hard_gates"],
            "next_task": None,
        }, indent=2))
        return
    typer.echo(json.dumps(result, indent=2))

@app.command("economics")
def economics(
    hourly_research_cost: float = typer.Option(25.0, min=0),
    default_intelligence_value: float = typer.Option(250.0, min=0),
    unknown_capture_rate: float = typer.Option(0.05, min=0, max=1),
):
    """Build adaptive planning economics for cases and pending research tasks."""
    stats = rebuild_case_economics(
        _db(),
        hourly_research_cost=hourly_research_cost,
        default_intelligence_value=default_intelligence_value,
        unknown_capture_rate=unknown_capture_rate,
    )
    typer.echo(
        f"cases={stats.cases} economically_ranked={stats.economically_ranked} "
        f"value_unknown={stats.unknown_value}"
    )


@app.command("economic-cases")
def economic_cases(
    limit: int = 50,
    min_expected_value: float = typer.Option(0, min=0),
    status: str | None = None,
):
    """List cases by probability/time/regulation-adjusted planning value."""
    rows = _db().list_case_economics(limit=limit, min_expected_value=min_expected_value, status=status)
    if not rows:
        typer.echo("No case economics yet; run `fia pipeline` or `fia economics`")
        return
    for row in rows:
        money = (
            f"{row['currency'] or ''} {row['expected_case_value']:.2f}"
            if row['revenue_reference'] is not None else "value=unknown"
        )
        next_bit = (
            f" next={row['best_task_type']} econ={row['best_task_economic_score']:.1f}"
            if row['best_task_id'] else ""
        )
        typer.echo(
            f"#{row['anomaly_id']:<4} {row['economic_status']:<20} {money:<20}"
            f"{next_bit}  {row['title'][:68]}"
        )


@app.command("case-economics")
def case_economics(anomaly_id: int):
    """Show revenue basis, assumptions, expected case value and task economics."""
    result = _db().case_economics(anomaly_id)
    if result is None:
        raise typer.BadParameter(f"No economics for anomaly id: {anomaly_id}; run `fia economics`")
    typer.echo(json.dumps(result, indent=2))


@app.command("next-economic-lookup")
def next_economic_lookup(anomaly_id: int):
    """Show the research lookup with the strongest probability/time/cost-adjusted economics."""
    result = _db().next_economic_task(anomaly_id)
    if result is None:
        case = _db().case_economics(anomaly_id)
        if case is None:
            raise typer.BadParameter(f"No economics for anomaly id: {anomaly_id}")
        typer.echo(json.dumps({
            "anomaly_id": anomaly_id,
            "economic_status": case["economic_status"],
            "expected_case_value": case["expected_case_value"],
            "next_task": None,
        }, indent=2))
        return
    typer.echo(json.dumps(result, indent=2))



@app.command("scheduler-run")
def scheduler_run(
    execute: bool = typer.Option(False, "--execute", help="Actually call whitelisted read-only APIs; default is dry-run."),
    max_steps: int = typer.Option(20, min=0, max=500),
    max_planning_cost: float = typer.Option(250.0, min=0),
    min_economic_score: float = typer.Option(1.0, min=0, max=100),
    min_expected_case_value: float = typer.Option(0.0, min=0),
    companies_house_min_interval: float = typer.Option(0.60, min=0.50, help="Conservative interval; official default limit is 600 requests/5 minutes."),
):
    """Run the bounded read-only economic research scheduler. Outreach/claims/legal tasks never auto-execute."""
    config = SchedulerConfig(
        max_steps=max_steps,
        max_planning_cost=max_planning_cost,
        min_economic_score=min_economic_score,
        min_expected_case_value=min_expected_case_value,
        company_house_min_interval_seconds=companies_house_min_interval,
        dry_run=not execute,
    )
    stats = run_scheduler(_db(), config)
    typer.echo(json.dumps({
        "run_id": stats.run_id,
        "status": stats.status,
        "steps_executed": stats.steps_executed,
        "planning_cost_spent": stats.planning_cost_spent,
        "completed_task_ids": list(stats.completed_task_ids),
        "stop_reason": stats.stop_reason,
    }, indent=2))


@app.command("scheduler-runs")
def scheduler_runs(limit: int = 50):
    """List scheduler runs and their explicit stop states."""
    rows = _db().list_scheduler_runs(limit=limit)
    for row in rows:
        typer.echo(
            f"#{row['id']:<4} {row['status']:<24} steps={row['completed_tasks']:<3} "
            f"cost={row['planning_cost_spent']:>8.2f}  {row['stop_reason'] or ''}"
        )


@app.command("scheduler-run-detail")
def scheduler_run_detail(run_id: int):
    """Show one scheduler run with its selected/executed research steps."""
    result = _db().scheduler_run(run_id)
    if result is None:
        raise typer.BadParameter(f"Unknown scheduler run id: {run_id}")
    typer.echo(json.dumps(result, indent=2))

@app.command("assimilate")
def assimilate():
    """Normalize completed research results into durable evidence facts."""
    stats = assimilate_research_results(_db())
    typer.echo(
        f"scanned={stats.tasks_scanned} ingested={stats.tasks_ingested} "
        f"unchanged={stats.tasks_unchanged} facts={stats.facts_written} errors={stats.errors}"
    )


@app.command("facts")
def facts(
    limit: int = 50,
    source_id: str | None = None,
    relation_type: str | None = None,
    task_id: int | None = None,
):
    """List evidence facts extracted from completed research results."""
    rows = _db().list_research_facts(limit=limit, source_id=source_id, relation_type=relation_type, task_id=task_id)
    for row in rows:
        object_display = row["object_display_name"] or ""
        typer.echo(
            f"#{row['id']:<4} conf={row['confidence']:.2f} {row['source_id']:<18} "
            f"{row['subject_display_name']} --{row['relation_type'] or row['fact_type']}--> {object_display}"
        )


@app.command("feedback-runs")
def feedback_runs(limit: int = 50):
    """Show which completed task results have been assimilated."""
    for row in _db().list_research_result_ingestions(limit=limit):
        typer.echo(
            f"task={row['task_id']:<4} {row['status']:<8} facts={row['fact_count']:<3} "
            f"{row['task_type']:<36} {row['ingested_at']}"
        )


@app.command("task-result-file")
def task_result_file(task_id: int, path: Path):
    """Attach a structured JSON result to a manual or externally completed research task."""
    if not path.exists():
        raise typer.BadParameter(f"File not found: {path}")
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid JSON: {exc}") from exc
    if not isinstance(result, dict):
        raise typer.BadParameter("Research result JSON must be an object")
    database = _db()
    if database.research_task_case(task_id) is None:
        raise typer.BadParameter(f"Unknown research task id: {task_id}")
    database.complete_research_task(task_id, result=result)
    stats = assimilate_research_results(database)
    typer.echo(f"task={task_id} completed; assimilated={stats.tasks_ingested} facts={stats.facts_written}")


@app.command("plan")
def plan(include_confirmed: bool = typer.Option(True, "--include-confirmed/--open-only")):
    """Generate a ranked second-hop research queue from current anomalies."""
    stats = plan_research(_db(), include_confirmed=include_confirmed)
    typer.echo(f"tasks={stats.tasks} anomalies_scanned={stats.anomalies_scanned} stale_marked={stats.stale_marked}")


@app.command("research-task-types")
def research_task_types():
    """List research task types and their execution boundary."""
    for item in TASK_CATALOG:
        typer.echo(f"{item['task_type']:<36} {item['execution']:<24} {item['description']}")


@app.command("tasks")
def tasks(
    limit: int = 50,
    min_priority: float = typer.Option(0, min=0, max=100),
    task_type: str | None = None,
    state: str = typer.Option("pending", help="pending, in_progress, completed, dismissed, blocked, stale, or all"),
    anomaly_id: int | None = None,
):
    """List ranked missing-edge research tasks."""
    state_filter = None if state == "all" else state
    rows = _db().list_research_tasks(limit=limit, min_priority=min_priority, task_type=task_type, state=state_filter, anomaly_id=anomaly_id)
    if not rows:
        typer.echo("No research tasks match the filters; run `fia pipeline` or `fia plan`")
        return
    for row in rows:
        typer.echo(
            f"#{row['id']:<4} pri={row['priority_score']:>5.1f} uplift={row['expected_uplift']:>4.1f} "
            f"{row['access_mode']:<18} {row['task_type']:<34} {row['title'][:80]}"
        )


@app.command("task")
def task(task_id: int):
    """Print one research task with provenance, blockers, target and result."""
    result = _db().research_task_case(task_id)
    if result is None:
        raise typer.BadParameter(f"Unknown research task id: {task_id}")
    typer.echo(json.dumps(result, indent=2))


@app.command("task-state")
def task_state(task_id: int, state: str):
    """Persist analyst state without deleting the task audit trail."""
    try:
        changed = _db().set_research_task_state(task_id, state)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if not changed:
        raise typer.BadParameter(f"Unknown research task id: {task_id}")
    typer.echo(f"task={task_id} state={state}")


@app.command("task-execute")
def task_execute(task_id: int):
    """Execute a whitelisted read-only API task; manual/legal/CAPTCHA tasks stay manual."""
    try:
        result = execute_task(_db(), task_id)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(result, indent=2))


@app.command("commercial")
def commercial(
    limit: int = 50,
    min_score: float = typer.Option(0, min=0, max=100),
    lane: str | None = None,
    jurisdiction: str | None = None,
):
    """Rank monetization lanes by actionability while preserving compliance blocks."""
    rows = _db().list_commercial_assessments(
        limit=limit, min_score=min_score, lane=lane, jurisdiction=jurisdiction
    )
    if not rows:
        typer.echo("No commercial assessments yet; run `fia infer`")
        return
    for row in rows:
        fee = f" fee_ceiling={row['currency']} {row['gross_fee_ceiling']}" if row['gross_fee_ceiling'] else ""
        typer.echo(
            f"{row['actionability_score']:>5.1f}/{row['commercial_score']:>5.1f} "
            f"{row['lane']:<28} {row['jurisdiction']:<22}{fee}  {row['title'][:80]}"
        )


@app.command("entity-commercial")
def entity_commercial(
    limit: int = 50,
    min_score: float = typer.Option(0, min=0, max=100),
    min_sources: int = typer.Option(1, min=1),
):
    """Rank entity-level commercial cases assembled from multiple public records."""
    rows = _db().list_entity_commercial_summaries(
        limit=limit, min_score=min_score, min_sources=min_sources
    )
    if not rows:
        typer.echo("No entity commercial summaries yet; run `fia infer`")
        return
    for row in rows:
        typer.echo(
            f"{row['actionability_score']:>5.1f}/{row['commercial_score']:>5.1f} "
            f"sources={row['source_count']:<2} records={row['opportunity_count']:<3} "
            f"{row['primary_lane']:<28} {row['display_name']}"
        )


@app.command("case")
def commercial_case(opportunity_id: int):
    """Print one opportunity's commercial evidence, blocks, and next-action gates."""
    result = _db().commercial_case(opportunity_id)
    if result is None:
        raise typer.BadParameter(f"No assessed opportunity id: {opportunity_id}; run `fia infer`")
    typer.echo(json.dumps(result, indent=2))

@app.command("route-catalog")
def route_catalog():
    """List lawful monetization routes and their revenue models."""
    for item in ROUTE_CATALOG:
        typer.echo(f"{item['route_id']:<30} {item['revenue_model']:<44} {item['description']}")


@app.command("route")
def rebuild_routes():
    """Rebuild monetization routing for opportunities and anomaly cases."""
    stats = rebuild_monetization_routes(_db())
    typer.echo(f"opportunity_routes={stats.opportunity_routes} anomaly_routes={stats.anomaly_routes}")


@app.command("routes")
def routes(
    limit: int = 50,
    route_id: str | None = None,
    target_type: str | None = typer.Option(None, help="opportunity or anomaly"),
    min_score: float = typer.Option(0, min=0, max=100),
):
    """Rank lawful monetization routes without clearing their legal/action gates."""
    rows = _db().list_monetization_routes(
        limit=limit, route_id=route_id, target_type=target_type, min_score=min_score
    )
    if not rows:
        typer.echo("No monetization routes yet; run `fia route` or `fia pipeline`")
        return
    for row in rows:
        typer.echo(
            f"{row['route_score']:>5.1f} {row['target_type']:<11} #{row['target_id']:<5} "
            f"{row['route_id']:<30} {row['revenue_model']}"
        )


@app.command("route-case")
def route_case(target_type: str, target_id: int):
    """Show one route with prerequisites, prohibitions, and its underlying case/record."""
    result = _db().monetization_route(target_type, target_id)
    if result is None:
        raise typer.BadParameter(f"No route for {target_type} #{target_id}; run `fia route`")
    typer.echo(json.dumps(result, indent=2))


@app.command("rank")
def rank(limit: int = 30, min_score: float = 0):
    rows = _db().list_opportunities(limit=limit, min_score=min_score)
    for row in rows:
        typer.echo(f"{row['score']:>5.1f}  {row['asset_class']:<24} {row['title'][:90]}")


@app.command("joins")
def joins(limit: int = 50):
    """Show identifiers/names that collide across two or more source systems."""
    rows = _db().collisions(limit=limit)
    if not rows:
        typer.echo("No cross-source key collisions yet")
        return
    for row in rows:
        typer.echo(
            f"{row['key_type']:<16} {row['key_value']:<40} "
            f"sources={row['sources']} records={row['record_count']}"
        )


@app.command("runs")
def runs(limit: int = 30):
    for row in _db().list_runs(limit=limit):
        typer.echo(
            f"{row['id']:>4} {row['status']:<9} {row['source_id']:<28} "
            f"records={row['record_count']} new={row['new_count']} changed={row['changed_count']} "
            f"same={row['unchanged_count']} started={row['started_at']}"
        )


@app.command("changes")
def changes(limit: int = 50):
    """Show records whose normalized source content changed after first discovery."""
    rows = _db().recent_changes(limit=limit)
    if not rows:
        typer.echo("No changed opportunities recorded yet")
        return
    for row in rows:
        typer.echo(
            f"{row['last_changed_at']} {row['source_id']:<24} changes={row['change_count']:<3} "
            f"score={row['score']:<5.1f} {row['title'][:90]}"
        )


@app.command("export")
def export_csv(path: Path = Path("data/exports/opportunities.csv"), limit: int = 5000):
    rows = _db().list_opportunities(limit=limit)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        typer.echo(f"No records; created empty {path}")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
    typer.echo(f"Exported {len(rows)} records to {path}")


@app.command("serve")
def serve(host: str = "127.0.0.1", port: int = 8787):
    uvicorn.run("fia.api:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
