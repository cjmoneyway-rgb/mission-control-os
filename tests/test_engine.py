from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mission_control import MissionControlOS
from mission_control.governance import review_output
from mission_control.models import RouteDecision


class RevisionProvider:
    name = "revision-test"

    def __init__(self) -> None:
        self.calls = 0

    def classify(self, directive, departments):
        return RouteDecision("executive_strategy", "Test route", 1.0)

    def execute(self, directive, department, governance_feedback=()):
        self.calls += 1
        if not governance_feedback:
            return "Incomplete first draft"
        return "\n".join(
            ("CEO Executive Summary", "Biggest Win", "Decision Required", "Next Major Move")
        )


class MissionControlTests(unittest.TestCase):
    def test_routes_journal_directive_to_media(self) -> None:
        system = MissionControlOS(provider="mock", audit_log=None)
        record = system.run("Create a Moneyway Journal article from this transcript")
        self.assertEqual(record.route.department_id, "media_editorial")
        self.assertTrue(record.governance.passed)
        self.assertIn("CEO Executive Summary", record.output)

    def test_routes_unknown_directive_to_executive_strategy(self) -> None:
        system = MissionControlOS(provider="mock", audit_log=None)
        record = system.run("Bring clarity to this unusual matter")
        self.assertEqual(record.route.department_id, "executive_strategy")

    def test_writes_jsonl_audit_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "audit.jsonl"
            system = MissionControlOS(provider="mock", audit_log=log_path)
            record = system.run("Prepare a podcast guest interview")
            payload = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["execution_id"], record.execution_id)
            self.assertEqual(payload["route"]["department_id"], "podcast_operations")

    def test_governance_rejects_missing_summary(self) -> None:
        result = review_output("A draft without the required executive closeout.")
        self.assertFalse(result.passed)
        self.assertEqual(result.status, "revision_required")

    def test_governance_rejects_secret_pattern(self) -> None:
        output = "\n".join(
            [
                "CEO Executive Summary",
                "Biggest Win",
                "Decision Required",
                "Next Major Move",
                "OPENAI_API_KEY=not-a-real-secret-for-test",
            ]
        )
        result = review_output(output)
        self.assertFalse(result.passed)
        self.assertTrue(any("secret" in finding for finding in result.findings))

    def test_empty_directive_is_rejected(self) -> None:
        system = MissionControlOS(provider="mock", audit_log=None)
        with self.assertRaises(ValueError):
            system.run("   ")

    def test_governance_feedback_triggers_one_revision(self) -> None:
        provider = RevisionProvider()
        system = MissionControlOS(provider=provider, audit_log=None)
        record = system.run("Prepare an executive decision")
        self.assertEqual(provider.calls, 2)
        self.assertEqual(record.revision_count, 1)
        self.assertTrue(record.governance.passed)


if __name__ == "__main__":
    unittest.main()
