"""Optional conformance check through the official MCP Python client."""

import importlib.util
import os
from pathlib import Path
import sys
import unittest


@unittest.skipUnless(importlib.util.find_spec("mcp"), "Install .[mcp-test] for official SDK interoperability checks")
class SdkTests(unittest.IsolatedAsyncioTestCase):
    async def test_sdk_initializes_lists_tools_and_reads_tool_error(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        root = Path(__file__).resolve().parents[1]
        params = StdioServerParameters(command=sys.executable, args=["-m", "retract", "mcp"],
                                       env={**os.environ, "PYTHONPATH": str(root / "src"), "RETRACT_URL": "http://127.0.0.1:8100"})
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                initialized = await session.initialize()
                self.assertEqual(initialized.serverInfo.name, "retract")
                tools = await session.list_tools()
                self.assertEqual({tool.name for tool in tools.tools}, {"remember", "process_update", "recall", "history", "record_plan", "revise_plan"})
                result = await session.call_tool("remember", {})
                self.assertTrue(result.isError)
