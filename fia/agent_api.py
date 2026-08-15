from __future__ import annotations

import hmac
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from .agent_service import (
    case_snapshot,
    discover_portal_candidates,
    discover_sources,
    portfolio_snapshot,
    refresh_sources,
    research_portfolio,
    run_analysis,
    run_portfolio_cycle,
)
from .config import load_settings
from .db import Database
from .source_discovery import DEFAULT_DISCOVERY_QUERIES

router = APIRouter(prefix="/agent", tags=["Vestra Intel GPT"])
_bearer = HTTPBearer(auto_error=False)


def _db() -> Database:
    return Database(load_settings().db_path)


def require_agent_key(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> None:
    expected = load_settings().agent_api_key
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="FIA_AGENT_API_KEY is not configured on the server",
        )
    supplied = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else ""
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid Vestra Intel API credential",
            headers={"WWW-Authenticate": "Bearer"},
        )


class AnalyzeRequest(BaseModel):
    fuzzy: bool = True


class SourceDiscoveryRequest(BaseModel):
    queries: list[str] = Field(default_factory=lambda: list(DEFAULT_DISCOVERY_QUERIES[:6]), max_length=20)
    catalog_ids: list[str] = Field(default_factory=list, max_length=10)
    results_per_query: int = Field(20, ge=1, le=100)
    min_score: float = Field(35.0, ge=0, le=100)
    max_candidates: int = Field(300, ge=1, le=2000)


class PortalDiscoveryRequest(BaseModel):
    urls: list[str] = Field(default_factory=list, max_length=25)
    from_source_candidates: bool = True
    min_source_score: float = Field(45.0, ge=0, le=100)
    max_seeds: int = Field(50, ge=1, le=250)


class RefreshRequest(BaseModel):
    execute: bool = False
    source_ids: list[str] = Field(default_factory=list, max_length=25)
    max_sources: int = Field(10, ge=0, le=50)


class ResearchRequest(BaseModel):
    execute: bool = False
    max_steps: int = Field(10, ge=0, le=100)
    max_planning_cost: float = Field(125.0, ge=0, le=10000)
    min_economic_score: float = Field(1.0, ge=0, le=100)
    min_expected_case_value: float = Field(0.0, ge=0)


class PortfolioCycleRequest(BaseModel):
    execute_sources: bool = False
    execute_research: bool = False
    max_source_refreshes: int = Field(10, ge=0, le=50)
    max_research_steps: int = Field(10, ge=0, le=100)
    max_planning_cost: float = Field(125.0, ge=0, le=10000)


class CandidateStateRequest(BaseModel):
    state: Literal["discovered", "approved", "rejected", "watch", "archived"]


class AnomalyStateRequest(BaseModel):
    state: Literal["open", "dismissed", "confirmed", "stale"]


@router.get("/status", operation_id="getVestraStatus")
def agent_status(_: None = Depends(require_agent_key)):
    database = _db()
    return {
        "service": "Vestra Intel / Forgotten Asset Intelligence",
        "version": "1.5.0",
        "mode": "gpt_action_api",
        "boundaries": {
            "automatic": ["public-data analysis", "entity resolution", "scoring", "read-only whitelisted research"],
            "human_gated": ["claimant outreach", "assignments", "asset purchases", "claims", "legal entitlement decisions"],
        },
        "portfolio": portfolio_snapshot(database, limit=5),
    }


@router.get("/portfolio", operation_id="getVestraPortfolio")
def agent_portfolio(
    limit: int = Query(10, ge=1, le=50),
    min_expected_value: float = Query(0, ge=0),
    _: None = Depends(require_agent_key),
):
    return portfolio_snapshot(_db(), limit=limit, min_expected_value=min_expected_value)


@router.get("/opportunities", operation_id="listVestraOpportunities")
def agent_opportunities(
    limit: int = Query(25, ge=1, le=100),
    min_score: float = Query(0, ge=0, le=100),
    lane: str | None = None,
    jurisdiction: str | None = None,
    _: None = Depends(require_agent_key),
):
    return [
        dict(r)
        for r in _db().list_commercial_assessments(
            limit=limit, min_score=min_score, lane=lane, jurisdiction=jurisdiction
        )
    ]


@router.get("/cases/{anomaly_id}", operation_id="getVestraCase")
def agent_case(anomaly_id: int, _: None = Depends(require_agent_key)):
    result = case_snapshot(_db(), anomaly_id)
    if result is None:
        raise HTTPException(status_code=404, detail="case not found")
    return result


