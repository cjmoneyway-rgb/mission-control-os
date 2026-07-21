"""Governance-first routing, execution, revision, and audit orchestration."""

from __future__ import annotations

from pathlib import Path

from .audit import JsonlAuditLog
from .config import DEFAULT_CONFIG, load_departments
from .governance import review_output
from .models import ExecutionRecord
from .providers import MockProvider, OpenAIProvider, Provider


class MissionControlOS:
    def __init__(
        self,
        provider: str | Provider = "mock",
        model: str = "gpt-5.6",
        department_config: Path | str = DEFAULT_CONFIG,
        audit_log: Path | str | None = "logs/executions.jsonl",
    ) -> None:
        self.departments = load_departments(department_config)
        if provider == "mock":
            self.provider: Provider = MockProvider()
        elif provider == "openai":
            self.provider = OpenAIProvider(model=model)
        elif isinstance(provider, str):
            raise ValueError("provider must be 'mock', 'openai', or a Provider object")
        else:
            self.provider = provider
        self.audit = JsonlAuditLog(audit_log) if audit_log else None

    def run(self, directive: str) -> ExecutionRecord:
        directive = directive.strip()
        if not directive:
            raise ValueError("Executive directive cannot be empty")

        route = self.provider.classify(directive, self.departments)
        if route.department_id not in self.departments:
            raise ValueError(
                f"Provider selected unknown department: {route.department_id}"
            )
        department = self.departments[route.department_id]

        output = self.provider.execute(directive, department)
        governance = review_output(output)
        revision_count = 0
        if not governance.passed:
            revision_count = 1
            output = self.provider.execute(directive, department, governance.findings)
            governance = review_output(output)

        record = ExecutionRecord(
            directive=directive,
            provider=self.provider.name,
            route=route,
            department=department,
            output=output,
            governance=governance,
            revision_count=revision_count,
        )
        if self.audit:
            self.audit.append(record)
        return record
