"""Lambda Function URL adapter for the Virtual Data Scientist backend."""

from __future__ import annotations

import base64
import json
import threading
from typing import Any
from urllib.parse import parse_qs, unquote

from server import (
    ANALYSIS_LOCK,
    continue_analysis,
    create_analysis_session,
    find_record,
    get_analysis_session_detail,
    get_analysis_status,
    get_schema,
    initialize_demo_database,
    list_analysis_sessions,
    list_data_sources,
    public_artifact,
    public_data_source,
    read_analysis_doc,
    request_deep_analysis,
    run_light_analysis,
    service_status,
    upload_csv_dataset,
    utc_now,
)

_INIT_LOCK = threading.Lock()
_INITIALIZED = False


def _json_response(payload: dict[str, Any], status_code: int = 200) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store",
        },
        "body": json.dumps(payload, default=str),
    }


def _read_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body")
    if not body:
        return {}
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    return json.loads(body)


def _method(event: dict[str, Any]) -> str:
    http = event.get("requestContext", {}).get("http", {})
    return str(http.get("method") or event.get("httpMethod") or "GET").upper()


def _path(event: dict[str, Any]) -> str:
    return unquote(str(event.get("rawPath") or event.get("path") or "/"))


def _query(event: dict[str, Any]) -> dict[str, str]:
    raw = str(event.get("rawQueryString") or "")
    parsed = parse_qs(raw, keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items()}


def _ensure_initialized() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return
    with _INIT_LOCK:
        if not _INITIALIZED:
            initialize_demo_database()
            _INITIALIZED = True


def _handle_get(path: str, query: dict[str, str]) -> dict[str, Any]:
    if path == "/api/health":
        return {"ok": True, "time": utc_now()}
    if path == "/api/config/status":
        return service_status()
    if path == "/api/data-sources":
        return {"data_sources": [public_data_source(source) for source in list_data_sources()]}
    if path == "/api/schema":
        return get_schema(query.get("data_source_id"))
    if path == "/api/analysis/sessions":
        return list_analysis_sessions()
    if path.startswith("/api/analysis/sessions/"):
        return get_analysis_session_detail(path.rsplit("/", 1)[-1])
    if path.startswith("/api/analysis/runs/"):
        return get_analysis_status(path.rsplit("/", 1)[-1])
    if path.startswith("/api/analysis/artifacts/"):
        artifact_id = path.rsplit("/", 1)[-1]
        with ANALYSIS_LOCK:
            doc = read_analysis_doc()
            artifact = find_record(doc, "artifacts", artifact_id)
            return {"ok": True, "artifact": public_artifact(artifact, include_content=True)}
    raise KeyError("Not found.")


def _handle_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    if path == "/api/analysis/sessions":
        return create_analysis_session(payload)
    if path == "/api/analysis/light":
        return run_light_analysis(payload)
    if path == "/api/analysis/deep":
        return request_deep_analysis(payload)
    if path == "/api/analysis/continue":
        return continue_analysis(payload)
    if path == "/api/csv/upload":
        name = str(payload.get("name", "uploaded_data"))
        csv_text = str(payload.get("csv_text", ""))
        return upload_csv_dataset(name, csv_text)
    raise KeyError("Not found.")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        _ensure_initialized()
        method = _method(event)
        path = _path(event)
        if method == "GET":
            return _json_response(_handle_get(path, _query(event)))
        if method == "POST":
            return _json_response(_handle_post(path, _read_body(event)))
        return _json_response({"ok": False, "error": "Method not allowed."}, 405)
    except KeyError as exc:
        return _json_response({"ok": False, "error": str(exc) or "Not found."}, 404)
    except ValueError as exc:
        return _json_response({"ok": False, "error": str(exc)}, 400)
    except Exception as exc:
        return _json_response({"ok": False, "error": f"Unexpected server error: {exc}"}, 500)
