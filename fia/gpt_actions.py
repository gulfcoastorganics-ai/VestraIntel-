from __future__ import annotations

from typing import Any


def build_action_schema(base_url: str) -> dict[str, Any]:
    base = base_url.rstrip("/")
    bearer = [{"AgentBearer": []}]
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Vestra Intel GPT Actions",
            "version": "1.5.0",
            "description": (
                "Conversational control API for Forgotten Asset Intelligence. "
                "Discovery, scoring, public-data research, and local analyst-state changes only. "
                "Claimant outreach, assignments, purchases, filings, and legal entitlement decisions remain human-gated."
            ),
        },
        "servers": [{"url": base}],
        "components": {
            "securitySchemes": {
                "AgentBearer": {"type": "http", "scheme": "bearer", "bearerFormat": "API key"}
            },
            "schemas": {
                "AnalyzeRequest": {
                    "type": "object",
                    "properties": {"fuzzy": {"type": "boolean", "default": True}},
                },
                "SourceDiscoveryRequest": {
                    "type": "object",
                    "properties": {
                        "queries": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
                        "catalog_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
                        "results_per_query": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                        "min_score": {"type": "number", "minimum": 0, "maximum": 100, "default": 35},
                        "max_candidates": {"type": "integer", "minimum": 1, "maximum": 2000, "default": 300},
                    },
                },
                "PortalDiscoveryRequest": {
                    "type": "object",
                    "properties": {
                        "urls": {"type": "array", "items": {"type": "string", "format": "uri"}, "maxItems": 25},
                        "from_source_candidates": {"type": "boolean", "default": True},
                        "min_source_score": {"type": "number", "minimum": 0, "maximum": 100, "default": 45},
                        "max_seeds": {"type": "integer", "minimum": 1, "maximum": 250, "default": 50},
                    },
                },
                "RefreshRequest": {
                    "type": "object",
                    "properties": {
                        "execute": {
                            "type": "boolean",
                            "default": False,
                            "description": "False previews due source refreshes. True performs approved public/read-only source calls and writes resulting records locally.",
                        },
                        "source_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 25},
                        "max_sources": {"type": "integer", "minimum": 0, "maximum": 50, "default": 10},
                    },
                },
                "ResearchRequest": {
                    "type": "object",
                    "properties": {
                        "execute": {
                            "type": "boolean",
                            "default": False,
                            "description": "False previews the best permitted research task. True executes only FIA's whitelisted read-only research actions.",
                        },
                        "max_steps": {"type": "integer", "minimum": 0, "maximum": 100, "default": 10},
                        "max_planning_cost": {"type": "number", "minimum": 0, "maximum": 10000, "default": 125},
                        "min_economic_score": {"type": "number", "minimum": 0, "maximum": 100, "default": 1},
                        "min_expected_case_value": {"type": "number", "minimum": 0, "default": 0},
                    },
                },
                "PortfolioCycleRequest": {
                    "type": "object",
                    "properties": {
                        "execute_sources": {"type": "boolean", "default": False},
                        "execute_research": {"type": "boolean", "default": False},
                        "max_source_refreshes": {"type": "integer", "minimum": 0, "maximum": 50, "default": 10},
                        "max_research_steps": {"type": "integer", "minimum": 0, "maximum": 100, "default": 10},
                        "max_planning_cost": {"type": "number", "minimum": 0, "maximum": 10000, "default": 125},
                    },
                },
                "CandidateStateRequest": {
                    "type": "object",
                    "required": ["state"],
                    "properties": {
                        "state": {"type": "string", "enum": ["discovered", "approved", "rejected", "watch", "archived"]}
                    },
                },
                "AnomalyStateRequest": {
                    "type": "object",
                    "required": ["state"],
                    "properties": {"state": {"type": "string", "enum": ["open", "dismissed", "confirmed", "stale"]}},
                },
            },
        },
        "security": bearer,
        "paths": {
            "/agent/status": {
                "get": {
                    "operationId": "getVestraStatus",
                    "summary": "Get Vestra Intel service status and a compact portfolio snapshot.",
                    "responses": {"200": {"description": "Service status"}},
                }
            },
            "/agent/portfolio": {
                "get": {
                    "operationId": "getVestraPortfolio",
                    "summary": "Get top economic cases, review-ready cases, anomalies, routes, source health, and discovery candidates.",
                    "parameters": [
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}},
                        {"name": "min_expected_value", "in": "query", "schema": {"type": "number", "minimum": 0, "default": 0}},
                    ],
                    "responses": {"200": {"description": "Portfolio snapshot"}},
                }
            },
            "/agent/opportunities": {
                "get": {
                    "operationId": "listVestraOpportunities",
                    "summary": "List ranked commercial opportunities with optional lane and jurisdiction filters.",
                    "parameters": [
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25}},
                        {"name": "min_score", "in": "query", "schema": {"type": "number", "minimum": 0, "maximum": 100, "default": 0}},
                        {"name": "lane", "in": "query", "schema": {"type": "string"}},
                        {"name": "jurisdiction", "in": "query", "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "Ranked opportunities"}},
                }
            },
            "/agent/cases/{anomaly_id}": {
                "get": {
                    "operationId": "getVestraCase",
                    "summary": "Get one complete case: anomaly evidence, resolution state, economics, route, and next task.",
                    "parameters": [{"name": "anomaly_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                    "responses": {"200": {"description": "Case detail"}, "404": {"description": "Case not found"}},
                }
            },
            "/agent/review-ready": {
                "get": {
                    "operationId": "listReviewReadyCases",
                    "summary": "List cases that have completed configured automated research and are ready for human review.",
                    "parameters": [{"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25}}],
                    "responses": {"200": {"description": "Review-ready cases"}},
                }
            },
            "/agent/source-candidates": {
                "get": {
                    "operationId": "listSourceCandidates",
                    "summary": "List candidate asset datasets found in official metadata catalogs.",
                    "parameters": [
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25}},
                        {"name": "min_score", "in": "query", "schema": {"type": "number", "minimum": 0, "maximum": 100, "default": 0}},
                        {"name": "state", "in": "query", "schema": {"type": "string", "default": "discovered"}},
                    ],
                    "responses": {"200": {"description": "Source candidates"}},
                }
            },
            "/agent/portal-candidates": {
                "get": {
                    "operationId": "listPortalCandidates",
                    "summary": "List candidate data portals/connectors discovered by FIA.",
                    "parameters": [
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25}},
                        {"name": "min_score", "in": "query", "schema": {"type": "number", "minimum": 0, "maximum": 100, "default": 0}},
                        {"name": "state", "in": "query", "schema": {"type": "string", "default": "discovered"}},
                    ],
                    "responses": {"200": {"description": "Portal candidates"}},
                }
            },
            "/agent/analyze": {
                "post": {
                    "operationId": "runVestraAnalysis",
                    "summary": "Rebuild FIA's local evidence graph, economics, anomalies, routes, research plan, and cases. No external call.",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/AnalyzeRequest"}}}},
                    "responses": {"200": {"description": "Analysis statistics"}},
                }
            },
            "/agent/discover-sources": {
                "post": {
                    "operationId": "discoverAssetDataSources",
                    "summary": "Search configured official metadata catalogs for new asset/right datasets.",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/SourceDiscoveryRequest"}}}},
                    "responses": {"200": {"description": "Source-discovery run statistics"}},
                }
            },
            "/agent/discover-portals": {
                "post": {
                    "operationId": "discoverDataPortals",
                    "summary": "Fingerprint approved/candidate portal URLs with bounded read-only probes and propose connectors.",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PortalDiscoveryRequest"}}}},
                    "responses": {"200": {"description": "Portal discovery statistics"}},
                }
            },
            "/agent/refresh": {
                "post": {
                    "operationId": "refreshVestraSources",
                    "summary": "Preview or execute FIA's approved public/read-only source refreshes. Set execute=false unless the user explicitly asks for a live refresh.",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/RefreshRequest"}}}},
                    "responses": {"200": {"description": "Source-refresh result"}},
                }
            },
            "/agent/research": {
                "post": {
                    "operationId": "runVestraResearch",
                    "summary": "Preview or execute FIA's bounded whitelisted read-only research scheduler. Set execute=false unless the user explicitly asks to run research.",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ResearchRequest"}}}},
                    "responses": {"200": {"description": "Research scheduler result"}},
                }
            },
            "/agent/portfolio-cycle": {
                "post": {
                    "operationId": "runVestraPortfolioCycle",
                    "summary": "Preview or run the combined source-refresh plus read-only research cycle. Execution flags default to false.",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PortfolioCycleRequest"}}}},
                    "responses": {"200": {"description": "Portfolio-cycle result"}},
                }
            },
            "/agent/source-candidates/{candidate_id}/state": {
                "post": {
                    "operationId": "setSourceCandidateState",
                    "summary": "Change local analyst review state for a source candidate. Use only when the user explicitly asks to approve, watch, reject, archive, or reset it.",
                    "parameters": [{"name": "candidate_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/CandidateStateRequest"}}}},
                    "responses": {"200": {"description": "Updated state"}},
                }
            },
            "/agent/portal-candidates/{candidate_id}/state": {
                "post": {
                    "operationId": "setPortalCandidateState",
                    "summary": "Change local analyst review state for a portal connector candidate. Use only on explicit user instruction.",
                    "parameters": [{"name": "candidate_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/CandidateStateRequest"}}}},
                    "responses": {"200": {"description": "Updated state"}},
                }
            },
            "/agent/anomalies/{anomaly_id}/state": {
                "post": {
                    "operationId": "setAnomalyState",
                    "summary": "Record local analyst review state for an anomaly. Use only on explicit user instruction.",
                    "parameters": [{"name": "anomaly_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/AnomalyStateRequest"}}}},
                    "responses": {"200": {"description": "Updated state"}},
                }
            },
        },
    }
