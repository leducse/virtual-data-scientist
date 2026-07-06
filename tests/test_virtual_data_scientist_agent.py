import importlib.util
import unittest
from pathlib import Path
from typing import Any


AGENT_MAIN_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "VirtualDataScientistAgent" / "main.py"
)


def load_agent_module():
    spec = importlib.util.spec_from_file_location("virtual_data_scientist_agent_main", AGENT_MAIN_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load Virtual Data Scientist AgentCore entrypoint.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent = load_agent_module()


class VirtualDataScientistAgentContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_process_message_creates_session_and_returns_artifact_metadata_only(self) -> None:
        calls: list[tuple[str, dict[str, Any]]] = []
        original_call_tool = agent.call_tool

        def fake_call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            calls.append((name, arguments))
            if name == "create_analysis_session":
                return {"ok": True, "session": {"id": "sess_created"}}
            if name == "run_light_analysis":
                return {
                    "ok": True,
                    "session": {"id": "sess_created"},
                    "dataset": {"id": "dataset_orders", "table_name": "orders"},
                    "run": {"id": "run_light", "status": "succeeded"},
                    "profile": {
                        "table_name": "orders",
                        "candidate_methods": [
                            {
                                "type": "descriptive_analysis",
                                "reason": "Start with table shape and data quality.",
                            }
                        ],
                        "warnings": [],
                    },
                    "artifacts": [
                        {
                            "id": "artifact_profile",
                            "artifact_type": "profile",
                            "title": "Schema profile",
                            "summary": "Profile summary",
                            "content": {"must_not": "leave the runtime"},
                        }
                    ],
                }
            raise AssertionError(f"Unexpected tool call: {name}")

        agent.call_tool = fake_call_tool
        try:
            result = await agent.process_message(
                "browser-session",
                "What should I analyze first?",
                {
                    "data_source_id": "demo_warehouse",
                    "table_name": "orders",
                    "run_deep": False,
                },
            )
        finally:
            agent.call_tool = original_call_tool

        self.assertEqual([name for name, _ in calls], ["create_analysis_session", "run_light_analysis"])
        self.assertEqual(calls[0][1]["user_goal"], "What should I analyze first?")
        self.assertEqual(calls[1][1]["session_id"], "sess_created")
        self.assertEqual(result["analysis_session_id"], "sess_created")
        self.assertEqual(result["table_name"], "orders")
        self.assertEqual(result["light_run_id"], "run_light")
        self.assertIsNone(result["deep_run_id"])
        self.assertEqual(
            result["artifacts"],
            [
                {
                    "id": "artifact_profile",
                    "artifact_type": "profile",
                    "title": "Schema profile",
                    "summary": "Profile summary",
                }
            ],
        )
        self.assertNotIn("content", result["artifacts"][0])
        self.assertIn("Best candidate paths", result["response"])

    async def test_process_message_continues_session_and_polls_deep_analysis(self) -> None:
        calls: list[tuple[str, dict[str, Any]]] = []
        original_call_tool = agent.call_tool

        def fake_call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            calls.append((name, arguments))
            if name == "continue_analysis":
                return {"ok": True}
            if name == "run_light_analysis":
                return {
                    "ok": True,
                    "session": {"id": "sess_existing"},
                    "dataset": {"id": "dataset_churn", "table_name": "customer_churn"},
                    "run": {"id": "run_light", "status": "succeeded"},
                    "profile": {
                        "table_name": "customer_churn",
                        "candidate_methods": [
                            {
                                "type": "classification",
                                "reason": "There is a likely churn target.",
                            }
                        ],
                        "warnings": ["Check class balance before modeling."],
                    },
                    "artifacts": [
                        {
                            "id": "artifact_light_code",
                            "artifact_type": "code",
                            "title": "Light analysis code",
                            "summary": "Reproduction code",
                        }
                    ],
                }
            if name == "request_deep_analysis":
                return {"ok": True, "run": {"id": "run_deep", "status": "queued"}}
            if name == "get_analysis_status":
                return {
                    "ok": True,
                    "run": {"id": "run_deep", "status": "succeeded"},
                    "artifacts": [
                        {
                            "id": "artifact_deep_report",
                            "artifact_type": "report",
                            "title": "Deep analysis report",
                            "summary": "Recommended path",
                            "content": {"summary": "Use a classification baseline with leakage checks."},
                        },
                        {
                            "id": "artifact_deep_code",
                            "artifact_type": "code",
                            "title": "Deep analysis code",
                            "summary": "Reproduction code",
                            "content": "print('model')",
                        },
                    ],
                }
            raise AssertionError(f"Unexpected tool call: {name}")

        agent.call_tool = fake_call_tool
        try:
            result = await agent.process_message(
                "browser-session",
                "Please run deep modeling for churn.",
                {
                    "analysis_session_id": "sess_existing",
                    "data_source_id": "uploaded_csv_1",
                    "table_name": "customer_churn",
                    "run_deep": True,
                },
            )
        finally:
            agent.call_tool = original_call_tool

        self.assertEqual(
            [name for name, _ in calls],
            ["continue_analysis", "run_light_analysis", "request_deep_analysis", "get_analysis_status"],
        )
        self.assertEqual(calls[0][1], {"session_id": "sess_existing", "message": "Please run deep modeling for churn."})
        self.assertEqual(calls[2][1]["constraints"]["privacy_mode"], "registered_dataset_only")
        self.assertEqual(result["analysis_session_id"], "sess_existing")
        self.assertEqual(result["deep_run_id"], "run_deep")
        self.assertEqual(result["deep_status"], "succeeded")
        self.assertIn("classification baseline", result["response"])
        self.assertEqual([artifact["id"] for artifact in result["artifacts"]], [
            "artifact_light_code",
            "artifact_deep_report",
            "artifact_deep_code",
        ])
        self.assertTrue(all("content" not in artifact for artifact in result["artifacts"]))

    async def test_handle_invocation_rejects_empty_prompt(self) -> None:
        result = await agent.handle_invocation({"prompt": "", "session_id": "browser-session"})

        self.assertEqual(result, {"error": "No prompt provided", "session_id": "browser-session"})


if __name__ == "__main__":
    unittest.main()
