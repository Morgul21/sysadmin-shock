"""Runner degli eval senza Docker né API key: lab finto, client scriptato, sandbox mock."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from datapizza.clients.mock_client import MockClient

from breakfix.evaluate import evaluate_scenario, write_report
from breakfix.lab import CheckResult, get_scenario
from test_agent_trace import ScriptedClient


class FakeLab:
    def __init__(self, passed: bool) -> None:
        self.passed = passed
        self.started = []

    def start(self, scenario) -> None:
        self.started.append(scenario.id)

    def check(self, scenario) -> CheckResult:
        return CheckResult(self.passed, "PASS: ok" if self.passed else "FAIL: l'app non parte")


class EvaluateScenarioTest(unittest.IsolatedAsyncioTestCase):
    async def test_row_comes_from_check_and_audit(self) -> None:
        scenario = get_scenario("run-sh-noexec")
        client = ScriptedClient(
            commands=["ls -l /srv/app", "chmod 777 /srv/app/run.sh", "chmod 755 /srv/app/run.sh"],
            answer="Causa: run.sh non eseguibile. Fix: chmod 755.",
        )
        lab = FakeLab(passed=True)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"BREAKFIX_SANDBOX": "mock"}):
            row = await evaluate_scenario(scenario, client, lab, audit_dir=Path(tmp))
            report = json.loads(write_report([row], "scripted", eval_dir=Path(tmp)).read_text(encoding="utf-8"))

        self.assertEqual(lab.started, ["run-sh-noexec"])
        self.assertTrue(row.passed)
        self.assertEqual(row.tool_calls, 3)
        self.assertEqual(row.blocked_by_guardrail, 1)
        self.assertIsNone(row.error)
        self.assertEqual((report["passed"], report["total"]), (1, 1))

    async def test_failed_agent_is_still_checked(self) -> None:
        # MockClient solleva un'eccezione se il task contiene "exception".
        base = get_scenario("run-sh-noexec")
        scenario = replace(base, ticket=replace(base.ticket, body="exception"))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"BREAKFIX_SANDBOX": "mock"}):
            row = await evaluate_scenario(scenario, MockClient(), FakeLab(passed=False), audit_dir=Path(tmp))

        self.assertFalse(row.passed)
        self.assertEqual(row.error, "Exception: This is a test exception")
        self.assertEqual(row.check_output, "FAIL: l'app non parte")


if __name__ == "__main__":
    unittest.main()
