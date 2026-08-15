from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from fia.models import Opportunity


class SourceAdapter(ABC):
    source_id: str

    @abstractmethod
    def fetch(self) -> Iterable[Opportunity]:
        raise NotImplementedError
