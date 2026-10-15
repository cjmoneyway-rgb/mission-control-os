"""Core data contracts for Mission Control OS."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
import math
from .contracts import text


@dataclass(frozen=True)
class Department:
    id: str
    name: str
    executive: str
    mandate: str
    keywords: tuple[str, ...]
    instructions: str

    def __post_init__(self):
        for value in (self.id, self.name, self.executive, self.mandate, self.instructions):
            text(value)
        if not isinstance(self.keywords, tuple) or not self.keywords:
            raise ValueError('Department keywords must be a nonempty tuple')
        for keyword in self.keywords:
            text(keyword)


@dataclass(frozen=True)
class RouteDecision:
    department_id: str
    rationale: str
    confidence: float

    def __post_init__(self):
        text(self.department_id)
        text(self.rationale)
        if type(self.confidence) not in (float, int) or not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError('Routing confidence must be finite and between 0 and 1')


@dataclass(frozen=True)
class GovernanceResult:
    status: str
    passed: bool
    findings: tuple[str, ...] = ()


@dataclass
class ExecutionRecord:
    directive: str
    provider: str
    route: RouteDecision
    department: Department
    output: str
    governance: GovernanceResult
    revision_count: int = 0
    execution_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
