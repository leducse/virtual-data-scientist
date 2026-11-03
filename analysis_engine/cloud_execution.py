"""Opt-in Code Interpreter boundary. Never use a local eval/exec fallback."""
from __future__ import annotations

import json
import threading
import time
import uuid
from analysis_engine.ingestion import InputError


class ExecutionFailure(InputError):
    pass


class CodeInterpreter:
    def __init__(self, client, identifier, max_seconds=120):
        if not 1 <= max_seconds <= 300:
            raise ValueError("Execution deadline must be 1–300 seconds")
        self.client, self.identifier, self.max_seconds = client, identifier, max_seconds
        self.session_id = None
        self.trace_id = uuid.uuid4().hex
        self._stop_lock = threading.Lock()
        self._stopped = False
        self.cleanup_error = None
        self._used = False

    def stop(self):
        with self._stop_lock:
            if self.session_id and not self._stopped:
                try:
                    self.client.stop_code_interpreter_session(codeInterpreterIdentifier=self.identifier,sessionId=self.session_id)
                    self._stopped = True
                    self.cleanup_error = None
                except Exception:
                    self.cleanup_error = "Stop was not confirmed; reconcile session state before retrying."

    def invoke(self, name, arguments):
        try:
            response = self.client.invoke_code_interpreter(codeInterpreterIdentifier=self.identifier,sessionId=self.session_id,
                                                          traceId=self.trace_id,name=name,arguments=arguments)
            results, size = [], 0
            for event in response["stream"]:
                if "result" not in event:
                    code = next(iter(event), "dependency_failure")
                    raise ExecutionFailure("Code Interpreter returned a service error.", code)
                result = event["result"]
                if result.get("isError") or result.get("structuredContent",{}).get("exitCode",0):
                    raise ExecutionFailure("Sandbox execution failed.", "execution_failed")
                # Keep result limits independent of the model's requested output.
                size += len(json.dumps(result,default=lambda v: f"<{len(v)} bytes>").encode())
                size += sum(len(c.get("data",b"")) + len(c.get("resource",{}).get("blob",b"")) for c in result.get("content",[]))
                if size > 2*1024*1024:
                    raise ExecutionFailure("Sandbox output exceeded 2 MiB.", "output_limit")
                results.append(result)
            if not results:
                raise ExecutionFailure("Sandbox returned no result.", "empty_output")
            return results
        except ExecutionFailure:
            raise
        except Exception as exc:
            # No automatic replay: the code may have executed before a response was lost.
            raise ExecutionFailure("Execution outcome is unknown; reconcile the session before retrying.", "outcome_unknown") from exc

    def execute(self, parquet: bytes, code: str, cancelled=None, files=None, output_files=None):
        if self._used:
            raise InputError("Use a fresh interpreter adapter for each run.", "session_reuse_rejected")
        self._used = True
        output_files = output_files or []
        if set(output_files) - {"plot.png"}:
            raise InputError("Unexpected output file.", "input_limit")
        if len(parquet) > 10*1024*1024 or len(code) > 32_000:
            raise InputError("Execution input exceeds the configured bound.", "input_limit")
        files = files or {}
        if set(files) - {"vds_recipe.py", "ingestion.py", "plan.json"} or sum(len(v) for v in files.values()) > 100_000:
            raise InputError("Unexpected sandbox support files.", "input_limit")
        cancelled = cancelled or threading.Event()
        completed = threading.Event()
        expired = threading.Event()
        start = time.monotonic()
        timings = {}
        try:
            try:
                response = self.client.start_code_interpreter_session(codeInterpreterIdentifier=self.identifier,
                    name=f"vds-{self.trace_id[:12]}",sessionTimeoutSeconds=self.max_seconds,clientToken=self.trace_id+"-vds")
                self.session_id = response["sessionId"]
            except Exception as exc:
                raise ExecutionFailure("Session creation was not confirmed; do not start a duplicate blindly.", "outcome_unknown") from exc
            timings["session_start"] = round((time.monotonic()-start)*1000,2)
            def monitor():
                while not completed.wait(.1):
                    if cancelled.is_set() or time.monotonic()-start > self.max_seconds:
                        expired.set()
                        self.stop()
                        return
            watcher = threading.Thread(target=monitor,daemon=True)
            watcher.start()
            if cancelled.is_set():
                raise ExecutionFailure("Execution cancelled.", "cancelled")
            self.invoke("writeFiles",{"content":[{"path":"dataset.parquet","blob":parquet}, *[{"path":name,"text":text} for name,text in files.items()]]})
            timings["input_ready"] = round((time.monotonic()-start)*1000,2)
            try:
                results = self.invoke("executeCode",{"language":"python","code":code,"clearContext":True})
            except ExecutionFailure:
                if expired.is_set() or cancelled.is_set():
                    raise ExecutionFailure("Execution cancelled or deadline exceeded.","cancelled" if cancelled.is_set() else "deadline_exceeded")
                raise
            if any(r.get("structuredContent",{}).get("taskStatus") in {"submitted","working"} for r in results):
                raise ExecutionFailure("Sandbox task has not reached a confirmed outcome.", "outcome_unknown")
            if expired.is_set() or cancelled.is_set():
                raise ExecutionFailure("Execution cancelled or deadline exceeded.","cancelled" if cancelled.is_set() else "deadline_exceeded")
            artifacts = self.invoke("readFiles", {"paths":output_files}) if output_files else []
            timings["total"] = round((time.monotonic()-start)*1000,2)
            return {"results":results,"artifacts":artifacts,"timing_ms":timings,"trace_id":self.trace_id,"session_id":self.session_id,"code":code,"execution":"agentcore_code_interpreter","support_files":files}
        finally:
            completed.set()
            self.stop()
