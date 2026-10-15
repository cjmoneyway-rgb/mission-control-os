"""Explicit synthetic authorities for tests; never deployment configuration."""
from datetime import datetime, timedelta, timezone
from mission_control.contracts import ApprovalEvidence
from mission_control.providers import SafetyDecision


def synthetic_clearance(payload):
    return SafetyDecision(True, True)


class SyntheticAuthority:
    def __init__(self, approval, references):
        now = datetime.now(timezone.utc)
        self.evidence = ApprovalEvidence(approval, now - timedelta(minutes=1), now + timedelta(minutes=5), True)
        self.references = set(references)

    def resolve_approval(self, reference):
        return self.evidence if reference == self.evidence.approval.evidence_reference else None

    def resolve_reference(self, kind, reference):
        return (kind, reference) in self.references
