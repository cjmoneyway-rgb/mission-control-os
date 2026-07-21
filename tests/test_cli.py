from __future__ import annotations

import subprocess
import sys
import unittest


class CommandLineTests(unittest.TestCase):
    def test_demo_runs_without_api_key_or_network(self) -> None:
        result = subprocess.run(
            [sys.executable, "main.py", "--demo", "--no-log"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Mission Control OS™ Execution", result.stdout)
        self.assertIn("Governance: approved", result.stdout)

    def test_missing_directive_returns_usage_error(self) -> None:
        result = subprocess.run(
            [sys.executable, "main.py", "--no-log"],
            check=False,
            capture_output=True,
            text=True,
            input="",
        )
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
