"""Runtime-local tool wrappers for the deployed AgentCore CodeZip package."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


BASE_URL = os.environ.get("DATA_SCIENCE_MCP_BASE_URL", "http://127.0.0.1:8765").rstrip("/")
AUTH_MODE = os.environ.get("DATA_SCIENCE_MCP_AUTH_MODE", "none").strip().lower()
AWS_REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
AWS_SIGNING_SERVICE = os.environ.get("DATA_SCIENCE_MCP_AWS_SIGNING_SERVICE", "lambda").strip()


def _sigv4_headers(method: str, url: str, headers: dict[str, str], data: bytes | None) -> dict[str, str]:
    try:
        import botocore.auth
        import botocore.awsrequest
        import botocore.session
    except ImportError as exc:
        raise RuntimeError("DATA_SCIENCE_MCP_AUTH_MODE=aws_iam requires botocore.") from exc

    session = botocore.session.get_session()
    credentials = session.get_credentials()
    if credentials is None:
        raise RuntimeError("AWS credentials are required for DATA_SCIENCE_MCP_AUTH_MODE=aws_iam.")

    request = botocore.awsrequest.AWSRequest(method=method, url=url, data=data, headers=headers)
    botocore.auth.SigV4Auth(credentials.get_frozen_credentials(), AWS_SIGNING_SERVICE, AWS_REGION).add_auth(request)
    return dict(request.headers.items())


def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{BASE_URL}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if AUTH_MODE in {"aws_iam", "sigv4"}:
        headers = _sigv4_headers(method, url, headers, data)
    elif AUTH_MODE not in {"", "none"}:
        raise RuntimeError(f"Unsupported DATA_SCIENCE_MCP_AUTH_MODE: {AUTH_MODE}")

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"error": body}
        raise RuntimeError(parsed.get("error") or f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not reach the data science app at {BASE_URL}. "
            "Set DATA_SCIENCE_MCP_BASE_URL to the authenticated backend endpoint."
        ) from exc


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "create_analysis_session":
        return _request("POST", "/api/analysis/sessions", arguments)
    if name == "upload_dataset":
        return _request("POST", "/api/csv/upload", arguments)
    if name == "run_light_analysis":
        return _request("POST", "/api/analysis/light", arguments)
    if name == "request_deep_analysis":
        return _request("POST", "/api/analysis/deep", arguments)
    if name == "get_analysis_status":
        run_id = urllib.parse.quote(str(arguments.get("run_id", "")))
        if not run_id:
            raise RuntimeError("run_id is required.")
        return _request("GET", f"/api/analysis/runs/{run_id}")
    if name == "get_analysis_session":
        session_id = urllib.parse.quote(str(arguments.get("session_id", "")))
        if not session_id:
            raise RuntimeError("session_id is required.")
        return _request("GET", f"/api/analysis/sessions/{session_id}")
    if name == "continue_analysis":
        return _request("POST", "/api/analysis/continue", arguments)
    raise RuntimeError(f"Unknown tool: {name}")
