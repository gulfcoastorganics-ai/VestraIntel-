from __future__ import annotations

from dataclasses import dataclass

from .db import Database
from .scheduler import SchedulerConfig, SchedulerStats, run_scheduler
from .source_orchestration import SourceOrchestratorConfig, SourceOrchestratorStats, run_source_orchestrator


@dataclass(frozen=True)
class PortfolioRunStats:
    sources: SourceOrchestratorStats
    research: SchedulerStats


def run_portfolio(
    db: Database,
    *,
    source_config: SourceOrchestratorConfig | None = None,
    research_config: SchedulerConfig | None = None,
) -> PortfolioRunStats:
    """Refresh due public sources, then allocate permitted research effort across all cases."""
    source_stats = run_source_orchestrator(db, source_config or SourceOrchestratorConfig())
    research_stats = run_scheduler(db, research_config or SchedulerConfig())
    return PortfolioRunStats(sources=source_stats, research=research_stats)
