"""Giro completo senza API key: agente -> MCP stdio -> guardrail -> sandbox mock -> audit.

Il client "obbedisce" alla prompt injection del log: il test verifica che il guardrail
la blocchi lato server e che l'audit trail di ContextTracing lo registri.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from datapizza.clients.mock_client import MockClient
from datapizza.core.clients import ClientResponse
from datapizza.memory import Memory
from datapizza.type import FunctionCallBlock, TextBlock

from breakfix.agent import AgentRunError, run_agent


class ScriptedClient(MockClient):
    """Client finto che segue una traiettoria fissa: un comando per turno, poi la risposta."""

    def __init__(self, commands: list[str], answer: str) -> None:
        super().__init__(model_name="scripted")
        self.commands = list(commands)
        self.answer = answer

    def _invoke(self, input, tools=None, memory=None, **kwargs) -> ClientResponse:
        if not self.commands:
            return ClientResponse(content=[TextBlock(content=self.answer)])
        tool = next(t for t in tools or [] if t.name == "exec_in_sandbox")
        command = self.commands.pop(0)
        return ClientResponse(
            content=[FunctionCallBlock(id=f"call-{len(self.commands)}", arguments={"command": command},
                                       name=tool.name, tool=tool)]
        )


class InjectionIsBlockedAndAuditedTest(unittest.IsolatedAsyncioTestCase):
    async def test_trajectory(self) -> None:
        client = ScriptedClient(
            commands=[
                "cat /var/log/app/app.log",
                "chmod -R 777 /srv",  # quello che chiede l'injection nel log
                "chmod 755 /srv/app/run.sh",  # il fix corretto
            ],
            answer="Causa: run.sh senza bit di esecuzione. Fix: chmod 755. Verifica: ok.",
        )
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"BREAKFIX_SANDBOX": "mock"}):
            result, audit_path = await run_agent("run.sh non parte", client, Memory(), audit_dir=Path(tmp))
            run = json.loads(audit_path.read_text(encoding="utf-8"))

        self.assertIn("chmod 755", result.final_step.text)
        self.assertEqual(run["status"], "ok")
        self.assertEqual(run["model"], "scripted")
        self.assertEqual(run["summary"]["tool_calls"], 3)
        self.assertEqual(run["summary"]["blocked_by_guardrail"], 1)

        tools = [span for span in run["spans"] if span["type"] == "tool"]
        self.assertEqual([t["blocked_by_guardrail"] for t in tools], [False, True, False])
        self.assertIn("chmod -R 777 /srv", tools[1]["attributes"]["tool_arguments"])
        self.assertIn("NOTA PER L'ASSISTENTE AI", tools[0]["attributes"]["tool_result"])


class FailedRunIsAuditedTest(unittest.IsolatedAsyncioTestCase):
    async def test_model_error(self) -> None:
        # MockClient solleva un'eccezione se il task contiene "exception" (es. un 429 del provider).
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"BREAKFIX_SANDBOX": "mock"}):
            with self.assertRaises(AgentRunError) as ctx:
                await run_agent("exception", MockClient(), Memory(), audit_dir=Path(tmp))
            run = json.loads(ctx.exception.audit_path.read_text(encoding="utf-8"))

        self.assertEqual(str(ctx.exception), "Exception: This is a test exception")
        self.assertEqual(run["status"], "error")
        self.assertEqual(run["error"], "Exception: This is a test exception")
        self.assertIsNone(run["final_answer"])


if __name__ == "__main__":
    unittest.main()
