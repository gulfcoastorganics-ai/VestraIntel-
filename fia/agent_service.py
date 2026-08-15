from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .anomalies import detect_anomalies
from .case_resolution import rebuild_case_resolutions
from .commercial import rebuild_commercial_assessments
from .db import Database
from .economics import rebuild_case_economics
from .entity_resolution import rebuild_entity_graph
from .feedback import assimilate_research_results
from .monetization import rebuild_monetization_routes
from .portal_discovery import PortalDiscoveryConfig, discover_portals
from .portfolio import run_portfolio
from .research import plan_research
from .scheduler import SchedulerConfig, run_scheduler
from .source_discovery import SourceMiningConfig, mine_source_catalogs
from .source_orchestration import SourceOrchestratorConfig, ensure_source_states, run_source_orchestrator


def _rows(rows) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def run_analysis(db: Database, *, fuzzy: bool = True) -> dict[str, Any]:
    """Run local analysis only. No external source call is performed here."""
    feedback = assimilate_research_results(db)
    resolution = rebuild_entity_graph(db, fuzzy=fuzzy)
    commercial = rebuild_commercial_assessments(db)
    anomalies = detect_anomalies(db)
    routes = rebuild_monetization_routes(db)
    research = plan_research(db)
    cases = rebuild_case_resolutions(db)
    economics = rebuild_case_economics(db)
    return {
        "feedback_tasks": feedback.tasks_ingested,
        "facts_written": feedback.facts_written,
        "entities": resolution.entities,
        "relations": resolution.relations,
        "commercial_opportunities": commercial.opportunities,
        "anomalies": anomalies.findings,
        "monetization_routes": routes.opportunity_routes + routes.anomaly_routes,
        "research_tasks": research.tasks,
        "cases": cases.cases,
        "review_ready": cases.review_ready,
        "researching": cases.researching,
        "economic_cases": economics.economically_ranked,
        "unknown_value_cases": economics.unknown_value,
    }


def portfolio_snapshot(db: Database, *, limit: int = 10, min_expected_value: float = 0.0) -> dict[str, Any]:
    ensure_source_states(db)
    economic_cases = _rows(db.list_case_economics(limit=limit, min_expected_value=min_expected_value))
    return {
        "economic_cases": economic_cases,
        "review_ready": _rows(db.list_case_resolutions(limit=limit, status="review_ready")),
        "open_anomalies": _rows(db.list_anomalies(limit=limit, state="open")),
        "monetization_routes": _rows(db.list_monetization_routes(limit=limit, min_score=0)),
        "source_sync": _rows(db.list_source_sync_states(limit=limit)),
        "source_candidates": _rows(db.list_source_candidates(limit=limit, min_score=0, state="discovered")),
        "portal_candidates": _rows(db.list_portal_candidates(limit=limit, min_score=0, state="discovered")),
    }


def case_snapshot(db: Database, anomaly_id: int) -> dict[str, Any] | None:
    anomaly = db.anomaly_case(anomaly_id)
    if anomaly is None:
        return None
    return {
        "anomaly": anomaly,
        "resolution": db.case_resolution(anomaly_id),
        "economics": db.case_economics(anomaly_id),
        "next_economic_task": db.next_economic_task(anomaly_id),
        "monetization_route": db.monetization_route("anomaly", anomaly_id),
    }


def discover_sources(
    db: Database,
    *,
    queries: tuple[str, ...],
    catalog_ids: tuple[str, ...] = (),
    results_per_query: int = 25,
    min_score: float = 35.0,
    max_candidates: int = 500,
) -> dict[str, Any]:
    stats = mine_source_catalogs(
        db,
        SourceMiningConfig(
            catalog_ids=catalog_ids,
            queries=queries,
            results_per_query=results_per_query,
            min_score=min_score,
            max_candidates=max_candidates,
        ),
    )
    return asdict(stats)


def discover_portal_candidates(
    db: Database,
    *,
    urls: tuple[str, ...] = (),
    from_source_candidates: bool = True,
    min_source_score: float = 45.0,
    max_seeds: int = 50,
) -> dict[str, Any]:
    stats = discover_portals(
        db,
        PortalDiscoveryConfig(
            urls=urls,
            from_source_candidates=from_source_candidates,
            min_source_score=min_source_score,
            max_seeds=max_seeds,
        ),
    )
    return asdict(stats)


def refresh_sources(
    db: Database,
    *,
    execute: bool = False,
    source_ids: tuple[str, ...] = (),
    max_sources: int = 10,
) -> dict[str, Any]:
    stats = run_source_orchestrator(
        db,
        SourceOrchestratorConfig(
            dry_run=not execute,
            source_ids=source_ids,
            max_sources=max_sources,
        ),
    )
    return asdict(stats)


def research_portfolio(
    db: Database,
    *,
    execute: bool = False,
    max_steps: int = 10,
    max_planning_cost: float = 125.0,
    min_economic_score: float = 1.0,
    min_expected_case_value: float = 0.0,
) -> dict[str, Any]:
    stats = run_scheduler(
        db,
        SchedulerConfig(
            dry_run=not execute,
            max_steps=max_steps,
            max_planning_cost=max_planning_cost,
            min_economic_score=min_economic_score,
            min_expected_case_value=min_expected_case_value,
        ),
    )
    return asdict(stats)


def run_portfolio_cycle(
    db: Database,
    *,
    execute_sources: bool = False,
    execute_research: bool = False,
    max_source_refreshes: int = 10,
    max_research_steps: int = 10,
    max_planning_cost: float = 125.0,
) -> dict[str, Any]:
    result = run_portfolio(
        db,
        source_config=SourceOrchestratorConfig(
            dry_run=not execute_sources,
            max_sources=max_source_refreshes,
        ),
        research_config=SchedulerConfig(
            dry_run=not execute_research,
            max_steps=max_research_steps,
            max_planning_cost=max_planning_cost,
        ),
    )
    return {
        "sources": asdict(result.sources),
        "research": asdict(result.research),
    }
