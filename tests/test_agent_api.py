from __future__ import annotations

from fastapi.testclient import TestClient

from fia.api import app


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("FIA_DB_PATH", str(tmp_path / "fia.sqlite3"))
    monkeypatch.setenv("FIA_AGENT_API_KEY", "test-agent-key")
    return TestClient(app)


def test_agent_api_requires_bearer_key(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    assert client.get("/health").status_code == 200
    assert client.get("/agent/status").status_code == 401
    assert client.get("/api/opportunities").status_code == 401

    headers = {"Authorization": "Bearer test-agent-key"}
    response = client.get("/agent/status", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "1.5.0"
    assert body["mode"] == "gpt_action_api"


def test_gpt_action_schema_is_public_and_uses_configured_origin(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setenv("FIA_PUBLIC_BASE_URL", "https://vestra.example.test")
    response = client.get("/gpt/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["openapi"] == "3.1.0"
    assert schema["servers"] == [{"url": "https://vestra.example.test"}]
    assert "/agent/portfolio" in schema["paths"]
    assert "/agent/portfolio-cycle" in schema["paths"]
    assert schema["components"]["securitySchemes"]["AgentBearer"]["scheme"] == "bearer"


def test_agent_analysis_and_portfolio_on_empty_database(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer test-agent-key"}

    response = client.post("/agent/analyze", headers=headers, json={"fuzzy": False})
    assert response.status_code == 200
    result = response.json()
    assert result["anomalies"] == 0
    assert result["economic_cases"] == 0

    response = client.get("/agent/portfolio", headers=headers)
    assert response.status_code == 200
    result = response.json()
    assert result["economic_cases"] == []
    assert result["review_ready"] == []


def test_agent_research_defaults_to_dry_run(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer test-agent-key"}
    response = client.post("/agent/research", headers=headers, json={})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"economically_exhausted", "review_ready", "human_gate", "access_blocked", "dry_run_complete"}
    assert body["steps_executed"] == 0


def test_privacy_policy_is_public(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    response = client.get("/privacy")
    assert response.status_code == 200
    assert "Vestra Intel Privacy Policy" in response.text


def test_gpt_schema_cli_command_is_registered():
    from typer.testing import CliRunner
    from fia.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["gpt-schema", "--base-url", "https://vestra.example.test"])
    assert result.exit_code == 0
    body = __import__("json").loads(result.stdout)
    assert body["servers"] == [{"url": "https://vestra.example.test"}]
