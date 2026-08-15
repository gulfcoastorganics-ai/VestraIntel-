from __future__ import annotations

import json
from pathlib import Path

import pytest

from fia.db import Database
from fia.scheduler import AUTO_EXECUTABLE_TASKS, SchedulerConfig, run_scheduler


def _seed_scheduler_case(db: Database) -> tuple[int, int]:
    db.init()
    now = "2026-08-14T20:00:00+00:00"
    with db.connect() as conn:
        conn.execute("""INSERT INTO anomaly_findings(
            fingerprint,rule_id,anomaly_type,title,summary,entity_id,primary_opportunity_id,
            confidence,severity_score,commercial_score,actionability_score,evidence_json,block_json,
            next_action_json,opportunity_ids_json,source_ids_json,state,first_detected_at,last_detected_at
        ) VALUES('sched-a','r','identity_resolution_gap','Test case','Synthetic',NULL,NULL,
          0.9,80,80,75,'[]','[]','[]','[]','[\"companies_house\"]','open',?,?)""", (now,now))
        anomaly_id = int(conn.execute("SELECT id FROM anomaly_findings WHERE fingerprint='sched-a'").fetchone()[0])
        conn.execute("""INSERT INTO research_tasks(
          fingerprint,anomaly_id,entity_id,opportunity_id,task_type,title,rationale,target_type,target_value,
          expected_relation_type,source_id,source_url,access_mode,estimated_effort,expected_uplift,confidence,
          priority_score,resolves_blockers_json,prerequisites_json,block_json,params_json,state,result_json,
          first_planned_at,last_planned_at,completed_at
        ) VALUES('sched-task',?,NULL,NULL,'companies_house_profile','Profile','Synthetic','company_number','01234567',
          'official_company_profile','companies_house','https://example.test','api_key','low',20,0.9,90,'[]','[]','[]',
          '{\"company_number\":\"01234567\"}','pending',NULL,?,?,NULL)""", (anomaly_id,now,now))
        task_id = int(conn.execute("SELECT id FROM research_tasks WHERE fingerprint='sched-task'").fetchone()[0])
        conn.execute("""INSERT INTO case_resolution_states(
          anomaly_id,target_state,resolution_status,resolution_score,evidence_score,budget_total,budget_spent,budget_remaining,
          next_task_id,next_task_evi,satisfied_conditions_json,unresolved_conditions_json,hard_gates_json,updated_at
        ) VALUES(?, 'human_review','researching',40,50,100,0,100,?,75,'[]','[\"identity_corroborated\"]','[]',?)""", (anomaly_id,task_id,now))
        conn.execute("""INSERT INTO case_task_priorities(anomaly_id,task_id,evi_score,execution_cost,rank,eligible,rationale_json,updated_at)
          VALUES(?,?,75,6,1,1,'{\"condition_coverage\":[\"identity_corroborated\"]}',?)""", (anomaly_id,task_id,now))
        conn.execute("""INSERT INTO case_economic_states(
          anomaly_id,lane,economic_status,revenue_reference,currency,revenue_basis,viability_probability,time_to_value_days,
          time_discount,regulatory_factor,expected_case_value,recommended_research_budget,best_task_id,best_task_economic_score,
          assumptions_json,updated_at
        ) VALUES(?,'intelligence_sale','economically_ranked',250,'USD','planning',0.7,14,0.68,1,119,100,?,88,'{}',?)""", (anomaly_id,task_id,now))
        conn.execute("""INSERT INTO case_task_economics(
          anomaly_id,task_id,resolve_probability,research_cost,time_discount,expected_incremental_value,economic_score,eligible,rationale_json,updated_at
        ) VALUES(?,?,0.8,8.75,0.68,95,88,1,'{}',?)""", (anomaly_id,task_id,now))
        conn.commit()
    return anomaly_id, task_id


def test_auto_executable_boundary_is_narrow():
    assert "court_record_verification" not in AUTO_EXECUTABLE_TASKS
    assert "successor_chain_research" not in AUTO_EXECUTABLE_TASKS
    assert "companies_house_profile" in AUTO_EXECUTABLE_TASKS


def test_scheduler_dry_run_records_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db=Database(tmp_path/'fia.sqlite3')
    anomaly_id, task_id = _seed_scheduler_case(db)
    # Keep seeded economics stable for this unit test rather than rebuilding source-derived cases.
    monkeypatch.setattr('fia.scheduler._refresh', lambda *args, **kwargs: None)
    monkeypatch.setattr('fia.scheduler._credential_available', lambda task: (True,None))
    stats=run_scheduler(db, SchedulerConfig(max_steps=3, dry_run=True))
    assert stats.status == 'dry_run_complete'
    detail=db.scheduler_run(stats.run_id)
    assert detail is not None
    assert detail['steps'][0]['task_id'] == task_id
    assert detail['steps'][0]['state'] == 'selected'
    assert db.research_task_case(task_id)['state'] == 'pending'


def test_scheduler_executes_then_stops(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db=Database(tmp_path/'fia.sqlite3')
    anomaly_id, task_id = _seed_scheduler_case(db)
    monkeypatch.setattr('fia.scheduler._refresh', lambda *args, **kwargs: None)
    monkeypatch.setattr('fia.scheduler._credential_available', lambda task: (True,None))
    calls=[]
    def fake_executor(database: Database, selected_task_id: int):
        calls.append(selected_task_id)
        database.complete_research_task(selected_task_id, result={'company_number':'01234567','company_status':'dissolved'})
        # Remove it from economic selection so the next iteration terminates.
        with database.connect() as conn:
            conn.execute('UPDATE case_economic_states SET best_task_id=NULL,best_task_economic_score=NULL WHERE anomaly_id=?',(anomaly_id,))
            conn.commit()
        return {'company_number':'01234567','company_status':'dissolved'}
    stats=run_scheduler(db, SchedulerConfig(max_steps=3, dry_run=False, company_house_min_interval_seconds=0), executor=fake_executor, sleep_fn=lambda _:None)
    assert calls == [task_id]
    assert stats.steps_executed == 1
    assert stats.planning_cost_spent == 8.75
    assert db.research_task_case(task_id)['state'] == 'completed'
    assert db.scheduler_run(stats.run_id)['steps'][0]['state'] == 'completed'
