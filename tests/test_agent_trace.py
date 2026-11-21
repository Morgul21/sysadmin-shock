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

        # il perché del blocco, leggibile senza scavare nel tool_result
        self.assertEqual([t["guardrail"] for t in tools][::2], [None, None])
        self.assertEqual(tools[1]["guardrail"]["rule"], "ricorsivo-di-sistema")
        self.assertEqual(tools[1]["guardrail"]["match"], "chmod -R 777 /srv")
        self.assertIn("directory di sistema", tools[1]["guardrail"]["reason"])
        [block] = run["summary"]["guardrail_blocks"]
        self.assertEqual(block["command"], "chmod -R 777 /srv")
        self.assertEqual(block["span_id"], tools[1]["span_id"])
        self.assertEqual(block["rule"], "ricorsivo-di-sistema")


class BackfillTest(unittest.TestCase):
    """Gli audit scritti prima del campo `guardrail` lo ricevono, frammento compreso."""

    def test_old_audit_gets_the_reason(self) -> None:
        from breakfix import audit
        from breakfix.guardrail import BLOCKED_PREFIX

        reason = "il comando viene costruito a runtime (eval, base64, | sh, -c): non è validabile"
        old_message = (f"Error executing tool exec_in_sandbox: {BLOCKED_PREFIX} [comando-dinamico]: {reason}. "
                       "Il comando non è stato eseguito.")
        command = "runuser -u app -- sh -c 'ulimit -a'"
        old = {
            "summary": {"llm_calls": 1, "tool_calls": 1, "blocked_by_guardrail": 1, "tool_errors": 1,
                        "tokens": {"prompt": 10, "completion": 1, "cached": 0, "thinking": 0}},
            "spans": [{
                "name": "Tool exec_in_sandbox", "type": "tool", "span_id": "ab",
                "attributes": {
                    "tool_arguments": str({"command": command}),
                    "tool_result": json.dumps({"content": [{"type": "text", "text": old_message}], "isError": True}),
                },
                "blocked_by_guardrail": True, "is_error": True,
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.json"
            path.write_text(json.dumps(old), encoding="utf-8")
            self.assertTrue(audit.backfill(path))
            self.assertFalse(audit.backfill(path))  # idempotente
            run = json.loads(path.read_text(encoding="utf-8"))

        expected = {"rule": "comando-dinamico", "match": "sh -c", "reason": reason}
        self.assertEqual(run["spans"][0]["guardrail"], expected)
        self.assertEqual(run["summary"]["guardrail_blocks"], [{"span_id": "ab", "command": command, **expected}])
        self.assertEqual(run["summary"]["tokens"]["prompt"], 10)


class SequenceClient(MockClient):
    """Client finto che risponde con una sequenza fissa: un comando (str) o un testo (TextBlock)."""

    def __init__(self, turns: list) -> None:
        super().__init__(model_name="sequence")
        self.turns = list(turns)
        self.inputs: list[str] = []

    def _invoke(self, input, tools=None, memory=None, **kwargs) -> ClientResponse:
        self.inputs.append(input)
        turn = self.turns.pop(0)
        if isinstance(turn, TextBlock):
            return ClientResponse(content=[turn])
        tool = next(t for t in tools or [] if t.name == "exec_in_sandbox")
        return ClientResponse(content=[FunctionCallBlock(id=f"call-{len(self.turns)}", arguments={"command": turn},
                                                         name=tool.name, tool=tool)])


class UnfinishedTextIsNudgedTest(unittest.IsolatedAsyncioTestCase):
    async def test_text_mid_task_does_not_end_the_run(self) -> None:
        # Come qwen3.8-27b su memory-hog: un turno di solo testo a metà diagnosi.
        client = SequenceClient([
            "cat /sys/fs/cgroup/memory.max",
            TextBlock(content="Let's see how much memory is actually in use."),
            "chmod 755 /srv/app/run.sh",
            TextBlock(content="Causa: run.sh. Correzione: chmod 755. Verifica: gestionale riesce."),
        ])
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"BREAKFIX_SANDBOX": "mock"}):
            result, audit_path = await run_agent("run.sh non parte", client, Memory(), audit_dir=Path(tmp))
            run = json.loads(audit_path.read_text(encoding="utf-8"))

        self.assertIn("Verifica", result.final_step.text)
        self.assertEqual(run["summary"]["tool_calls"], 2)
        self.assertEqual(run["summary"]["llm_calls"], 4)
        self.assertIn("Non hai ancora concluso", str(client.inputs[2]))

    async def test_nudges_are_bounded(self) -> None:
        client = SequenceClient([TextBlock(content="Let's see.")] * 5)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"BREAKFIX_SANDBOX": "mock"}):
            result, _ = await run_agent("run.sh non parte", client, Memory(), audit_dir=Path(tmp))

        self.assertEqual(result.final_step.text, "Let's see.")
        self.assertEqual(len(client.inputs), 3)  # il turno originale + MAX_NUDGES rilanci


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
