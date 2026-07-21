"""Offline and OpenAI execution providers."""

from __future__ import annotations

import json
from typing import Protocol

from .models import Department, RouteDecision


class Provider(Protocol):
    name: str

    def classify(
        self, directive: str, departments: dict[str, Department]
    ) -> RouteDecision: ...

    def execute(
        self,
        directive: str,
        department: Department,
        governance_feedback: tuple[str, ...] = (),
    ) -> str: ...


class MockProvider:
    """Deterministic provider for demos, tests, and zero-cost evaluation."""

    name = "mock"

    def classify(
        self, directive: str, departments: dict[str, Department]
    ) -> RouteDecision:
        normalized = directive.lower()
        scores = {
            department_id: sum(
                1 for keyword in department.keywords if keyword in normalized
            )
            for department_id, department in departments.items()
        }
        best_score = max(scores.values())
        department_id = (
            max(scores, key=scores.get) if best_score else "executive_strategy"
        )
        confidence = min(0.99, 0.55 + (best_score * 0.1)) if best_score else 0.5
        return RouteDecision(
            department_id=department_id,
            rationale=(
                f"Matched {best_score} configured keyword(s)."
                if best_score
                else "No specialist keyword matched; routed to executive strategy."
            ),
            confidence=confidence,
        )

    def execute(
        self,
        directive: str,
        department: Department,
        governance_feedback: tuple[str, ...] = (),
    ) -> str:
        feedback_note = (
            " Governance feedback was incorporated: " + "; ".join(governance_feedback)
            if governance_feedback
            else ""
        )
        return f"""# Mission Control OS™ Execution

## Routed Department
**{department.name}** — {department.executive}

## Directive
{directive}

## Department Intelligence
The directive was evaluated under this mandate: {department.mandate}

## Recommended Execution
1. Confirm the source material, audience, decision owner, and delivery deadline.
2. Produce the primary governed work product in the {department.name} context.
3. Preserve reusable insights, relationship implications, and next actions.
4. Submit the result for human executive review before external publication.{feedback_note}

## Decision Trail
- Classification: {department.id}
- Specialist context: isolated department instructions applied
- Governance: brand alignment, executive-summary structure, and secret screening
- Human authority: final approval remains with the CEO

## CEO Executive Summary

### Biggest Win
The directive is now converted into a department-owned, decision-ready execution path.

### Decision Required
Approve the recommended execution path and confirm any source material needed for production.

### Next Major Move
Assign the first deliverable to {department.name} and record the approved outcome in organizational memory.
"""


class OpenAIProvider:
    """Live provider powered by the official OpenAI Python SDK Responses API."""

    name = "openai"

    def __init__(self, model: str = "gpt-5.6") -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The openai package is required for live mode. Run: pip install -r requirements.txt"
            ) from exc
        self.client = OpenAI()
        self.model = model

    def _respond(self, instructions: str, prompt: str) -> str:
        response = self.client.responses.create(
            model=self.model,
            instructions=instructions,
            input=prompt,
        )
        return response.output_text

    def classify(
        self, directive: str, departments: dict[str, Department]
    ) -> RouteDecision:
        catalog = [
            {"id": item.id, "name": item.name, "mandate": item.mandate}
            for item in departments.values()
        ]
        prompt = (
            "Classify the executive directive into exactly one department. Return only "
            "valid JSON with keys department_id, rationale, and confidence (0 to 1).\n\n"
            f"Departments: {json.dumps(catalog)}\n\nDirective: {directive}"
        )
        raw = self._respond(
            "You are the Mission Control OS routing layer. Do not execute the work.",
            prompt,
        )
        try:
            data = json.loads(raw)
            return RouteDecision(
                department_id=str(data["department_id"]),
                rationale=str(data["rationale"]),
                confidence=float(data["confidence"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Router returned invalid JSON: {raw[:240]}") from exc

    def execute(
        self,
        directive: str,
        department: Department,
        governance_feedback: tuple[str, ...] = (),
    ) -> str:
        feedback = "\n".join(f"- {item}" for item in governance_feedback)
        prompt = f"""Executive directive:
{directive}

Department mandate:
{department.mandate}

Governance feedback from a previous attempt:
{feedback or "None"}

Produce a decision-ready response. End with a section titled "CEO Executive Summary"
containing the exact subsections "Biggest Win", "Decision Required", and
"Next Major Move". Never include credentials or claim unverified execution.
"""
        instructions = (
            "You are Mission Control OS operating inside an isolated specialist context. "
            + department.instructions
        )
        return self._respond(instructions, prompt)
