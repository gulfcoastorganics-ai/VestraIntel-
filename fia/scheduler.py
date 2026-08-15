from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .anomalies import detect_anomalies
from .case_resolution import rebuild_case_resolutions
from .commercial import rebuild_commercial_assessments
from .config import load_settings
from .db import Database
from .economics import rebuild_case_economics
from .entity_resolution import rebuild_entity_graph
from .feedback import assimilate_research_results
from .research import execute_task, plan_research

# Intentionally narrow. No manual/CAPTCHA/legal/enrollment/outreach/claim/acquisition task is here.
AUTO_EXECUTABLE_TASKS = frozenset({
    "companies_house_profile",
    "companies_house_filing_history",
    "companies_house_officers",
    "companies_house_psc",
    "companies_house_insolvency",
    "companies_house_officer_appointments",
})

@dataclass(frozen=True)
class SchedulerConfig:
    max_steps: int = 20
    max_planning_cost: float = 250.0
    min_economic_score: float = 1.0
    min_expected_case_value: float = 0.0
    company_house_min_interval_seconds: float = 0.60
    dry_run: bool = True
    fuzzy: bool = True
    hourly_research_cost: float = 25.0
    default_intelligence_value: float = 250.0
    unknown_capture_rate: float = 0.05

@dataclass(frozen=True)
class SchedulerStats:
    run_id: int
    status: str
    steps_executed: int
    planning_cost_spent: float
    completed_task_ids: tuple[int, ...]
    stop_reason: str


def _refresh(db: Database, config: SchedulerConfig) -> None:
    assimilate_research_results(db)
    rebuild_entity_graph(db, fuzzy=config.fuzzy)
    rebuild_commercial_assessments(db)
    detect_anomalies(db)
    plan_research(db)
    rebuild_case_resolutions(db)
    rebuild_case_economics(
        db,
        hourly_research_cost=config.hourly_research_cost,
        default_intelligence_value=config.default_intelligence_value,
        unknown_capture_rate=config.unknown_capture_rate,
    )


def _credential_available(task: dict[str, Any]) -> tuple[bool, str | None]:
    settings = load_settings()
    task_type = str(task.get("task_type") or "")
    if task_type in AUTO_EXECUTABLE_TASKS and not settings.companies_house_api_key:
        return False, "COMPANIES_HOUSE_API_KEY is required for the selected read-only Companies House task"
    return True, None


def _classify_stop(db: Database, *, min_economic_score: float, min_expected_case_value: float) -> tuple[str, str]:
    cases = [dict(r) for r in db.list_case_economics(limit=1000, min_expected_value=min_expected_case_value)]
    if not cases:
        return "economically_exhausted", "No active economic cases meet the scheduler threshold."
    if all(str(c.get("resolution_status")) == "review_ready" for c in cases):
        return "review_ready", "All active cases meeting the threshold are ready for human review."

    access_blocked = False
    human_gate = False
    economically_live = False
    for case in cases:
        if float(case.get("expected_case_value") or 0.0) < min_expected_case_value:
            continue
        task = db.next_economic_task(int(case["anomaly_id"]))
        if not task:
            if str(case.get("resolution_status")) == "review_ready":
                continue
            human_gate = True
            continue
        if float(task.get("best_task_economic_score") or 0.0) < min_economic_score:
            continue
        economically_live = True
        if str(task.get("task_type")) not in AUTO_EXECUTABLE_TASKS:
            human_gate = True
            continue
        ok, _ = _credential_available(task)
        if not ok:
            access_blocked = True

    if access_blocked:
        return "access_blocked", "The highest-value permitted automatic lookup requires a configured credential."
    if human_gate and economically_live:
        return "human_gate", "Remaining economically useful research requires manual, legal, CAPTCHA, enrollment, or other human-gated work."
    return "economically_exhausted", "No economically eligible automatic research task remains."