@router.get("/review-ready", operation_id="listReviewReadyCases")
def agent_review_ready(limit: int = Query(25, ge=1, le=100), _: None = Depends(require_agent_key)):
    return [dict(r) for r in _db().list_case_resolutions(limit=limit, status="review_ready")]


@router.get("/source-candidates", operation_id="listSourceCandidates")
def agent_source_candidates(
    limit: int = Query(25, ge=1, le=100),
    min_score: float = Query(0, ge=0, le=100),
    state: str | None = "discovered",
    _: None = Depends(require_agent_key),
):
    return [dict(r) for r in _db().list_source_candidates(limit=limit, min_score=min_score, state=state)]


@router.get("/portal-candidates", operation_id="listPortalCandidates")
def agent_portal_candidates(
    limit: int = Query(25, ge=1, le=100),
    min_score: float = Query(0, ge=0, le=100),
    state: str | None = "discovered",
    _: None = Depends(require_agent_key),
):
    return [dict(r) for r in _db().list_portal_candidates(limit=limit, min_score=min_score, state=state)]


@router.post("/analyze", operation_id="runVestraAnalysis")
def agent_analyze(body: AnalyzeRequest, _: None = Depends(require_agent_key)):
    return run_analysis(_db(), fuzzy=body.fuzzy)


@router.post("/discover-sources", operation_id="discoverAssetDataSources")
def agent_discover_sources(body: SourceDiscoveryRequest, _: None = Depends(require_agent_key)):
    return discover_sources(
        _db(),
        queries=tuple(body.queries),
        catalog_ids=tuple(body.catalog_ids),
        results_per_query=body.results_per_query,
        min_score=body.min_score,
        max_candidates=body.max_candidates,
    )


@router.post("/discover-portals", operation_id="discoverDataPortals")
def agent_discover_portals(body: PortalDiscoveryRequest, _: None = Depends(require_agent_key)):
    return discover_portal_candidates(
        _db(),
        urls=tuple(body.urls),
        from_source_candidates=body.from_source_candidates,
        min_source_score=body.min_source_score,
        max_seeds=body.max_seeds,
    )


@router.post("/refresh", operation_id="refreshVestraSources")
def agent_refresh(body: RefreshRequest, _: None = Depends(require_agent_key)):
    return refresh_sources(
        _db(), execute=body.execute, source_ids=tuple(body.source_ids), max_sources=body.max_sources
    )


@router.post("/research", operation_id="runVestraResearch")
def agent_research(body: ResearchRequest, _: None = Depends(require_agent_key)):
    return research_portfolio(
        _db(),
        execute=body.execute,
        max_steps=body.max_steps,
        max_planning_cost=body.max_planning_cost,
        min_economic_score=body.min_economic_score,
        min_expected_case_value=body.min_expected_case_value,
    )


@router.post("/portfolio-cycle", operation_id="runVestraPortfolioCycle")
def agent_portfolio_cycle(body: PortfolioCycleRequest, _: None = Depends(require_agent_key)):
    return run_portfolio_cycle(
        _db(),
        execute_sources=body.execute_sources,
        execute_research=body.execute_research,
        max_source_refreshes=body.max_source_refreshes,
        max_research_steps=body.max_research_steps,
        max_planning_cost=body.max_planning_cost,
    )


@router.post("/source-candidates/{candidate_id}/state", operation_id="setSourceCandidateState")
def agent_set_source_candidate_state(
    candidate_id: int, body: CandidateStateRequest, _: None = Depends(require_agent_key)
):
    if not _db().set_source_candidate_state(candidate_id, body.state):
        raise HTTPException(status_code=404, detail="source candidate not found")
    return {"candidate_id": candidate_id, "state": body.state}


@router.post("/portal-candidates/{candidate_id}/state", operation_id="setPortalCandidateState")
def agent_set_portal_candidate_state(
    candidate_id: int, body: CandidateStateRequest, _: None = Depends(require_agent_key)
):
    if not _db().set_portal_candidate_state(candidate_id, body.state):
        raise HTTPException(status_code=404, detail="portal candidate not found")
    return {"candidate_id": candidate_id, "state": body.state}


@router.post("/anomalies/{anomaly_id}/state", operation_id="setAnomalyState")
def agent_set_anomaly_state(
    anomaly_id: int, body: AnomalyStateRequest, _: None = Depends(require_agent_key)
):
    if not _db().set_anomaly_state(anomaly_id, body.state):
        raise HTTPException(status_code=404, detail="anomaly not found")
    return {"anomaly_id": anomaly_id, "state": body.state}
