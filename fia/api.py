from __future__ import annotations

import html
import hmac

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from .config import load_settings
from .db import Database
from .registry import SOURCES
from .anomalies import RULE_CATALOG
from .research import TASK_CATALOG
from .source_orchestration import ensure_source_states
from .monetization import ROUTE_CATALOG
from .source_discovery import DISCOVERY_CATALOGS
from .portal_discovery import PORTAL_TECHNOLOGIES
from .agent_api import router as agent_router
from .gpt_actions import build_action_schema

app = FastAPI(title="Forgotten Asset Intelligence", version="1.5.0")
app.include_router(agent_router)


@app.middleware("http")
async def protect_deployed_data(request: Request, call_next):
    """Fail closed on deployed operational surfaces when FIA_AGENT_API_KEY is configured.

    Local development remains unchanged when the key is absent. Public health, action-schema, and
    privacy endpoints stay available so hosting checks and the GPT editor can reach them.
    """
    settings = load_settings()
    protected = request.url.path == "/" or request.url.path.startswith("/api/") or request.url.path.startswith("/agent/")
    if settings.agent_api_key and protected:
        auth = request.headers.get("authorization", "")
        supplied = auth[7:] if auth.lower().startswith("bearer ") else ""
        if not supplied or not hmac.compare_digest(supplied, settings.agent_api_key):
            return JSONResponse({"detail": "invalid Vestra Intel API credential"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
    return await call_next(request)


@app.get("/gpt/openapi.json", include_in_schema=False)
def gpt_action_schema(request: Request):
    settings = load_settings()
    base_url = settings.public_base_url or str(request.base_url).rstrip("/")
    return JSONResponse(build_action_schema(base_url))


@app.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
def privacy_policy():
    return """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Vestra Intel Privacy Policy</title></head><body style='font-family:system-ui,sans-serif;max-width:850px;margin:3rem auto;padding:0 1rem;line-height:1.55'><h1>Vestra Intel Privacy Policy</h1><p><strong>Last updated: August 14, 2026.</strong></p><p>Vestra Intel is a research and intelligence service that analyzes public, authorized, and user-supplied records. Requests sent through the Vestra Intel GPT Action API are processed by the Vestra Intel backend to retrieve, analyze, score, or update the user's local research state.</p><h2>Data handled</h2><p>The service may process API request parameters, public-record metadata, source identifiers, case/anomaly identifiers, research results, and analyst review states. API credentials are used only for authentication and must not be stored in prompts or knowledge files.</p><h2>Purpose</h2><p>Data is used to provide asset/right discovery, entity resolution, public-data research, economic prioritization, and audit history. Vestra Intel does not automatically submit claims, purchase assets, contact claimants, or make binding legal entitlement decisions.</p><h2>Retention</h2><p>Research state is retained in the configured Vestra Intel database until the operator deletes or replaces that database. Server and hosting providers may retain operational logs according to their own policies.</p><h2>Third parties</h2><p>When an authorized source refresh or research action is executed, requests may be sent to the public or credentialed source named by the action. Those sources are governed by their own terms and privacy policies.</p><h2>Contact</h2><p>The operator should publish a business contact address on the deployed version of this page before distributing the GPT publicly.</p></body></html>"""


def db() -> Database:
    return Database(load_settings().db_path)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/sources")
def sources():
    return SOURCES


@app.get("/api/opportunities")
def opportunities(
    limit: int = Query(100, ge=1, le=1000),
    asset_class: str | None = None,
    jurisdiction: str | None = None,
    min_score: float | None = Query(None, ge=0, le=100),
):
    return [
        dict(r)
        for r in db().list_opportunities(
            limit=limit,
            asset_class=asset_class,
            jurisdiction=jurisdiction,
            min_score=min_score,
        )
    ]


@app.get("/api/joins")
def joins(limit: int = Query(100, ge=1, le=1000)):
    return [dict(r) for r in db().collisions(limit=limit)]


@app.get("/api/entities")
def entities(
    limit: int = Query(100, ge=1, le=1000),
    min_sources: int = Query(1, ge=1),
    entity_type: str | None = None,
):
    return [
        dict(r)
        for r in db().list_entities(
            limit=limit, min_sources=min_sources, entity_type=entity_type
        )
    ]


@app.get("/api/entities/{entity_id}")
def entity_graph(entity_id: int):
    result = db().entity_graph(entity_id)
    if result is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="entity not found")
    return result


@app.get("/api/entity-relations")
def entity_relations(
    limit: int = Query(100, ge=1, le=1000),
    relation_type: str | None = None,
    min_confidence: float = Query(0, ge=0, le=1),
):
    return [
        dict(r)
        for r in db().list_entity_relations(
            limit=limit, relation_type=relation_type, min_confidence=min_confidence
        )
    ]



@app.get("/api/commercial")
def commercial_assessments(
    limit: int = Query(100, ge=1, le=1000),
    min_score: float = Query(0, ge=0, le=100),
    lane: str | None = None,
    jurisdiction: str | None = None,
):
    return [dict(r) for r in db().list_commercial_assessments(
        limit=limit, min_score=min_score, lane=lane, jurisdiction=jurisdiction
    )]


@app.get("/api/commercial/entities")
def commercial_entities(
    limit: int = Query(100, ge=1, le=1000),
    min_score: float = Query(0, ge=0, le=100),
    min_sources: int = Query(1, ge=1),
):
    return [dict(r) for r in db().list_entity_commercial_summaries(
        limit=limit, min_score=min_score, min_sources=min_sources
    )]


@app.get("/api/commercial/{opportunity_id}")
def commercial_case(opportunity_id: int):
    result = db().commercial_case(opportunity_id)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="commercial assessment not found")
    return result

