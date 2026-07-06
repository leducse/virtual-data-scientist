import json
import unittest
from typing import Any

import mcp_server.server as mcp_server


class McpStdioContractTest(unittest.TestCase):
    def test_initialize_and_tools_list_contract(self) -> None:
        initialized = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        tools = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

        self.assertEqual(initialized["result"]["serverInfo"]["name"], "virtual-data-scientist")
        self.assertEqual(initialized["result"]["capabilities"], {"tools": {}})
        tool_names = [tool["name"] for tool in tools["result"]["tools"]]
        self.assertEqual(
            tool_names,
            [
                "create_analysis_session",
                "upload_dataset",
                "run_light_analysis",
                "request_deep_analysis",
                "get_analysis_status",
                "get_analysis_session",
                "continue_analysis",
            ],
        )

    def test_tools_call_wraps_tool_result_as_mcp_text_content(self) -> None:
        original_call_tool = mcp_server.call_tool
        calls: list[tuple[str, dict[str, Any]]] = []

        def fake_call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            calls.append((name, arguments))
            return {"ok": True, "session": {"id": "sess_1"}}

        mcp_server.call_tool = fake_call_tool
        try:
            result = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "create_analysis_session",
                        "arguments": {"user_goal": "Profile uploaded sales data."},
                    },
                }
            )
        finally:
            mcp_server.call_tool = original_call_tool

        self.assertEqual(calls, [("create_analysis_session", {"user_goal": "Profile uploaded sales data."})])
        self.assertFalse(result["result"]["isError"])
        self.assertEqual(result["result"]["content"][0]["type"], "text")
        self.assertEqual(json.loads(result["result"]["content"][0]["text"])["session"]["id"], "sess_1")


if __name__ == "__main__":
    unittest.main()
