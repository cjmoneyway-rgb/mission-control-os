"""Deterministic governance checks applied before executive delivery."""

from __future__ import annotations

import re

from .models import GovernanceResult


REQUIRED_SECTIONS = (
    "CEO Executive Summary",
    "Biggest Win",
    "Decision Required",
    "Next Major Move",
)

SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"OPENAI_API_KEY\s*=\s*[^\s<]+", re.IGNORECASE),
)


def review_output(output: str) -> GovernanceResult:
    findings: list[str] = []
    if not output.strip():
        findings.append("Output is empty.")
    for section in REQUIRED_SECTIONS:
        if section not in output:
            findings.append(f"Missing required section: {section}")
    if any(pattern.search(output) for pattern in SECRET_PATTERNS):
        findings.append("Output appears to contain a secret and cannot be delivered.")

    return GovernanceResult(
        status="approved" if not findings else "revision_required",
        passed=not findings,
        findings=tuple(findings),
    )
