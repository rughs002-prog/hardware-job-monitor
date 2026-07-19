from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any


@dataclass(slots=True)
class Job:
    company: str
    title: str
    url: str
    location: str = ""
    description: str = ""
    external_id: str = ""
    posted_at: str = ""
    source: str = ""
    tags: list[str] = field(default_factory=list)
    relevance: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def fingerprint(self) -> str:
        stable_id = self.external_id.strip() or self.url.strip().lower()
        value = f"{self.company.strip().lower()}|{stable_id}"
        return sha256(value.encode("utf-8")).hexdigest()