@app.get("/api/anomaly-rules")
def anomaly_rules():
    return list(RULE_CATALOG)


@app.get("/api/anomalies")
def anomalies(
    limit: int = Query(100, ge=1, le=1000),
    min_severity: float = Query(0, ge=0, le=100),
    anomaly_type: str | None = None,
    state: str | None = "open",
):
    return [dict(r) for r in db().list_anomalies(
        limit=limit, min_severity=min_severity, anomaly_type=anomaly_type, state=state
    )]


@app.get("/api/anomalies/{anomaly_id}")
def anomaly_case(anomaly_id: int):
    result = db().anomaly_case(anomaly_id)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="anomaly not found")
    return result


@app.get("/api/research-task-types")
def research_task_types():
    return list(TASK_CATALOG)


@app.get("/api/research-tasks")
def research_tasks(
    limit: int = Query(100, ge=1, le=1000),
    min_priority: float = Query(0, ge=0, le=100),
    task_type: str | None = None,
    state: str | None = "pending",
    anomaly_id: int | None = None,
):
    return [dict(r) for r in db().list_research_tasks(
        limit=limit, min_priority=min_priority, task_type=task_type, state=state, anomaly_id=anomaly_id
    )]


@app.get("/api/research-tasks/{task_id}")
def research_task_case(task_id: int):
    result = db().research_task_case(task_id)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="research task not found")
    return result


@app.get("/api/research-facts")
def research_facts(
    limit: int = Query(100, ge=1, le=1000),
    source_id: str | None = None,
    relation_type: str | None = None,
    task_id: int | None = None,
):
    return [dict(r) for r in db().list_research_facts(
        limit=limit, source_id=source_id, relation_type=relation_type, task_id=task_id
    )]


@app.get("/api/research-feedback")
def research_feedback(limit: int = Query(100, ge=1, le=1000)):
    return [dict(r) for r in db().list_research_result_ingestions(limit=limit)]



@app.get("/api/cases")
def case_resolutions(
    limit: int = Query(100, ge=1, le=1000),
    status: str | None = None,
    min_resolution: float = Query(0, ge=0, le=100),
):
    return [dict(r) for r in db().list_case_resolutions(
        limit=limit, status=status, min_resolution=min_resolution
    )]


@app.get("/api/cases/{anomaly_id}")
def case_resolution(anomaly_id: int):
    result = db().case_resolution(anomaly_id)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="case resolution not found")
    return result


@app.get("/api/cases/{anomaly_id}/next-task")
def case_next_task(anomaly_id: int):
    result = db().next_case_task(anomaly_id)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="no eligible next task")
    return result

