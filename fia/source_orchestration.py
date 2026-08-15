from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
import calendar
import json

import httpx

from .config import load_settings
from .db import Database, UpsertStats
from .sources.california_unclaimed import CaliforniaUnclaimedProperty
from .sources.companies_house import CompaniesHouseStreamClient, normalize_stream_dissolutions
from .sources.flc_notices import FLCLicenseNotices
from .sources.uk_unclaimed_estates import UKUnclaimedEstates
from .sources.uspto_og import USPTOOfficialGazette


@dataclass(frozen=True)
class SourcePolicy:
    source_id: str
    mode: str
    cadence_label: str
    min_interval_hours: float
    preferred_weekday: int | None = None  # Monday=0
    credential: str | None = None
    enabled: bool = True


SOURCE_POLICIES: tuple[SourcePolicy, ...] = (
    SourcePolicy("ca_unclaimed_property", "weekly_bulk", "weekly_thursday", 24 * 6, preferred_weekday=3),
    SourcePolicy("companies_house_stream", "bounded_stream", "hourly_catchup", 1, credential="companies_house_stream_key"),
    SourcePolicy("flc_license_notices", "public_poll", "12_hour_poll", 12),
    SourcePolicy("uk_unclaimed_estates", "public_poll", "24_hour_poll", 24),
    SourcePolicy("uspto_official_gazette", "weekly_issue", "weekly_tuesday", 24 * 6, preferred_weekday=1),
    SourcePolicy("uspto_open_data", "authenticated_api", "credential_gated", 24 * 7, credential="uspto_api_key", enabled=False),
    SourcePolicy("soundexchange_unclaimed", "manual_public_status_import", "on_demand", 24, enabled=False),
    SourcePolicy("mlc_data", "authorized_file_or_api", "enrollment_gated", 24, enabled=False),
    SourcePolicy("treasury_unpaid_checks_foia", "foia_or_agency_file", "on_demand", 24, enabled=False),
    SourcePolicy("sam_contract_opportunities", "public_file_import", "on_demand", 24, enabled=False),
    SourcePolicy("us_bankruptcy_unclaimed", "manual_court_export", "on_demand", 24, enabled=False),
    SourcePolicy("official_surplus_funds", "official_file_import", "on_demand", 24, enabled=False),
)


@dataclass(frozen=True)
class SourceOrchestratorConfig:
    dry_run: bool = True
    source_ids: tuple[str, ...] = ()
    max_sources: int = 10
    california_bucket: str = "500_plus"
    companies_house_stream_max_events: int = 100
    retry_base_minutes: int = 15
    retry_max_hours: int = 24


@dataclass(frozen=True)
class SourceOrchestratorStats:
    status: str
    due_sources: tuple[str, ...]
    completed_sources: tuple[str, ...]
    blocked_sources: tuple[str, ...]
    failed_sources: tuple[str, ...]
    total_records: int
    new_records: int
    changed_records: int


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _next_weekday_after(now: datetime, weekday: int) -> datetime:
    days = (weekday - now.weekday()) % 7
    if days == 0:
        days = 7
    return now + timedelta(days=days)


def next_due_after_success(policy: SourcePolicy, now: datetime) -> datetime:
    if policy.preferred_weekday is not None:
        return _next_weekday_after(now, policy.preferred_weekday)
    return now + timedelta(hours=policy.min_interval_hours)


def retry_due(now: datetime, failures: int, config: SourceOrchestratorConfig) -> datetime:
    exponent = max(0, failures)
    minutes = min(config.retry_base_minutes * (2 ** exponent), config.retry_max_hours * 60)
    return now + timedelta(minutes=minutes)


def _credential_status(policy: SourcePolicy) -> tuple[bool, str | None]:
    if not policy.credential:
        return True, None
    settings = load_settings()
    if getattr(settings, policy.credential, None):
        return True, None
    env_name = {
        "companies_house_stream_key": "COMPANIES_HOUSE_STREAM_KEY",
        "uspto_api_key": "USPTO_API_KEY",
    }.get(policy.credential, policy.credential.upper())
    return False, f"{env_name} is required"


def ensure_source_states(db: Database) -> None:
    for policy in SOURCE_POLICIES:
        db.ensure_source_sync_state(
            policy.source_id, mode=policy.mode, cadence_label=policy.cadence_label, enabled=policy.enabled
        )


def is_due(db: Database, policy: SourcePolicy, *, now: datetime | None = None) -> bool:
    now = now or _utcnow()
    state = db.source_sync_state(policy.source_id)
    if state is None or not bool(state.get("enabled", 1)):
        return False
    next_due = _parse_dt(state.get("next_due_at"))
    if next_due is not None:
        return next_due <= now
    last_success = _parse_dt(state.get("last_success_at"))
    if last_success is None:
        return True
    return (now - last_success) >= timedelta(hours=policy.min_interval_hours)


