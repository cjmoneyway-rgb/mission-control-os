"""Core data contracts for Mission Control OS."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class Department:
    id: str
    name: str
    executive: str
    mandate: str
    keywords: tuple[str, ...]
    instructions: str


@dataclass(frozen=True)
class RouteDecision:
    department_id: str
    rationale: str
    confidence: float


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