@app.get("/api/economic-cases")
def economic_cases(
    limit: int = Query(100, ge=1, le=1000),
    min_expected_value: float = Query(0, ge=0),
    status: str | None = None,
):
    return [dict(r) for r in db().list_case_economics(
        limit=limit, min_expected_value=min_expected_value, status=status
    )]


@app.get("/api/economic-cases/{anomaly_id}")
def case_economics(anomaly_id: int):
    result = db().case_economics(anomaly_id)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="case economics not found")
    return result


@app.get("/api/economic-cases/{anomaly_id}/next-task")
def case_next_economic_task(anomaly_id: int):
    result = db().next_economic_task(anomaly_id)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="no economically ranked next task")
    return result




@app.get("/api/scheduler/runs")
def scheduler_runs(limit: int = Query(100, ge=1, le=1000)):
    return [dict(r) for r in db().list_scheduler_runs(limit=limit)]


@app.get("/api/scheduler/runs/{run_id}")
def scheduler_run(run_id: int):
    result = db().scheduler_run(run_id)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="scheduler run not found")
    return result


@app.get("/api/scheduler/steps")
def scheduler_steps(limit: int = Query(100, ge=1, le=1000), run_id: int | None = None):
    return [dict(r) for r in db().list_scheduler_steps(limit=limit, run_id=run_id)]



@app.get("/api/source-discovery/catalogs")
def source_discovery_catalogs():
    return list(DISCOVERY_CATALOGS)


@app.get("/api/source-discovery/candidates")
def source_discovery_candidates(
    limit: int = Query(100, ge=1, le=1000),
    min_score: float = Query(0, ge=0, le=100),
    catalog_id: str | None = None,
    route: str | None = None,
    state: str | None = "discovered",
):
    return [dict(r) for r in db().list_source_candidates(
        limit=limit, min_score=min_score, catalog_id=catalog_id, route=route, state=state
    )]


@app.get("/api/source-discovery/candidates/{candidate_id}")
def source_discovery_candidate(candidate_id: int):
    result = db().source_candidate(candidate_id)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="source candidate not found")
    return result


@app.get("/api/source-discovery/runs")
def source_discovery_runs(limit: int = Query(100, ge=1, le=1000)):
    return [dict(r) for r in db().list_source_mining_runs(limit=limit)]


@app.get("/api/portal-discovery/technologies")
def portal_discovery_technologies():
    return list(PORTAL_TECHNOLOGIES)


@app.get("/api/portal-discovery/candidates")
def portal_discovery_candidates(
    limit: int = Query(100, ge=1, le=1000),
    min_score: float = Query(0, ge=0, le=100),
    portal_type: str | None = None,
    state: str | None = "discovered",
):
    return [dict(r) for r in db().list_portal_candidates(
        limit=limit, min_score=min_score, portal_type=portal_type, state=state
    )]


@app.get("/api/portal-discovery/candidates/{candidate_id}")
def portal_discovery_candidate(candidate_id: int):
    result = db().portal_candidate(candidate_id)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="portal candidate not found")
    return result


@app.get("/api/portal-discovery/runs")
def portal_discovery_runs(limit: int = Query(100, ge=1, le=1000)):
    return [dict(r) for r in db().list_portal_discovery_runs(limit=limit)]


@app.get("/api/source-sync")
def source_sync(limit: int = Query(100, ge=1, le=1000)):
    database = db()
    ensure_source_states(database)
    return [dict(r) for r in database.list_source_sync_states(limit=limit)]


@app.get("/api/source-sync/events")
def source_sync_events(limit: int = Query(100, ge=1, le=1000), source_id: str | None = None):
    return [dict(r) for r in db().list_source_sync_events(limit=limit, source_id=source_id)]


@app.get("/api/monetization-route-catalog")
def monetization_route_catalog():
    return list(ROUTE_CATALOG)


@app.get("/api/monetization-routes")
def monetization_routes(
    limit: int = Query(100, ge=1, le=1000),
    route_id: str | None = None,
    target_type: str | None = None,
    min_score: float = Query(0, ge=0, le=100),
):
    return [dict(r) for r in db().list_monetization_routes(
        limit=limit, route_id=route_id, target_type=target_type, min_score=min_score
    )]


