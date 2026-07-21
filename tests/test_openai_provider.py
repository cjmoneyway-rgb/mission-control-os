from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

from mission_control.config import load_departments
from mission_control.providers import OpenAIProvider


class FakeResponses:
    def __init__(self) -> None:
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if "routing layer" in kwargs["instructions"]:
            text = '{"department_id":"ai_innovation","rationale":"AI work","confidence":0.91}'
        else:
            text = "\n".join(
                ("CEO Executive Summary", "Biggest Win", "Decision Required", "Next Major Move")
            )
        return types.SimpleNamespace(output_text=text)


class FakeOpenAI:
    last_instance = None

    def __init__(self) -> None:
        self.responses = FakeResponses()
        FakeOpenAI.last_instance = self


class OpenAIProviderContractTests(unittest.TestCase):
    def test_uses_responses_api_without_network(self) -> None:
        fake_module = types.SimpleNamespace(OpenAI=FakeOpenAI)
        with patch.dict(sys.modules, {"openai": fake_module}):
            provider = OpenAIProvider(model="test-model")
            departments = load_departments()
            route = provider.classify("Build an AI workflow", departments)
            output = provider.execute(
                "Build an AI workflow", departments[route.department_id]
            )

        self.assertEqual(route.department_id, "ai_innovation")
        self.assertIn("CEO Executive Summary", output)
        calls = FakeOpenAI.last_instance.responses.calls
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(call["model"] == "test-model" for call in calls))
        self.assertTrue(all("input" in call for call in calls))


if __name__ == "__main__":
    unittest.main()
