"""AgentCore entrypoint for the Virtual Data Scientist app.

The runtime is intentionally orchestration-only. It accepts chat requests from
the website, calls the MCP facade tools, preserves the app-owned analysis
session, and returns summaries plus artifact metadata. The BI app remains the
source of truth for datasets, code artifacts, and reports.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Any, AsyncIterator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from mcp_server.tools import call_tool  # noqa: E402
except ImportError:  # pragma: no cover - deployed CodeZip package is runtime-local
    from runtime_tools import call_tool  # type: ignore[no-redef]  # noqa: E402

try:
    from bedrock_agentcore import BedrockAgentCoreApp
except ImportError:  # pragma: no cover - local syntax/dev fallback

    class BedrockAgentCoreApp:  # type: ignore[no-redef]
        def __init__(self, debug: bool = False) -> None:
            self.debug = debug

        def entrypoint(self, func):
            return func

        def websocket(self, func):
            return func

        def run(self, port: int = 8080) -> None:
            print(
                "bedrock_agentcore is not installed. Install the AgentCore runtime package "
                "or run this module through AgentCore CLI.",
                flush=True,
            )


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp(debug=True)

DEFAULT_DATA_SOURCE_ID = "demo_warehouse"
DEEP_ANALYSIS_TOKENS = (
    "deep",
    "model",
    "forecast",
    "predict",
    "cluster",
    "segment",
    "anomaly",
    "outlier",
    "driver",
    "why",
)


def wants_deep_analysis(prompt: str, explicit: Any = None) -> bool:
    if isinstance(explicit, bool):
        return explicit
    normalized = prompt.lower()
    return any(token in normalized for token in DEEP_ANALYSIS_TOKENS)


def infer_table_name(prompt: str, table_name: Any = None) -> str | None:
    if isinstance(table_name, str) and table_name.strip():
        return table_name.strip()
    normalized = prompt.lower()
    if any(token in normalized for token in ("order", "sales", "forecast")):
        return "orders"
    return None


def artifact_metadata(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": artifact.get("id"),
        "artifact_type": artifact.get("artifact_type"),
        "title": artifact.get("title"),
        "summary": artifact.get("summary"),
    }


def _summary_from_light(result: dict[str, Any]) -> str:
    profile = result.get("profile", {})
    methods = profile.get("candidate_methods", [])
    warnings = profile.get("warnings", [])
    lines = [
        f"I created analysis session `{result.get('session', {}).get('id')}` and profiled `{profile.get('table_name')}`.",
        "",
        "Best candidate paths:",
    ]
    for method in methods[:5]:
        lines.append(f"- {method.get('type')}: {method.get('reason')}")
    if warnings:
        lines.append("")
        lines.append("Data quality warnings:")
        for warning in warnings[:5]:
            lines.append(f"- {warning}")
    lines.append("")
    lines.append("I also saved the profile, summary, and reproduction-code artifacts for follow-up work.")
    return "\n".join(lines)


def _summary_from_deep_queued(result: dict[str, Any]) -> str:
    run = result.get("run", {})
    context = result.get("context_bundle", {})
    return "\n".join(
        [
            f"Deep analysis is queued as `{run.get('id')}` with status `{run.get('status')}`.",
            "",
            "The handoff bundle includes:",
            f"- dataset: `{context.get('dataset_id')}`",
            f"- light analysis report: `{context.get('light_analysis_report_id')}`",
            f"- light analysis code: `{context.get('light_analysis_code_id')}`",
            f"- schema profile: `{context.get('schema_profile_id')}`",
            "",
            "The app-owned backend persists the deep-analysis run, context bundle, report, and code artifacts.",
        ]
    )


def _summary_from_deep_status(result: dict[str, Any] | None) -> str:
    if not result:
        return "Deep analysis was queued. Poll the run status for the final report."
    run = result.get("run", {})
    report_artifact = next(
        (artifact for artifact in result.get("artifacts", []) if artifact.get("artifact_type") == "report"),
        None,
    )
    content = report_artifact.get("content") if isinstance(report_artifact, dict) else None
    if isinstance(content, dict) and content.get("summary"):
        return str(content["summary"])
    return f"Deep analysis status: {run.get('status', 'unknown')}."


async def poll_deep_run(run_id: str, attempts: int = 8, delay_seconds: float = 0.3) -> dict[str, Any] | None:
    status = None
    for _ in range(attempts):
        status = call_tool("get_analysis_status", {"run_id": run_id})
        run_status = status.get("run", {}).get("status")
        if run_status not in {"queued", "running"}:
            return status
        await asyncio.sleep(delay_seconds)
    return status


async def process_message(session_id: str, prompt: str, request: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the first-pass data scientist chat controller."""
    request = request or {}
    wants_deep = wants_deep_analysis(prompt, request.get("run_deep"))
    data_source_id = str(request.get("data_source_id") or DEFAULT_DATA_SOURCE_ID)
    table_name = infer_table_name(prompt, request.get("table_name"))
    analysis_session_id = str(request.get("analysis_session_id") or "").strip()

    try:
        if analysis_session_id:
            call_tool("continue_analysis", {"session_id": analysis_session_id, "message": prompt})
        else:
            session_result = call_tool(
                "create_analysis_session",
                {
                    "user_goal": prompt,
                    "data_source_id": data_source_id,
                    "table_name": table_name,
                },
            )
            analysis_session_id = session_result["session"]["id"]

        light_result = call_tool(
            "run_light_analysis",
            {
                "session_id": analysis_session_id,
                "user_question": prompt,
                "data_source_id": data_source_id,
                "table_name": table_name,
            },
        )
        response = _summary_from_light(light_result)
        deep_result = None
        deep_status = None
        if wants_deep:
            deep_result = call_tool(
                "request_deep_analysis",
                {
                    "session_id": analysis_session_id,
                    "user_question": prompt,
                    "constraints": {
                        "max_runtime_minutes": 15,
                        "privacy_mode": "registered_dataset_only",
                    },
                },
            )
            run_id = deep_result.get("run", {}).get("id")
            deep_status = await poll_deep_run(str(run_id)) if run_id else None
            response = f"{response}\n\nDeep analysis:\n{_summary_from_deep_status(deep_status) or _summary_from_deep_queued(deep_result)}"

        artifacts = [
            *(light_result.get("artifacts") or []),
            *((deep_status or {}).get("artifacts") or []),
        ]
        profile = light_result.get("profile") or {}
        dataset = light_result.get("dataset") or {}
        return {
            "response": response,
            "session_id": session_id,
            "analysis_session_id": analysis_session_id,
            "data_source_id": data_source_id,
            "table_name": table_name or dataset.get("table_name") or profile.get("table_name"),
            "light_run_id": light_result.get("run", {}).get("id"),
            "deep_run_id": (deep_result or {}).get("run", {}).get("id"),
            "deep_status": (deep_status or {}).get("run", {}).get("status"),
            "artifacts": [artifact_metadata(artifact) for artifact in artifacts],
        }
    except Exception as exc:
        logger.exception("Virtual data scientist agent failed")
        return {
            "response": (
                "I could not reach the data-science MCP facade yet. Start the BI app with "
                "`python3 server.py`, set `DATA_SCIENCE_MCP_BASE_URL` if needed, and then retry. "
                f"Details: {exc}"
            ),
            "session_id": session_id,
            "analysis_session_id": analysis_session_id or None,
            "error": str(exc),
        }