def _current_uspto_gazette_url(now: datetime) -> str:
    # USPTO patent OG is published weekly on Tuesday. Week 1 is the first Tuesday of the year.
    year_start = datetime(now.year, 1, 1, tzinfo=timezone.utc)
    days_to_tuesday = (calendar.TUESDAY - year_start.weekday()) % 7
    first_tuesday = year_start + timedelta(days=days_to_tuesday)
    effective = now
    days_since_tuesday = (effective.weekday() - calendar.TUESDAY) % 7
    latest_tuesday = (effective - timedelta(days=days_since_tuesday)).replace(hour=0, minute=0, second=0, microsecond=0)
    if latest_tuesday < first_tuesday:
        latest_tuesday = first_tuesday
    week = ((latest_tuesday.date() - first_tuesday.date()).days // 7) + 1
    return f"https://patentsgazette.uspto.gov/week{week:02d}/OG/TOC.htm"


def _default_execute(db: Database, policy: SourcePolicy, config: SourceOrchestratorConfig) -> tuple[UpsertStats, str | None, dict[str, Any]]:
    settings = load_settings()
    headers = {"User-Agent": settings.user_agent}
    with httpx.Client(timeout=45, headers=headers) as client:
        if policy.source_id == "ca_unclaimed_property":
            stats = db.upsert_with_stats(CaliforniaUnclaimedProperty(client).fetch(bucket=config.california_bucket))
            return stats, None, {"bucket": config.california_bucket}
        if policy.source_id == "flc_license_notices":
            stats = db.upsert_with_stats(FLCLicenseNotices(client).fetch())
            return stats, None, {}
        if policy.source_id == "uk_unclaimed_estates":
            stats = db.upsert_with_stats(UKUnclaimedEstates(client).fetch())
            return stats, None, {}
        if policy.source_id == "uspto_official_gazette":
            url = _current_uspto_gazette_url(_utcnow())
            stats = db.upsert_with_stats(USPTOOfficialGazette(client, url=url).fetch())
            return stats, None, {"issue_url": url}
        if policy.source_id == "companies_house_stream":
            if not settings.companies_house_stream_key:
                raise RuntimeError("COMPANIES_HOUSE_STREAM_KEY is required")
            state = db.source_sync_state(policy.source_id) or {}
            before = str(state.get("cursor")) if state.get("cursor") else None
            events, cursor = CompaniesHouseStreamClient(settings.companies_house_stream_key, client).company_events(
                timepoint=before, max_events=config.companies_house_stream_max_events
            )
            stats = db.upsert_with_stats(normalize_stream_dissolutions(events))
            return stats, cursor, {"events_read": len(events), "cursor_before": before}
    raise RuntimeError(f"No automatic source executor implemented for {policy.source_id}")


def run_source_orchestrator(
    db: Database,
    config: SourceOrchestratorConfig | None = None,
    *,
    now: datetime | None = None,
    executor: Callable[[Database, SourcePolicy, SourceOrchestratorConfig], tuple[UpsertStats, str | None, dict[str, Any]]] = _default_execute,
) -> SourceOrchestratorStats:
    config = config or SourceOrchestratorConfig()
    now = now or _utcnow()
    if config.max_sources < 0:
        raise ValueError("max_sources must be non-negative")
    ensure_source_states(db)
    selected = [p for p in SOURCE_POLICIES if p.enabled]
    if config.source_ids:
        wanted = set(config.source_ids)
        selected = [p for p in selected if p.source_id in wanted]
    due = [p for p in selected if is_due(db, p, now=now)][:config.max_sources]
    if config.dry_run:
        return SourceOrchestratorStats(
            status="dry_run_complete", due_sources=tuple(p.source_id for p in due), completed_sources=(),
            blocked_sources=(), failed_sources=(), total_records=0, new_records=0, changed_records=0,
        )

    completed: list[str] = []
    blocked: list[str] = []
    failed: list[str] = []
    total = new = changed = 0
    for policy in due:
        state = db.source_sync_state(policy.source_id) or {}
        cursor_before = str(state.get("cursor")) if state.get("cursor") else None
        event_id = db.begin_source_sync_event(policy.source_id, cursor_before=cursor_before, detail={"mode": policy.mode})
        ok, reason = _credential_status(policy)
        if not ok:
            blocked.append(policy.source_id)
            next_due = retry_due(now, int(state.get("consecutive_failures") or 0), config)
            db.finish_source_sync_event(
                event_id, status="blocked", next_due_at=next_due.isoformat(), error=reason,
                detail={"credential_required": policy.credential},
            )
            continue
        try:
            stats, cursor_after, detail = executor(db, policy, config)
            next_due = next_due_after_success(policy, now)
            db.finish_source_sync_event(
                event_id, status="completed", record_count=stats.total, new_count=stats.new,
                changed_count=stats.changed, unchanged_count=stats.unchanged, cursor_after=cursor_after,
                next_due_at=next_due.isoformat(), detail=detail,
            )
            completed.append(policy.source_id)
            total += stats.total
            new += stats.new
            changed += stats.changed
        except Exception as exc:
            failed.append(policy.source_id)
            next_due = retry_due(now, int(state.get("consecutive_failures") or 0), config)
            db.finish_source_sync_event(
                event_id, status="failed", next_due_at=next_due.isoformat(),
                error=f"{type(exc).__name__}: {exc}", detail={"mode": policy.mode},
            )
    status = "completed"
    if failed:
        status = "partial_failure"
    elif blocked and not completed:
        status = "access_blocked"
    return SourceOrchestratorStats(
        status=status, due_sources=tuple(p.source_id for p in due), completed_sources=tuple(completed),
        blocked_sources=tuple(blocked), failed_sources=tuple(failed), total_records=total,
        new_records=new, changed_records=changed,
    )
