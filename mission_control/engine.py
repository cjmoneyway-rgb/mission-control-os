"""Governance-first routing, execution, revision, and audit orchestration."""

from __future__ import annotations

from pathlib import Path
from dataclasses import asdict
import copy

from .audit import JsonlAuditLog
from .config import DEFAULT_CONFIG, load_departments
from .governance import review_output
from .models import ExecutionRecord, RouteDecision
from .providers import MockProvider, OpenAIProvider, Provider, SafetyDecision


class BlockedExecution(RuntimeError):
    """No rejected content is attached to this exception."""


class MissionControlOS:
    def __init__(
        self,
        provider: str | Provider = "mock",
        model: str = "gpt-5.6",
        department_config: Path | str = DEFAULT_CONFIG,
        audit_log: Path | str | None = "logs/executions.jsonl",
        safety_gate=None,
    ) -> None:
        self.departments = load_departments(department_config)
        self.safety_gate = safety_gate
        self._offline_provider = None
        if isinstance(provider, str):
            if provider == "mock":
                self.provider: Provider = MockProvider()
                self._offline_provider = self.provider
            elif provider == "openai":
                self.provider = OpenAIProvider(model=model, safety_gate=safety_gate)
            else:
                raise ValueError("provider must be 'mock', 'openai', or a Provider object")
        else:
            # No self-declared provider name/type/attribute grants a bypass.
            self.provider = provider
        self.audit = JsonlAuditLog(audit_log) if audit_log else None

    def _invoke(self, operation, directive, departments, feedback=()):
        # Only the internally constructed deterministic mock is exempt. Even a
        # MockProvider instance injected by a caller must obtain clearance.
        offline = self.provider is self._offline_provider and type(self.provider) is MockProvider
        if not offline:
            payload = {
                'operation': operation,
                'directive': directive,
                'department_projections': [asdict(item) for item in departments.values()],
                'governance_feedback': list(feedback),
            }
            try:
                decision = self.safety_gate(copy.deepcopy(payload)) if self.safety_gate else None
            except Exception:
                raise BlockedExecution('Provider clearance could not be verified') from None
            if not isinstance(decision, SafetyDecision) or decision.authorized is not True or decision.sensitive_data_cleared is not True:
                raise BlockedExecution('Provider call blocked: authorization and sensitive-data clearance required')
        if operation == 'classify':
            if offline:
                return MockProvider.classify(self.provider, directive, dict(departments))
            return self.provider.classify(directive, dict(departments))
        department = next(iter(departments.values()))
        if offline:
            return MockProvider.execute(self.provider, directive, department, feedback)
        return self.provider.execute(directive, department, feedback)

    def run(self, directive: str) -> ExecutionRecord:
        if not isinstance(directive, str):
            raise ValueError("Directive must be text")
        directive = directive.strip()
        if not directive:
            raise ValueError("Executive directive cannot be empty")

        route = self._invoke('classify', directive, self.departments)
        if not isinstance(route, RouteDecision):
            raise ValueError("Malformed provider routing result")
        route = RouteDecision(route.department_id, route.rationale, route.confidence)
        if route.department_id not in self.departments:
            raise ValueError(
                "Provider selected an unknown department"
            )
        department = self.departments[route.department_id]

        output = self._invoke('execute', directive, {department.id: department})
        if not isinstance(output, str):
            raise ValueError("Malformed provider output")
        governance = review_output(output)
        revision_count = 0
        if not governance.passed:
            revision_count = 1
            output = self._invoke('execute', directive, {department.id: department}, governance.findings)
            if not isinstance(output, str):
                raise ValueError("Malformed provider output")
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
        if not governance.passed:
            raise BlockedExecution("Execution blocked: final technical governance review failed")
        return record
