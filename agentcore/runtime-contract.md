# Virtual Data Scientist Runtime Contract

This is the local contract the AgentCore runtime entrypoint supports before AWS
deployment. It mirrors the consulting website bridge so the UI can swap from the
local HTTP bridge to AgentCore WebSocket mode without changing the app workflow.

## Request

```json
{
  "prompt": "Run deep analysis on the sales table.",
  "session_id": "vds-browser-session",
  "analysis_session_id": "sess_optional_app_session",
  "data_source_id": "demo_warehouse",
  "table_name": "orders",
  "run_deep": true
}
```

Fields:

- `prompt`: required natural-language user request.
- `session_id`: website/AgentCore conversation id.
- `analysis_session_id`: optional app-owned analysis session id. If present,
  the runtime appends the prompt through `continue_analysis`; otherwise it
  creates a new analysis session.
- `data_source_id`: registered backend data source. Defaults to
  `demo_warehouse` for local validation.
- `table_name`: optional registered table scope.
- `run_deep`: optional boolean override. If omitted, the runtime infers deep
  analysis intent from the prompt.

## Response

```json
{
  "response": "Human-readable analysis summary",
  "session_id": "vds-browser-session",
  "analysis_session_id": "sess_app_session",
  "data_source_id": "demo_warehouse",
  "table_name": "orders",
  "light_run_id": "run_light",
  "deep_run_id": "run_deep",
  "deep_status": "succeeded",
  "artifacts": [
    {
      "id": "artifact_id",
      "artifact_type": "report",
      "title": "Local deep analysis report",
      "summary": "Recommended path..."
    }
  ]
}
```

The runtime returns artifact metadata only. Full artifact contents stay in the
BI app's artifact store and should be fetched through authenticated backend
APIs, not streamed directly through the public chat surface.

## Local Contract Tests

The runtime contract is validated without AWS by monkeypatching the MCP facade
calls:

```bash
cd /Users/scottleduc/Projects/virtual-data-scientist
python3 -m unittest tests.test_mcp_stdio_contract tests.test_virtual_data_scientist_agent
```

These tests prove that the runtime creates or continues app-owned analysis
sessions, preserves the `registered_dataset_only` deep-analysis constraint,
polls deep-analysis status, and returns artifact metadata without artifact
content.

## Tool Boundary

The runtime does not connect directly to databases or credentials. It calls the
MCP/API facade tools:

- `create_analysis_session`
- `continue_analysis`
- `run_light_analysis`
- `request_deep_analysis`
- `get_analysis_status`
- `get_analysis_session`

The app-owned database and artifact store remain the source of truth.