def _candidate_tasks(db: Database, config: SchedulerConfig, spent: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case_row in db.list_case_economics(limit=1000, min_expected_value=config.min_expected_case_value):
        case = dict(case_row)
        if str(case.get("resolution_status")) == "review_ready":
            continue
        task = db.next_economic_task(int(case["anomaly_id"]))
        if not task:
            continue
        task = dict(task)
        if str(task.get("state")) not in {"pending", "in_progress"}:
            continue
        if str(task.get("task_type")) not in AUTO_EXECUTABLE_TASKS:
            continue
        score = float(task.get("best_task_economic_score") or 0.0)
        cost = float(task.get("research_cost") or 0.0)
        if score < config.min_economic_score:
            continue
        if spent + cost > config.max_planning_cost:
            continue
        ok, reason = _credential_available(task)
        task["credential_available"] = ok
        task["credential_block_reason"] = reason
        rows.append(task)
    rows.sort(
        key=lambda x: (
            1 if x.get("credential_available") else 0,
            float(x.get("best_task_economic_score") or 0.0),
            float(x.get("expected_case_value") or 0.0),
        ),
        reverse=True,
    )
    return rows


def run_scheduler(
    db: Database,
    config: SchedulerConfig | None = None,
    *,
    executor: Callable[[Database, int], dict[str, Any]] = execute_task,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> SchedulerStats:
    """Run a bounded read-only research loop.

    The scheduler can only execute task types in AUTO_EXECUTABLE_TASKS. It never performs
    claimant outreach, signs agreements, submits claims, purchases rights, bypasses CAPTCHAs,
    or makes legal entitlement determinations.
    """
    config = config or SchedulerConfig()
    if config.max_steps < 0 or config.max_planning_cost < 0:
        raise ValueError("Scheduler limits must be non-negative")

    db.init()
    _refresh(db, config)
    run_id = db.begin_scheduler_run({
        "max_steps": config.max_steps,
        "max_planning_cost": config.max_planning_cost,
        "min_economic_score": config.min_economic_score,
        "min_expected_case_value": config.min_expected_case_value,
        "company_house_min_interval_seconds": config.company_house_min_interval_seconds,
        "dry_run": config.dry_run,
        "hourly_research_cost": config.hourly_research_cost,
        "default_intelligence_value": config.default_intelligence_value,
        "unknown_capture_rate": config.unknown_capture_rate,
    })

    spent = 0.0
    completed: list[int] = []
    status = "running"
    stop_reason = ""
    last_ch_call = 0.0

    try:
        for step_index in range(1, config.max_steps + 1):
            candidates = _candidate_tasks(db, config, spent)
            executable = [c for c in candidates if c.get("credential_available")]
            if not executable:
                status, stop_reason = _classify_stop(
                    db,
                    min_economic_score=config.min_economic_score,
                    min_expected_case_value=config.min_expected_case_value,
                )
                break

            task = executable[0]
            task_id = int(task["id"])
            anomaly_id = int(task["anomaly_id"])
            cost = float(task.get("research_cost") or 0.0)
            db.add_scheduler_step(
                run_id=run_id,
                step_index=step_index,
                anomaly_id=anomaly_id,
                task_id=task_id,
                task_type=str(task["task_type"]),
                economic_score=float(task.get("best_task_economic_score") or 0.0),
                expected_case_value=float(task.get("expected_case_value") or 0.0),
                planning_cost=cost,
                state="selected" if config.dry_run else "executing",
                detail={"dry_run": config.dry_run},
            )

            if config.dry_run:
                status = "dry_run_complete"
                stop_reason = "Dry run selected the highest-value permitted task without calling an external source."
                break

            db.set_research_task_state(task_id, "in_progress")
            try:
                if str(task["task_type"]).startswith("companies_house_"):
                    elapsed = time.monotonic() - last_ch_call if last_ch_call else config.company_house_min_interval_seconds
                    wait = max(0.0, config.company_house_min_interval_seconds - elapsed)
                    if wait:
                        sleep_fn(wait)
                    result = executor(db, task_id)
                    last_ch_call = time.monotonic()
                else:
                    result = executor(db, task_id)
            except Exception as exc:
                # Failed API calls remain auditable and do not consume a false "completed" state.
                db.set_research_task_state(task_id, "blocked")
                db.finish_scheduler_step(
                    run_id=run_id,
                    step_index=step_index,
                    state="blocked",
                    detail={"error_type": type(exc).__name__, "error": str(exc)},
                )
                status = "access_blocked"
                stop_reason = f"Automatic research stopped after {type(exc).__name__}: {exc}"
                break

            spent += cost
            completed.append(task_id)
            db.finish_scheduler_step(
                run_id=run_id,
                step_index=step_index,
                state="completed",
                detail={"result_summary": _summarize_result(result)},
            )
            _refresh(db, config)
        else:
            status = "max_steps_reached"
            stop_reason = f"Scheduler reached its configured maximum of {config.max_steps} steps."

        if not stop_reason:
            status, stop_reason = _classify_stop(
                db,
                min_economic_score=config.min_economic_score,
                min_expected_case_value=config.min_expected_case_value,
            )
    except Exception as exc:
        status = "error"
        stop_reason = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        db.finish_scheduler_run(
            run_id,
            status=status,
            planning_cost_spent=spent,
            completed_tasks=len(completed),
            stop_reason=stop_reason,
        )

    return SchedulerStats(
        run_id=run_id,
        status=status,
        steps_executed=len(completed),
        planning_cost_spent=round(spent, 2),
        completed_task_ids=tuple(completed),
        stop_reason=stop_reason,
    )


def _summarize_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"type": type(result).__name__}
    summary: dict[str, Any] = {"keys": sorted(result.keys())[:20]}
    for key in ("company_number", "company_name", "company_status", "not_found", "total_results", "total_count"):
        if key in result:
            summary[key] = result[key]
    if isinstance(result.get("items"), list):
        summary["item_count"] = len(result["items"])
    return summary
