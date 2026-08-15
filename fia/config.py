from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_path: Path
    user_agent: str
    companies_house_api_key: str | None
    companies_house_stream_key: str | None
    uspto_api_key: str | None
    data_gov_api_key: str | None
    agent_api_key: str | None
    public_base_url: str | None


def load_settings() -> Settings:
    db_path = Path(os.getenv("FIA_DB_PATH", "data/fia.sqlite3")).expanduser()
    return Settings(
        db_path=db_path,
        user_agent=os.getenv(
            "FIA_USER_AGENT", "ForgottenAssetIntelligence/1.5 (+contact@example.com)"
        ),
        companies_house_api_key=os.getenv("COMPANIES_HOUSE_API_KEY") or None,
        companies_house_stream_key=os.getenv("COMPANIES_HOUSE_STREAM_KEY") or None,
        uspto_api_key=os.getenv("USPTO_API_KEY") or None,
        data_gov_api_key=os.getenv("DATA_GOV_API_KEY") or None,
        agent_api_key=os.getenv("FIA_AGENT_API_KEY") or None,
        public_base_url=os.getenv("FIA_PUBLIC_BASE_URL") or None,
    )
