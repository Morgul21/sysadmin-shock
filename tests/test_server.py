from __future__ import annotations

import os
import subprocess
import sys
import unittest
from unittest import mock

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client
from mcp.shared.memory import create_connected_server_and_client_session

from breakfix.guardrail import BLOCKED_PREFIX
from breakfix.sandbox import DockerSandbox, MockSandbox
from breakfix.server import build_server


class ServerContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_exposes_exactly_one_tool(self) -> None:
        async with create_connected_server_and_client_session(build_server(MockSandbox())) as session:
            tools = (await session.list_tools()).tools
        self.assertEqual([tool.name for tool in tools], ["exec_in_sandbox"])
        self.assertTrue(tools[0].annotations.destructiveHint)

    async def test_exec_returns_structured_result(self) -> None:
        async with create_connected_server_and_client_session(build_server(MockSandbox())) as session:
            result = await session.call_tool("exec_in_sandbox", {"command": "ls -l /srv/app"})
        self.assertFalse(result.isError)
        self.assertEqual(result.structuredContent["exit_code"], 0)
        self.assertIn("run.sh", result.structuredContent["stdout"])

    async def test_guardrail_blocks_before_the_sandbox(self) -> None:
        sandbox = mock.Mock(wraps=MockSandbox())
        async with create_connected_server_and_client_session(build_server(sandbox)) as session:
            result = await session.call_tool("exec_in_sandbox", {"command": "chmod 777 /srv/app/run.sh"})
        self.assertTrue(result.isError)
        self.assertIn("scrivibile-da-tutti", result.content[0].text)
        sandbox.exec.assert_not_called()

    async def test_empty_command_is_rejected(self) -> None:
        async with create_connected_server_and_client_session(build_server(MockSandbox())) as session:
            result = await session.call_tool("exec_in_sandbox", {"command": ""})
        self.assertTrue(result.isError)

    async def test_a_command_that_hangs_comes_back_as_a_result(self) -> None:
        # Il tool critico si blocca (es. `tail -f`): dopo il timeout l'agente riceve un esito che può
        # leggere (124, come `timeout` di coreutils), non un'eccezione e non un'attesa senza fine.
        hang = subprocess.TimeoutExpired(cmd="docker exec", timeout=1)
        with mock.patch("breakfix.sandbox.subprocess.run", side_effect=hang) as run:
            async with create_connected_server_and_client_session(build_server(DockerSandbox(timeout=1))) as session:
                result = await session.call_tool("exec_in_sandbox", {"command": "tail -f /var/log/app/app.log"})
        self.assertEqual(run.call_args.kwargs["timeout"], 1)
        self.assertFalse(result.isError)
        self.assertEqual(result.structuredContent["exit_code"], 124)
        self.assertIn("timeout: comando interrotto dopo 1s", result.structuredContent["stderr"])

    async def test_a_sandbox_that_is_down_is_a_tool_error(self) -> None:
        # Docker non c'è: l'agente riceve un errore del tool con il motivo, e può dirlo a chi l'ha lanciato.
        with mock.patch("breakfix.sandbox.subprocess.run", side_effect=FileNotFoundError("docker")):
            async with create_connected_server_and_client_session(build_server(DockerSandbox())) as session:
                result = await session.call_tool("exec_in_sandbox", {"command": "id"})
        self.assertTrue(result.isError)
        self.assertIn("docker", result.content[0].text)


class DatapizzaMCPClientTest(unittest.IsolatedAsyncioTestCase):
    """Stesso percorso dell'agente: datapizza MCPClient -> stdio -> server con backend mock."""

    async def test_agent_sees_and_calls_the_tool(self) -> None:
        from breakfix.agent import mcp_server_client

        with mock.patch.dict(os.environ, {"BREAKFIX_SANDBOX": "mock"}):
            client = mcp_server_client()
        async with client as mcp:
            tools = await mcp.a_list_tools()
            self.assertEqual([tool.name for tool in tools], ["exec_in_sandbox"])
            output = await tools[0].func(command="free -m")
        self.assertIn("Mem:", output)


class AnotherHostTest(unittest.IsolatedAsyncioTestCase):
    """Un host MCP che non è datapizza (qui il client stdio dell'SDK), come Claude Desktop o Cursor:
    lancia il server come sottoprocesso e gli parla nel protocollo, senza niente del progetto."""

    async def test_any_host_gets_the_tool_and_the_guardrail(self) -> None:
        env = {**get_default_environment(), "BREAKFIX_SANDBOX": "mock"}
        server = StdioServerParameters(command=sys.executable, args=["-m", "breakfix.server"], env=env)
        async with stdio_client(server) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            allowed = await session.call_tool("exec_in_sandbox", {"command": "id"})
            blocked = await session.call_tool("exec_in_sandbox", {"command": "chmod 777 /srv/app/run.sh"})
        self.assertEqual([tool.name for tool in tools], ["exec_in_sandbox"])
        self.assertIn("uid=0(root)", allowed.structuredContent["stdout"])
        self.assertTrue(blocked.isError)
        self.assertIn(BLOCKED_PREFIX, blocked.content[0].text)


if __name__ == "__main__":
    unittest.main()
