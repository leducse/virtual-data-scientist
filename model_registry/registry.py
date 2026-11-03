"""Versioned local model registry with approval and audit events."""

from __future__ import annotations

import datetime as dt
import json
import threading
import uuid
from pathlib import Path
from typing import Any


JsonDict = dict[str, Any]


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


class LocalModelRegistry:
    """Persist model cards and artifacts in one transparent JSON document.

    SageMaker Model Registry is the target managed analogue. This local class
    keeps the same important concepts—model group, version, approval state,
    metrics, lineage, and audit history—without creating cloud resources.
    """

    _lock = threading.Lock()

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _empty(self) -> JsonDict:
        return {"schema_version": 1, "model_groups": {}, "audit_events": []}

    def _read(self) -> JsonDict:
        if not self.path.exists():
            return self._empty()
        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("Model registry document must be a JSON object.")
        return {**self._empty(), **payload}

    def _write(self, payload: JsonDict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    def register_version(
        self,
        *,
        group_name: str,
        model_card: JsonDict,
        artifact: JsonDict,
        metrics: JsonDict,
        quality_gates: JsonDict,
        lineage: JsonDict,
    ) -> JsonDict:
        with self._lock:
            document = self._read()
            group = document["model_groups"].setdefault(
                group_name,
                {"name": group_name, "versions": []},
            )
            version_number = len(group["versions"]) + 1
            version = {
                "version": version_number,
                "version_id": f"{group_name}-v{version_number}",
                "status": "PendingReview",
                "created_at": _now(),
                "model_card": model_card,
                "artifact": artifact,
                "metrics": metrics,
                "quality_gates": quality_gates,
                "lineage": lineage,
            }
            group["versions"].append(version)
            document["audit_events"].append(
                {
                    "event_id": f"audit-{uuid.uuid4().hex[:10]}",
                    "event_type": "model_version_registered",
                    "timestamp": _now(),
                    "group_name": group_name,
                    "version": version_number,
                    "status": version["status"],
                }
            )
            self._write(document)
            return self.public_version(version)

    def approve_version(self, group_name: str, version_number: int) -> JsonDict:
        with self._lock:
            document = self._read()
            version = self._find(document, group_name, version_number)
            if not version["quality_gates"].get("passed"):
                raise ValueError("A version that failed quality gates cannot be approved.")
            version["status"] = "ApprovedForDemo"
            version["approved_at"] = _now()
            document["audit_events"].append(
                {
                    "event_id": f"audit-{uuid.uuid4().hex[:10]}",
                    "event_type": "model_version_approved_for_demo",
                    "timestamp": _now(),
                    "group_name": group_name,
                    "version": version_number,
                    "status": version["status"],
                }
            )
            self._write(document)
            return self.public_version(version)

    def record_batch_score(
        self,
        *,
        group_name: str,
        version_number: int,
        batch_id: str,
        records: int,
    ) -> None:
        with self._lock:
            document = self._read()
            self._find(document, group_name, version_number)
            document["audit_events"].append(
                {
                    "event_id": f"audit-{uuid.uuid4().hex[:10]}",
                    "event_type": "batch_scoring_completed",
                    "timestamp": _now(),
                    "group_name": group_name,
                    "version": version_number,
                    "batch_id": batch_id,
                    "records": records,
                }
            )
            self._write(document)

    def get_version(self, group_name: str, version_number: int) -> JsonDict:
        with self._lock:
            return dict(self._find(self._read(), group_name, version_number))

    def catalog(self) -> JsonDict:
        with self._lock:
            document = self._read()
            groups = []
            for group in document["model_groups"].values():
                groups.append(
                    {
                        "name": group["name"],
                        "versions": [self.public_version(version) for version in group["versions"]],
                    }
                )
            return {
                "model_groups": groups,
                "audit_events": list(document["audit_events"][-20:]),
            }

    @staticmethod
    def _find(document: JsonDict, group_name: str, version_number: int) -> JsonDict:
        group = document["model_groups"].get(group_name)
        if not group:
            raise ValueError(f"Unknown model group: {group_name}")
        for version in group["versions"]:
            if int(version["version"]) == int(version_number):
                return version
        raise ValueError(f"Unknown model version: {group_name} v{version_number}")

    @staticmethod
    def public_version(version: JsonDict) -> JsonDict:
        """Hide learned coefficients from catalog responses but retain lineage."""

        return {
            key: value
            for key, value in version.items()
            if key != "artifact"
        } | {
            "artifact_summary": {
                "model_type": version["artifact"].get("model_type"),
                "feature_count": len(version["artifact"].get("feature_names", [])),
            }
        }