async def stream_text(text: str) -> AsyncIterator[str]:
    for token in text.split(" "):
        yield token + " "
        await asyncio.sleep(0.01)


@app.entrypoint
async def handle_invocation(request: dict[str, Any], context=None) -> dict[str, Any]:
    prompt = str(request.get("prompt") or "").strip()
    session_id = str(request.get("session_id") or uuid.uuid4())
    if not prompt:
        return {"error": "No prompt provided", "session_id": session_id}
    return await process_message(session_id, prompt, request)


@app.websocket
async def handle_websocket(websocket, context):
    await websocket.accept()
    while True:
        raw = await websocket.receive_text()
        request = json.loads(raw)
        prompt = str(request.get("prompt") or "").strip()
        session_id = str(request.get("session_id") or uuid.uuid4())
        if not prompt:
            await websocket.send_text(
                json.dumps({"type": "error", "content": "No prompt provided", "session_id": session_id})
            )
            continue
        result = await process_message(session_id, prompt, request)
        async for chunk in stream_text(str(result.get("response") or "")):
            await websocket.send_text(json.dumps({"type": "chunk", "content": chunk, "session_id": session_id}))
        done_payload = {key: value for key, value in result.items() if key != "response"}
        await websocket.send_text(json.dumps({"type": "done", **done_payload, "session_id": session_id}))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    app.run(port=port)
