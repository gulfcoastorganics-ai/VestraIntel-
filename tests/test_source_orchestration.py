from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from fia.db import Database, UpsertStats
from fia.source_orchestration import (
    SOURCE_POLICIES,
    SourceOrchestratorConfig,
    ensure_source_states,
    is_due,
    retry_due,
    run_source_orchestrator,
    _current_uspto_gazette_url,
)
from fia.sources.companies_house import normalize_stream_dissolutions


def _policy(source_id: str):
    return next(p for p in SOURCE_POLICIES if p.source_id == source_id)


def test_initial_enabled_sources_are_due(tmp_path: Path):
    db=Database(tmp_path/'fia.sqlite3')
    ensure_source_states(db)
    now=datetime(2026,8,14,20,tzinfo=timezone.utc)
    assert is_due(db,_policy('ca_unclaimed_property'),now=now)
    assert is_due(db,_policy('flc_license_notices'),now=now)


def test_retry_backoff_is_bounded():
    now=datetime(2026,8,14,20,tzinfo=timezone.utc)
    cfg=SourceOrchestratorConfig(retry_base_minutes=15,retry_max_hours=24)
    assert retry_due(now,0,cfg)==now+timedelta(minutes=15)
    assert retry_due(now,20,cfg)==now+timedelta(hours=24)


def test_gazette_week_url_tracks_tuesday_issue():
    assert _current_uspto_gazette_url(datetime(2026,7,28,12,tzinfo=timezone.utc)).endswith('/week30/OG/TOC.htm')
    assert _current_uspto_gazette_url(datetime(2026,8,14,12,tzinfo=timezone.utc)).endswith('/week32/OG/TOC.htm')


def test_dry_run_does_not_create_events(tmp_path: Path):
    db=Database(tmp_path/'fia.sqlite3')
    stats=run_source_orchestrator(db,SourceOrchestratorConfig(dry_run=True,source_ids=('flc_license_notices',)))
    assert stats.status=='dry_run_complete'
    assert stats.due_sources==('flc_license_notices',)
    assert db.list_source_sync_events()==[]


def test_execute_records_success_and_next_due(tmp_path: Path):
    db=Database(tmp_path/'fia.sqlite3')
    calls=[]
    def fake(database, policy, config):
        calls.append(policy.source_id)
        return UpsertStats(total=3,new=2,changed=1,unchanged=0),None,{'test':True}
    now=datetime(2026,8,14,20,tzinfo=timezone.utc)
    stats=run_source_orchestrator(
        db,SourceOrchestratorConfig(dry_run=False,source_ids=('flc_license_notices',)),now=now,executor=fake
    )
    assert calls==['flc_license_notices']
    assert stats.new_records==2 and stats.changed_records==1
    state=db.source_sync_state('flc_license_notices')
    assert state['last_status']=='completed'
    assert state['next_due_at'] is not None
    assert db.list_source_sync_events()[0]['status']=='completed'


def test_stream_normalizer_only_keeps_cessations():
    events=[
      {'event':{'timepoint':123},'data':{'company_number':'01234567','company_name':'Old Co Ltd','company_status':'dissolved','date_of_cessation':'2026-08-01'}},
      {'event':{'timepoint':124},'data':{'company_number':'76543210','company_name':'Live Co Ltd','company_status':'active'}},
    ]
    rows=normalize_stream_dissolutions(events)
    assert len(rows)==1
    assert rows[0].external_id=='01234567'
    assert rows[0].source_id=='companies_house_stream'