@app.get("/api/monetization-routes/{target_type}/{target_id}")
def monetization_route_case(target_type: str, target_id: int):
    result = db().monetization_route(target_type, target_id)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="monetization route not found")
    return result

@app.get("/api/runs")
def runs(limit: int = Query(100, ge=1, le=1000)):
    return [dict(r) for r in db().list_runs(limit=limit)]


@app.get("/api/changes")
def changes(limit: int = Query(100, ge=1, le=1000)):
    return [dict(r) for r in db().recent_changes(limit=limit)]


@app.get("/", response_class=HTMLResponse)
def dashboard(min_score: float = 0):
    database = db()
    commercial_rows = database.list_commercial_assessments(limit=250, min_score=min_score)
    rows = commercial_rows or database.list_opportunities(limit=250, min_score=min_score)
    runs = database.list_runs(limit=10)
    changes = database.recent_changes(limit=10)
    collisions = database.collisions(limit=10)
    entities = database.list_entities(limit=10, min_sources=2)
    relations = database.list_entity_relations(limit=10, min_confidence=0.9)
    anomalies = database.list_anomalies(limit=10, min_severity=0, state="open")
    research_tasks = database.list_research_tasks(limit=10, min_priority=0, state="pending")
    research_facts = database.list_research_facts(limit=10)
    cases = database.list_case_resolutions(limit=10)
    economic_cases = database.list_case_economics(limit=10)

    tr = []
    for row in rows:
        commercial_score = row['commercial_score'] if 'commercial_score' in row.keys() else row['score']
        actionability = row['actionability_score'] if 'actionability_score' in row.keys() else row['score']
        lane = row['lane'] if 'lane' in row.keys() else row['legal_model']
        tr.append(
            "<tr>"
            f"<td>{actionability:.1f}</td>"
            f"<td>{commercial_score:.1f}</td>"
            f"<td>{html.escape(lane)}</td>"
            f"<td>{html.escape(row['asset_class'])}</td>"
            f"<td>{html.escape(row['jurisdiction'])}</td>"
            f"<td><a href='{html.escape(row['source_url'])}' target='_blank' rel='noreferrer'>"
            f"{html.escape(row['title'])}</a></td>"
            f"<td>{html.escape(row['compliance_status'])}</td>"
            "</tr>"
        )
    body = "\n".join(tr) or "<tr><td colspan='7'>No opportunities ingested yet.</td></tr>"
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Forgotten Asset Intelligence</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1400px;margin:2rem auto;padding:0 1rem;background:#0e1116;color:#e8edf2}}
a{{color:#8fc7ff}}table{{width:100%;border-collapse:collapse}}th,td{{padding:.7rem;border-bottom:1px solid #29313a;text-align:left;vertical-align:top}}th{{position:sticky;top:0;background:#0e1116}}.pill{{display:inline-block;padding:.25rem .5rem;border:1px solid #394553;border-radius:999px;margin-right:.5rem}}input{{background:#161b22;color:#fff;border:1px solid #394553;border-radius:6px;padding:.5rem}}button{{padding:.5rem .8rem}}
</style></head><body>
<h1>Forgotten Asset Intelligence</h1>
<p>Discovery and ranking only. Entitlement, outreach, assignments and claims remain human-reviewed.</p>
<form><label>Minimum score <input name='min_score' type='number' min='0' max='100' value='{min_score}'></label> <button>Filter</button></form>
<p><span class='pill'>{len(rows)} opportunities</span><span class='pill'>{len(changes)} recent changes</span><span class='pill'>{len(collisions)} raw joins</span><span class='pill'>{len(entities)} resolved entities</span><span class='pill'>{len(relations)} graph relations</span><span class='pill'>{len(anomalies)} open anomalies</span><span class='pill'>{len(research_tasks)} pending research tasks</span><span class='pill'>{len(research_facts)} research facts</span><span class='pill'>{len(cases)} resolved cases</span><span class='pill'>{len(economic_cases)} economic cases</span><span class='pill'>{len(runs)} recent runs</span></p>
<table><thead><tr><th>Actionable</th><th>Commercial</th><th>Lane</th><th>Class</th><th>Jurisdiction</th><th>Opportunity</th><th>Gate</th></tr></thead><tbody>{body}</tbody></table>
</body></html>"""
