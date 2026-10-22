from __future__ import annotations

import os
import unittest
from unittest import mock

from mcp.shared.memory import create_connected_server_and_client_session

from breakfix.sandbox import MockSandbox
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


if __name__ == "__main__":
    unittest.main()
